"""Offline backup and restore with content checksums and process exclusion."""
from contextlib import contextmanager
import fcntl
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import zipfile

from .store import digest, packed


@contextmanager
def exclusive_lock(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (root / '.service.lock').open('a') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('此数据目录正在使用。请先停止服务再维护；服务只允许单进程运行。') from None
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def backup(root, destination):
    root, destination = Path(root).resolve(), Path(destination).resolve()
    if root in destination.parents or destination.exists():
        raise ValueError('备份必须写入数据目录之外的新文件。')
    with exclusive_lock(root), tempfile.TemporaryDirectory() as tmp:
        staging = Path(tmp)
        dbpath = root / 'workbench.sqlite3'
        if not dbpath.is_file():
            raise ValueError('数据目录未初始化。')
        source = sqlite3.connect(dbpath)
        target = sqlite3.connect(staging / 'workbench.sqlite3')
        try:
            source.backup(target)
            target.execute('DELETE FROM sessions')
            target.commit()
        finally:
            source.close()
            target.close()
        paths = [staging / 'workbench.sqlite3']
        checksums = {'workbench.sqlite3': digest(paths[0].read_bytes())}
        artifacts = root / 'files'
        if artifacts.exists():
            for path in artifacts.rglob('*'):
                if path.is_symlink():
                    raise ValueError('备份拒绝包含符号链接。')
                if path.is_file():
                    checksums[str(path.relative_to(root))] = digest(path.read_bytes())
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation never overwrites a previous backup.
        with destination.open('xb') as output:
            destination.chmod(0o600)
            with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
                for name in checksums:
                    archive.write(staging / name if name == 'workbench.sqlite3' else root / name, name)
                archive.writestr('manifest.json', packed({'format': 1, 'sha256': checksums}))
    return destination


def restore(archive_path, destination):
    destination = Path(destination).resolve()
    if destination.exists():
        raise ValueError('恢复目标必须是尚不存在的新目录。')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as tmp, zipfile.ZipFile(archive_path) as archive:
        staging = Path(tmp)
        entries = archive.infolist()
        if len(entries) > 100000 or sum(e.file_size for e in entries) > 2 * 1024**3:
            raise ValueError('备份超过恢复大小限制。')
        names = [e.filename for e in entries]
        if len(set(names)) != len(names):
            raise ValueError('备份包含重复文件。')
        manifest = json.loads(archive.read('manifest.json'))
        if manifest.get('format') != 1 or set(names) != set(manifest['sha256']) | {'manifest.json'}:
            raise ValueError('备份清单不匹配。')
        if 'workbench.sqlite3' not in manifest['sha256']:
            raise ValueError('备份缺少数据库。')
        for name, checksum in manifest['sha256'].items():
            path = Path(name)
            if path.is_absolute() or '..' in path.parts or (name != 'workbench.sqlite3' and path.parts[0] != 'files'):
                raise ValueError('备份包含不安全路径。')
            data = archive.read(name)
            if digest(data) != checksum:
                raise ValueError('备份校验失败。')
            output = staging / path
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(data)
        db = sqlite3.connect(staging / 'workbench.sqlite3')
        try:
            if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or db.execute('PRAGMA user_version').fetchone()[0] != 1:
                raise ValueError('数据库校验失败或版本不支持。')
            db.execute('DELETE FROM sessions')
            db.commit()
        finally:
            db.close()
        staging.chmod(0o700)
        (staging / 'workbench.sqlite3').chmod(0o600)
        shutil.move(str(staging), str(destination))
    return destination
