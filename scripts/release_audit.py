"""Audit tracked release content and Git history for private information."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
import subprocess
import sys
from typing import Iterable


WINDOWS_USER_PATH = re.compile(r"(?i)\b[A-Z]:\\Users\\[^\\/\r\n]+")
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
PROTECTED_DIRECTORIES = {"private-inputs", "customer-data"}


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
    if protected_directory or protected_root_file:
        return Finding("protected-business-file", path.as_posix(), 0, _redact(path.name))
    return None


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
        data = path.read_bytes()
        if b"\0" in data:
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            continue
        findings.extend(audit_text(text, relative.as_posix(), banlist))

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
    parser.add_argument("--banlist", type=Path, help="exact-value banlist; defaults to the ignored local file")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    repo = Path(__file__).resolve().parents[1]
    banlist_path = args.banlist or repo / ".release-audit.local.txt"
    try:
        findings = audit_repository(repo, args.history, _read_banlist(banlist_path))
    except (OSError, subprocess.SubprocessError) as exc:
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
