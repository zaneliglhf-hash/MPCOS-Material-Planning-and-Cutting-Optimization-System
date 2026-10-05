import http.client
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from cutting_layout import deepseek_connection as client
from examples import agent_lesson_03
from scripts import setup_deepseek


FAKE_KEY = "fictional-key-for-offline-tests"


@pytest.fixture(autouse=True)
def forbid_live_api(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    def forbidden(*args, **kwargs):
        pytest.fail("Tests must never access the real API")

    monkeypatch.setattr(client.http.client, "HTTPSConnection", forbidden)


def test_private_config_round_trip_and_no_overwrite(tmp_path):
    path = client.save_api_key(tmp_path, FAKE_KEY)
    assert client.load_api_key(tmp_path) == FAKE_KEY
    if os.name == "posix":
        assert path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        client.save_api_key(tmp_path, "another-fictional-key")
    assert client.load_api_key(tmp_path) == FAKE_KEY


@pytest.mark.parametrize("key", ["", "  ", "test\nnew-field", "中文密钥", "test\x00key"])
def test_invalid_key_is_not_written(tmp_path, key):
    with pytest.raises(client.DeepSeekConnectionError):
        client.save_api_key(tmp_path, key)
    assert not (tmp_path / ".env").exists()


def test_environment_can_supply_key_without_file(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", FAKE_KEY)
    assert client.load_api_key(tmp_path) == FAKE_KEY
    assert not (tmp_path / ".env").exists()


@pytest.mark.parametrize("content", [
    None,
    b"unrelated=value\n",
    b"DEEPSEEK_API_KEY=\n",
    b"DEEPSEEK_API_KEY=one\nDEEPSEEK_API_KEY=two\n",
    b"\xff",
])
def test_config_errors_are_safe_and_actionable(tmp_path, content):
    if content is not None:
        (tmp_path / ".env").write_bytes(content)
    with pytest.raises(client.DeepSeekConnectionError) as error:
        client.load_api_key(tmp_path)
    assert "DEEPSEEK_API_KEY=one" not in str(error.value)


@pytest.fixture
def fake_api(tmp_path, monkeypatch):
    client.save_api_key(tmp_path, FAKE_KEY)
    state = SimpleNamespace(
        status=200,
        body=json.dumps({
            "choices": [{"message": {"content": "连接成功"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 4, "secret": FAKE_KEY},
        }, ensure_ascii=False).encode("utf-8"),
        failure=None,
        calls=[],
        closed=False,
    )

    class Connection:
        def __init__(self, host, timeout):
            state.host = host
            state.timeout = timeout

        def request(self, method, path, *, body, headers):
            state.calls.append((method, path, json.loads(body), headers))
            if state.failure:
                raise state.failure

        def getresponse(self):
            return SimpleNamespace(status=state.status, read=lambda limit: state.body[:limit])

        def close(self):
            state.closed = True

    monkeypatch.setattr(client.http.client, "HTTPSConnection", Connection)
    return state


def test_probe_makes_one_small_request_without_orders_or_key_in_body(tmp_path, fake_api):
    result = client.probe_connection(tmp_path)
    assert result == {
        "status": "connected", "model": "deepseek-flash", "reply": "连接成功",
        "usage": {"prompt_tokens": 10, "completion_tokens": 4},
    }
    assert fake_api.host == "api.deepseek.com"
    assert len(fake_api.calls) == 1
    method, path, body, headers = fake_api.calls[0]
    assert method == "POST" and path == "/chat/completions"
    assert headers["Authorization"] == f"Bearer {FAKE_KEY}"
    assert FAKE_KEY not in json.dumps(body)
    assert "tools" not in body
    assert body["thinking"] == {"type": "disabled"}
    assert body["max_tokens"] <= 64
    assert body["stream"] is False
    assert fake_api.closed


@pytest.mark.parametrize("status", [302, 400, 401, 402, 422, 429, 500, 503])
def test_http_error_does_not_echo_secret_retry_or_follow_redirect(tmp_path, fake_api, status):
    fake_api.status = status
    fake_api.body = FAKE_KEY.encode("utf-8")
    with pytest.raises(client.DeepSeekConnectionError) as error:
        client.probe_connection(tmp_path)
    assert str(status) in str(error.value)
    assert FAKE_KEY not in str(error.value)
    assert len(fake_api.calls) == 1
    assert fake_api.closed


@pytest.mark.parametrize("failure", [TimeoutError(FAKE_KEY), http.client.HTTPException(FAKE_KEY)])
def test_network_error_is_redacted_and_not_retried(tmp_path, fake_api, failure):
    fake_api.failure = failure
    with pytest.raises(client.DeepSeekConnectionError, match="网络连接失败") as error:
        client.probe_connection(tmp_path)
    assert FAKE_KEY not in str(error.value)
    assert len(fake_api.calls) == 1
    assert fake_api.closed


@pytest.mark.parametrize("body", [
    b"not json",
    b"[]",
    b'{"choices": []}',
    b'{"choices": [{"message": {"content": null}}]}',
    b'{"choices": [{"message": {"content": " "}}]}',
    b"x" * (64 * 1024 + 1),
])
def test_unusable_response_is_not_reported_as_connected(tmp_path, fake_api, body):
    fake_api.body = body
    with pytest.raises(client.DeepSeekConnectionError):
        client.probe_connection(tmp_path)


def test_reply_redaction_and_missing_usage(tmp_path, fake_api):
    fake_api.body = json.dumps({
        "choices": [{"message": {"content": "echo: " + FAKE_KEY}}],
        "usage": None,
    }).encode("utf-8")
    result = client.probe_connection(tmp_path)
    assert FAKE_KEY not in json.dumps(result)
    assert result["usage"] == {}


def test_setup_hides_input_and_never_prints_key(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(setup_deepseek, "ROOT", tmp_path)
    monkeypatch.setattr(setup_deepseek.sys, "stdin", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(setup_deepseek.getpass, "getpass", lambda prompt: FAKE_KEY)
    assert setup_deepseek.main([]) == 0
    assert FAKE_KEY not in capsys.readouterr().out
    assert client.load_api_key(tmp_path) == FAKE_KEY
    # Running setup twice keeps the first configuration.
    assert setup_deepseek.main([]) == 0
    assert "已保留" in capsys.readouterr().out


def test_setup_refuses_noninteractive_input(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(setup_deepseek, "ROOT", tmp_path)
    monkeypatch.setattr(setup_deepseek.sys, "stdin", SimpleNamespace(isatty=lambda: False))
    assert setup_deepseek.main([]) == 2
    assert not (tmp_path / ".env").exists()


def test_lesson_reports_errors_without_traceback(monkeypatch, capsys):
    def fail(root):
        raise client.DeepSeekConnectionError("账户余额不足（402）。")

    monkeypatch.setattr(agent_lesson_03, "probe_connection", fail)
    assert agent_lesson_03.main() == 2
    output = capsys.readouterr().out
    assert '"status": "error"' in output and "402" in output
    assert "Traceback" not in output


def test_replace_preserves_other_settings_and_removes_duplicate_keys(tmp_path):
    path = tmp_path / ".env"
    path.write_bytes(
        b"# keep this comment\r\nOTHER=value\r\nDEEPSEEK_API_KEY=old-one\r\n"
        b"  DEEPSEEK_API_KEY=old-two\r\nLAST=unchanged"
    )
    path.chmod(0o644)
    client.save_api_key(tmp_path, FAKE_KEY, replace=True)
    assert path.read_bytes() == (
        b"# keep this comment\r\nOTHER=value\r\n"
        + f"DEEPSEEK_API_KEY={FAKE_KEY}\r\n".encode()
        + b"LAST=unchanged"
    )
    assert client.load_api_key(tmp_path) == FAKE_KEY
    if os.name == "posix":
        assert path.stat().st_mode & 0o777 == 0o600
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize("content", [None, "# existing comment", "OTHER=value\n"])
def test_replace_can_add_missing_key(tmp_path, content):
    if content is not None:
        (tmp_path / ".env").write_text(content, encoding="utf-8")
    path = client.save_api_key(tmp_path, FAKE_KEY, replace=True)
    assert client.load_api_key(tmp_path) == FAKE_KEY
    if content:
        assert path.read_text(encoding="utf-8").startswith(content)


def test_failed_replace_preserves_old_key_and_cleans_temporary(tmp_path, monkeypatch):
    path = client.save_api_key(tmp_path, FAKE_KEY)
    previous = path.read_bytes()

    def fail_replace(*args):
        raise OSError("fictional disk failure")

    monkeypatch.setattr(client.os, "replace", fail_replace)
    with pytest.raises(OSError):
        client.save_api_key(tmp_path, "fictional-new-key", replace=True)
    assert path.read_bytes() == previous
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize("kind", ["symlink", "invalid_utf8", "invalid_key"])
def test_unsafe_replace_keeps_original(tmp_path, kind):
    path = tmp_path / ".env"
    key = FAKE_KEY
    if kind == "symlink":
        target = tmp_path / "other-config"
        target.write_text("preserve", encoding="utf-8")
        path.symlink_to(target)
    elif kind == "invalid_utf8":
        path.write_bytes(b"\xff")
    else:
        path.write_text("DEEPSEEK_API_KEY=previous", encoding="utf-8")
        key = ""
    before = path.read_bytes()
    with pytest.raises(client.DeepSeekConnectionError):
        client.save_api_key(tmp_path, key, replace=True)
    assert path.read_bytes() == before


def test_replace_command_never_prints_either_key(tmp_path, monkeypatch, capsys):
    client.save_api_key(tmp_path, FAKE_KEY)
    new_key = "fictional-new-key"
    monkeypatch.setattr(setup_deepseek, "ROOT", tmp_path)
    monkeypatch.setattr(setup_deepseek.sys, "stdin", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(setup_deepseek.getpass, "getpass", lambda prompt: new_key)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fictional-old-environment-key")
    assert setup_deepseek.main(["--replace"]) == 0
    output = capsys.readouterr().out
    assert "已更换" in output and "unset DEEPSEEK_API_KEY" in output
    assert all(key not in output for key in (FAKE_KEY, new_key, "fictional-old-environment-key"))
    monkeypatch.delenv("DEEPSEEK_API_KEY")
    assert client.load_api_key(tmp_path) == new_key


def test_cancelling_replacement_keeps_previous_key(tmp_path, monkeypatch, capsys):
    path = client.save_api_key(tmp_path, FAKE_KEY)
    before = path.read_bytes()
    monkeypatch.setattr(setup_deepseek, "ROOT", tmp_path)
    monkeypatch.setattr(setup_deepseek.sys, "stdin", SimpleNamespace(isatty=lambda: True))

    def cancel(prompt):
        raise KeyboardInterrupt

    monkeypatch.setattr(setup_deepseek.getpass, "getpass", cancel)
    assert setup_deepseek.main(["--replace"]) == 2
    assert path.read_bytes() == before
    assert FAKE_KEY not in capsys.readouterr().out
