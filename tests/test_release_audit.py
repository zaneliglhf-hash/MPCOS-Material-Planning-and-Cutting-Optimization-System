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
