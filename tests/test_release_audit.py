from pathlib import Path

from scripts.release_audit import Finding, audit_text


def test_audit_redacts_private_values():
    secret = "private-person" + "@" + "private.example"
    findings = audit_text(f"contact={secret}", "sample.txt", (secret,))
    assert findings
    rendered = "\n".join(item.render() for item in findings)
    assert secret not in rendered
    assert "pr***le" in rendered


def test_audit_detects_windows_username():
    private_path = "C:" + "\\Users\\" + "private-user\\project"
    findings = audit_text(private_path, "sample.txt", ())
    assert any(item.category == "windows-user-path" for item in findings)


def test_audit_allows_documentation_and_noreply_email_domains():
    text = "demo@example.com contributors@users.noreply.github.com"
    assert audit_text(text, "sample.txt", ()) == []


def test_finding_render_never_needs_original_value():
    finding = Finding("local-banlist", Path("sample.txt").as_posix(), 3, "se***et")
    assert finding.render() == "local-banlist: sample.txt:3: se***et"


def test_audit_detects_unix_path_and_tokens_without_printing_them():
    private_path = '/' + 'Users' + '/private-user/project'
    token = 'sk-' + 'x' * 32
    key_header = '-----BEGIN ' + 'PRIVATE KEY-----'
    findings = audit_text('\n'.join([private_path, token, key_header]), 'example.txt', ())
    assert {item.category for item in findings} == {'unix-user-path', 'access-token', 'private-key'}
    assert token not in '\n'.join(item.render() for item in findings)


def test_protected_paths_include_runtime_credentials_and_local_lessons():
    from scripts.release_audit import _protected_path_finding
    for name in ['.env', '.env.production', '.local-access.md', 'var/workbench.sqlite3',
                 'backups/backup.zip', '.DS_Store', 'elsewhere/database.db', 'docs/agent-lesson-01.md']:
        assert _protected_path_finding(Path(name)) is not None
    for name in ['.env.example', 'examples/minimal.json', 'src/cutting_layout/workbench/app.py']:
        assert _protected_path_finding(Path(name)) is None


def test_staged_audit_reads_index_not_cleaned_worktree(tmp_path):
    import subprocess
    from scripts.release_audit import audit_staged
    def git(*args):
        subprocess.run(['git', *args], cwd=tmp_path, check=True, capture_output=True)
    git('init')
    secret = 'sk-' + 'x' * 32
    path = tmp_path / 'settings.txt'
    path.write_text(secret)
    git('add', 'settings.txt')
    path.write_text('cleaned working file')
    assert any(item.category == 'access-token' for item in audit_staged(tmp_path, ()))


def test_package_audit_checks_sdist_and_wheel_contents(tmp_path):
    import io
    import tarfile
    import zipfile
    from scripts.release_audit import audit_archive
    wheel = tmp_path / 'example.whl'
    secret = 'sk-' + 'x' * 32
    with zipfile.ZipFile(wheel, 'w') as archive:
        archive.writestr('.env', secret)
        archive.writestr('package/app.py', 'print("hello")')
    assert {f.category for f in audit_archive(wheel, ())} == {'protected-business-file', 'access-token'}
    sdist = tmp_path / 'example.tar.gz'
    with tarfile.open(sdist, 'w:gz') as archive:
        info = tarfile.TarInfo('example-1.0/var/database.sqlite3')
        info.size = 3
        archive.addfile(info, io.BytesIO(b'abc'))
    assert any(f.category == 'protected-business-file' for f in audit_archive(sdist, ()))
