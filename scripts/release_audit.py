"""Audit tracked release content and Git history for private information."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
import subprocess
import sys
import tarfile
from typing import Iterable
import zipfile


WINDOWS_USER_PATH = re.compile(r"(?i)\b[A-Z]:\\Users\\[^\\/\r\n]+")
UNIX_USER_PATH = re.compile(r"/(?:Users|home)/[^/\s\"'<>]+")
ACCESS_TOKEN = re.compile(
    r"\b(?:sk-[A-Za-z0-9_-]{24,}|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})\b"
)
PRIVATE_KEY = re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")
EMAIL = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
MAINLAND_MOBILE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
MAINLAND_ID = re.compile(
    r"(?<!\d)\d{6}(?:19|20)\d{2}(?:0[1-9]|1[0-2])"
    r"(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx](?!\d)"
)
SAFE_EMAIL_DOMAINS = {
    "example.com",
    "example.net",
    "example.org",
    "users.noreply.github.com",
}
PROTECTED_EXTENSIONS = {".bak", ".dwg", ".dxf"}
PROTECTED_DIRECTORIES = {
    "private-inputs", "customer-data", "var", "backups", "output",
    ".git", ".venv", ".smoke-venv", ".superpowers",
}
PRIVATE_SUFFIXES = {".sqlite", ".sqlite3", ".db", ".pem", ".key", ".p12", ".pfx", ".log"}


@dataclass(frozen=True, order=True)
class Finding:
    category: str
    source: str
    line: int
    redacted: str

    def render(self) -> str:
        return f"{self.category}: {self.source}:{self.line}: {self.redacted}"


def _redact(value: str) -> str:
    if len(value) <= 4:
        return "*" * len(value)
    return f"{value[:2]}***{value[-2:]}"


def _matches(pattern: re.Pattern[str], text: str) -> Iterable[tuple[int, str]]:
    for line_number, line in enumerate(text.splitlines(), start=1):
        for match in pattern.finditer(line):
            yield line_number, match.group(0)


def audit_text(text: str, source: str, banlist: tuple[str, ...]) -> list[Finding]:
    findings: list[Finding] = []
    for line, value in _matches(WINDOWS_USER_PATH, text):
        findings.append(Finding("windows-user-path", source, line, _redact(value)))
    for category, pattern in (
        ("unix-user-path", UNIX_USER_PATH),
        ("access-token", ACCESS_TOKEN),
        ("private-key", PRIVATE_KEY),
    ):
        for line, value in _matches(pattern, text):
            findings.append(Finding(category, source, line, _redact(value)))
    for line, value in _matches(EMAIL, text):
        domain = value.rsplit("@", 1)[-1].lower()
        if domain not in SAFE_EMAIL_DOMAINS:
            findings.append(Finding("private-email", source, line, _redact(value)))
    for line, value in _matches(MAINLAND_MOBILE, text):
        findings.append(Finding("mainland-mobile", source, line, _redact(value)))
    for line, value in _matches(MAINLAND_ID, text):
        findings.append(Finding("mainland-id", source, line, _redact(value)))
    for forbidden in banlist:
        if not forbidden:
            continue
        for line, value in _matches(re.compile(re.escape(forbidden)), text):
            findings.append(Finding("local-banlist", source, line, _redact(value)))
    return sorted(set(findings))


def _git(repo: Path, *args: str, text: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=text,
        encoding="utf-8" if text else None,
        errors="replace" if text else None,
    )


def _tracked_paths(repo: Path) -> tuple[Path, ...]:
    completed = _git(repo, "ls-files", "-z")
    names = completed.stdout.decode("utf-8", errors="surrogateescape").split("\0")
    return tuple(Path(name) for name in names if name)


def _protected_path_finding(path: Path) -> Finding | None:
    normalized_parts = tuple(part.lower() for part in path.parts)
    protected_directory = bool(normalized_parts) and normalized_parts[0] in PROTECTED_DIRECTORIES
    protected_root_file = len(path.parts) == 1 and path.suffix.lower() in PROTECTED_EXTENSIONS
    name = path.name.lower()
    private_file = (
        name in {".ds_store", ".local-access.md", ".release-audit.local.txt"}
        or (name.startswith(".env") and name != ".env.example")
        or path.suffix.lower() in PRIVATE_SUFFIXES
        or ".sqlite3-" in name or ".db-" in name
        or name.startswith("id_rsa") or name.startswith("id_ed25519")
        or (len(path.parts) >= 2 and path.parts[0] == "docs" and name.startswith("agent-lesson-"))
        or path.parts[:2] in {("docs", "superpowers"), ("docs", "codebase")}
    )
    if protected_directory or protected_root_file or private_file:
        return Finding("protected-business-file", path.as_posix(), 0, _redact(path.name))
    return None


def audit_bytes(data: bytes, source: str, banlist: tuple[str, ...]) -> list[Finding]:
    # Text scanners cannot inspect visible contents of raster images. Exact
    # local secret matches still apply to binary/package metadata.
    if b"\0" in data:
        return [Finding("local-banlist", source, 0, _redact(value))
                for value in banlist if value and value.encode() in data]
    try:
        return audit_text(data.decode("utf-8"), source, banlist)
    except UnicodeDecodeError:
        return []


def audit_staged(repo: Path, banlist: tuple[str, ...]) -> list[Finding]:
    """Audit the actual index blobs, including force-added ignored files."""
    findings = []
    for path in _tracked_paths(repo):
        protected = _protected_path_finding(path)
        if protected:
            findings.append(protected)
        data = _git(repo, "show", f":{path.as_posix()}").stdout
        findings.extend(audit_bytes(data, path.as_posix(), banlist))
    return sorted(set(findings))


def audit_archive(path: Path, banlist: tuple[str, ...]) -> list[Finding]:
    """Scan an sdist/wheel without extracting or executing archive contents."""
    findings = []

    def check(name: str, data: bytes, *, sdist: bool = False):
        relative = Path(name)
        if sdist and len(relative.parts) > 1:
            relative = Path(*relative.parts[1:])
        source = f"{path.name}:{name}"
        protected = _protected_path_finding(relative)
        if protected:
            findings.append(Finding(protected.category, source, 0, protected.redacted))
        findings.extend(audit_bytes(data, source, banlist))

    if path.suffix in {".whl", ".zip"}:
        with zipfile.ZipFile(path) as archive:
            for entry in archive.infolist():
                if not entry.is_dir():
                    check(entry.filename, archive.read(entry))
    else:
        with tarfile.open(path, "r:*") as archive:
            for entry in archive:
                if entry.issym() or entry.islnk():
                    findings.append(Finding("archive-link", f"{path.name}:{entry.name}", 0, "link"))
                elif entry.isfile():
                    with archive.extractfile(entry) as handle:
                        check(entry.name, handle.read(), sdist=True)
    return sorted(set(findings))


def audit_repository(
    repo: Path,
    include_history: bool,
    banlist: tuple[str, ...],
) -> list[Finding]:
    repo = repo.resolve()
    findings: list[Finding] = []
    for relative in _tracked_paths(repo):
        protected = _protected_path_finding(relative)
        if protected is not None:
            findings.append(protected)
        path = repo / relative
        if not path.is_file():
            continue
        findings.extend(audit_bytes(path.read_bytes(), relative.as_posix(), banlist))

    if include_history:
        history = _git(
            repo,
            "log",
            "--all",
            "--format=fuller",
            "-p",
            "--no-ext-diff",
            "--no-textconv",
            text=True,
        ).stdout
        findings.extend(audit_text(history, "<git-history>", banlist))
    return sorted(set(findings))


def _read_banlist(path: Path | None) -> tuple[str, ...]:
    if path is None or not path.exists():
        return ()
    return tuple(
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit release content for private information.")
    parser.add_argument("--history", action="store_true", help="also scan all reachable Git history")
    parser.add_argument("--staged", action="store_true", help="scan the actual Git index instead of working files")
    parser.add_argument("--archive", type=Path, action="append", default=[], help="also scan a built wheel or sdist")
    parser.add_argument("--banlist", type=Path, help="exact-value banlist; defaults to the ignored local file")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    repo = Path(__file__).resolve().parents[1]
    banlist_path = args.banlist or repo / ".release-audit.local.txt"
    try:
        banlist = _read_banlist(banlist_path)
        findings = (audit_staged(repo, banlist) if args.staged
                    else audit_repository(repo, args.history, banlist))
        if args.staged and args.history:
            findings.extend(audit_repository(repo, True, banlist))
        for archive in args.archive:
            findings.extend(audit_archive(archive, banlist))
        findings = sorted(set(findings))
    except (OSError, subprocess.SubprocessError, zipfile.BadZipFile, tarfile.TarError) as exc:
        print(f"release audit error: {exc}", file=sys.stderr)
        return 2
    if findings:
        for finding in findings:
            print(finding.render())
        print(f"release audit failed: {len(findings)} finding(s)", file=sys.stderr)
        return 1
    print("release audit passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
