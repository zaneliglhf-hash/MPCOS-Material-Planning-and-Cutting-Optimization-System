"""SQLite transactions, identities and append-only business audit records."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import hmac
import json
from pathlib import Path
import re
import secrets
import sqlite3
import time


class Problem(Exception):
    def __init__(self, status: int, message: str):
        self.status, self.message = status, message
        super().__init__(message)


def packed(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def password_hash(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    value = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=32768, r=8, p=3, maxmem=67108864)
    return salt + ":" + value.hex()


def password_matches(password: str, encoded: str) -> bool:
    return hmac.compare_digest(password_hash(password, encoded.split(":")[0]), encoded)


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
 id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL, password TEXT NOT NULL,
 role TEXT NOT NULL CHECK(role IN ('employee','manager')), active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS sessions (
 token TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), csrf TEXT NOT NULL, expires REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS login_attempts (ip TEXT NOT NULL, username TEXT NOT NULL, at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS orders (
 id TEXT PRIMARY KEY, title TEXT NOT NULL, material TEXT NOT NULL, profile TEXT NOT NULL,
 owner TEXT NOT NULL REFERENCES users(id), created REAL NOT NULL,
 messages TEXT NOT NULL DEFAULT '[]', proposal TEXT, chat_busy INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS versions (
 id TEXT PRIMARY KEY, order_id TEXT NOT NULL REFERENCES orders(id), number INTEGER NOT NULL,
 actor TEXT NOT NULL REFERENCES users(id), created REAL NOT NULL, parameters TEXT NOT NULL,
 process_source TEXT NOT NULL, status TEXT NOT NULL,
 request_key TEXT NOT NULL, request_hash TEXT NOT NULL, result TEXT, error TEXT,
 reviewer TEXT REFERENCES users(id), reviewed_at REAL, review_note TEXT,
 UNIQUE(order_id,number), UNIQUE(order_id,request_key)
);
CREATE UNIQUE INDEX IF NOT EXISTS active_order_job ON versions(order_id) WHERE status IN ('queued','running');
CREATE TABLE IF NOT EXISTS audit (
 id INTEGER PRIMARY KEY AUTOINCREMENT, order_id TEXT REFERENCES orders(id), actor TEXT,
 event TEXT NOT NULL, details TEXT NOT NULL, at REAL NOT NULL
);
CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit BEGIN SELECT RAISE(ABORT,'audit is append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit BEGIN SELECT RAISE(ABORT,'audit is append-only'); END;
CREATE TABLE IF NOT EXISTS model_calls (user_id TEXT NOT NULL, order_id TEXT NOT NULL, at REAL NOT NULL);
PRAGMA user_version=1;
"""


class Store:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.root / "workbench.sqlite3"
        with self.connection() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise RuntimeError("Unsupported database version; restore the matching application release.")
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(SCHEMA)
        self.path.chmod(0o600)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @contextmanager
    def transaction(self):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            yield db

    @staticmethod
    def audit(db, order_id, actor, event, details=None):
        db.execute("INSERT INTO audit(order_id,actor,event,details,at) VALUES(?,?,?,?,?)",
                   (order_id, actor, event, packed(details or {}), time.time()))

    def create_user(self, username, password, role):
        if not re.fullmatch(r"[a-zA-Z0-9_.-]{3,40}", username):
            raise ValueError("用户名须为 3–40 位英文字母、数字、点、横线或下划线。")
        if not 12 <= len(password) <= 256 or role not in {"employee", "manager"}:
            raise ValueError("密码须为 12–256 个字符，角色须为 employee 或 manager。")
        encoded = password_hash(password)
        with self.transaction() as db:
            uid = secrets.token_hex(16)
            db.execute("INSERT INTO users(id,username,password,role) VALUES(?,?,?,?)", (uid, username, encoded, role))
            self.audit(db, None, "local-admin", "user_created", {"username": username, "role": role})
        return uid

    def reset_password(self, username, password):
        if not 12 <= len(password) <= 256:
            raise ValueError("密码须为 12–256 个字符。")
        encoded = password_hash(password)
        with self.transaction() as db:
            user = db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
            if not user:
                raise ValueError("账号不存在。")
            db.execute("UPDATE users SET password=? WHERE id=?", (encoded, user['id']))
            db.execute("DELETE FROM sessions WHERE user_id=?", (user['id'],))
            self.audit(db, None, "local-admin", "password_reset", {"username": username})

    def disable_user(self, username):
        with self.transaction() as db:
            user = db.execute('SELECT id FROM users WHERE username=?', (username,)).fetchone()
            if not user:
                raise ValueError('账号不存在。')
            db.execute('UPDATE users SET active=0 WHERE id=?', (user['id'],))
            db.execute('DELETE FROM sessions WHERE user_id=?', (user['id'],))
            self.audit(db, None, 'local-admin', 'user_disabled', {'username': username})

    def login(self, username, password, ip):
        now = time.time()
        with self.transaction() as db:
            db.execute("DELETE FROM login_attempts WHERE at<?", (now - 900,))
            attempts = db.execute("SELECT COUNT(*) FROM login_attempts WHERE ip=? OR username=?", (ip, username)).fetchone()[0]
            if attempts >= 10:
                raise Problem(429, "尝试过多，请 15 分钟后再试。")
            db.execute("INSERT INTO login_attempts VALUES(?,?,?)", (ip, username, now))
            user = db.execute("SELECT * FROM users WHERE username=? AND active=1", (username,)).fetchone()
        # Unknown users pay the same password-hash cost; no credential details are logged.
        valid = password_matches(password, user['password'] if user else '00' * 16 + ':' + '00' * 64)
        if not user or not valid:
            raise Problem(401, "账号或密码不正确。")
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        with self.transaction() as db:
            db.execute("DELETE FROM login_attempts WHERE ip=? AND username=? AND at=?", (ip, username, now))
            db.execute("DELETE FROM sessions WHERE expires<?", (now,))
            db.execute("INSERT INTO sessions VALUES(?,?,?,?)", (digest(token.encode()), user['id'], csrf, now + 8 * 3600))
            self.audit(db, None, user['id'], "login")
        return token, csrf

    def session(self, token):
        with self.connection() as db:
            row = db.execute("SELECT u.id,u.username,u.role,s.csrf FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=? AND s.expires>? AND u.active=1",
                             (digest(token.encode()), time.time())).fetchone()
        if row is None:
            raise Problem(401, "请先登录。")
        return dict(row)

    def order(self, db, oid, user, *, write=False):
        row = db.execute("SELECT o.*,u.username AS owner_name FROM orders o JOIN users u ON u.id=o.owner WHERE o.id=?", (oid,)).fetchone()
        if row is None or (row['owner'] != user['id'] and (write or user['role'] != 'manager')):
            raise Problem(404, "订单不存在或无权访问。")
        return dict(row)

    def reserve_call(self, oid, uid):
        now = time.time()
        with self.transaction() as db:
            order_calls = db.execute("SELECT COUNT(*) FROM model_calls WHERE order_id=?", (oid,)).fetchone()[0]
            daily = db.execute("SELECT COUNT(*) FROM model_calls WHERE user_id=? AND at>?", (uid, now - 86400)).fetchone()[0]
            if order_calls >= 40 or daily >= 100:
                raise Problem(429, "模型请求上限已到：每订单 40 次，每账号滚动 24 小时 100 次。仍可填写参数生成方案。")
            db.execute("INSERT INTO model_calls VALUES(?,?,?)", (uid, oid, now))
