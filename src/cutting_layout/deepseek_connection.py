"""Local credentials and bounded DeepSeek requests for the beginner lessons."""

from __future__ import annotations

import http.client
import json
import os
from pathlib import Path
import tempfile


MODEL = "deepseek-flash"
API_HOST = "api.deepseek.com"
_MAX_RESPONSE_BYTES = 64 * 1024


class DeepSeekConnectionError(RuntimeError):
    """A user-facing error that never contains credentials or raw HTTP bodies."""


def _validate_key(value: str) -> str:
    key = value.strip()
    if not key or any(ord(char) < 33 or ord(char) > 126 for char in key):
        raise DeepSeekConnectionError("密钥为空或含有不合法字符，请重新复制完整 API Key。")
    return key


def save_api_key(project_root: Path, value: str, *, replace: bool = False) -> Path:
    """Create a private config, or atomically replace only its key setting."""
    key = _validate_key(value)
    path = project_root / ".env"
    if not replace:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(f"DEEPSEEK_API_KEY={key}\n")
        return path

    if path.is_symlink():
        raise DeepSeekConnectionError(".env 是链接文件，未更改。请使用项目内的普通配置文件。")
    try:
        content = path.read_bytes().decode("utf-8")
    except FileNotFoundError:
        content = ""
    except UnicodeError:
        raise DeepSeekConnectionError(".env 不是有效的 UTF-8 文本，原文件已保留。") from None

    lines = []
    replaced = False
    for line in content.splitlines(keepends=True):
        name, separator, _ = line.partition("=")
        if separator and name.strip() == "DEEPSEEK_API_KEY":
            if not replaced:
                ending = "\r\n" if line.endswith("\r\n") else "\n"
                lines.append(f"DEEPSEEK_API_KEY={key}{ending}")
                replaced = True
            # Remove duplicate key settings while keeping unrelated lines.
        else:
            lines.append(line)
    if not replaced:
        if content and not content.endswith(("\n", "\r")):
            lines.append("\n")
        lines.append(f"DEEPSEEK_API_KEY={key}\n")

    descriptor, temporary_name = tempfile.mkstemp(prefix=".env.", suffix=".tmp", dir=project_root)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write("".join(lines))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


def load_api_key(project_root: Path) -> str:
    """Prefer the environment, otherwise read the one supported .env field.

    The local format is plain NAME=value; it is never executed as shell code.
    No file contents or credential values are included in errors.
    """
    key = os.environ.get("DEEPSEEK_API_KEY")
    if key:
        return _validate_key(key)
    try:
        content = (project_root / ".env").read_text(encoding="utf-8")
    except FileNotFoundError:
        raise DeepSeekConnectionError(
            "尚未配置密钥。请先运行：.venv/bin/python scripts/setup_deepseek.py"
        ) from None
    except (OSError, UnicodeError):
        raise DeepSeekConnectionError("无法读取本地配置文件，请检查 .env 的权限和格式。") from None

    values = []
    for line in content.splitlines():
        name, separator, value = line.partition("=")
        if separator and name.strip() == "DEEPSEEK_API_KEY":
            values.append(value.strip())
    if len(values) != 1:
        raise DeepSeekConnectionError(".env 必须且只能包含一项 DEEPSEEK_API_KEY 配置。")
    return _validate_key(values[0])


def _redact_response(value, key: str):
    if isinstance(value, str):
        return value.replace(key, "[密钥已隐藏]")
    if isinstance(value, list):
        return [_redact_response(item, key) for item in value]
    if isinstance(value, dict):
        return {name: _redact_response(item, key) for name, item in value.items()}
    return value


def _request_completion(project_root: Path, payload: dict) -> dict:
    """Use the fixed official endpoint once, with no automatic retries."""
    key = load_api_key(project_root)
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    # HTTPSConnection verifies TLS and does not follow redirects. Credentials
    # are sent only to this fixed official host, not a model-supplied URL.
    connection = http.client.HTTPSConnection(API_HOST, timeout=30)
    try:
        connection.request("POST", "/chat/completions", body=body, headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        })
        response = connection.getresponse()
        if response.status != 200:
            messages = {
                400: "请求格式错误，请把错误码 400 告诉我。",
                401: "密钥认证失败（401）。请检查密钥是否完整、有效。",
                402: "账户余额不足（402）。请先到 DeepSeek 平台查看可用余额。",
                422: "请求参数错误，请把错误码 422 告诉我。",
                429: "请求过于频繁（429），请稍后再试。",
                500: "DeepSeek 服务暂时出错（500），请稍后再试。",
                503: "DeepSeek 服务繁忙（503），请稍后再试。",
            }
            # Do not print the server body: it might contain sensitive values.
            raise DeepSeekConnectionError(messages.get(
                response.status, f"服务返回 HTTP {response.status}，未继续请求。",
            ))
        raw = response.read(_MAX_RESPONSE_BYTES + 1)
    except (OSError, http.client.HTTPException):
        raise DeepSeekConnectionError(
            "网络连接失败或超时。请检查网络后再试；超时不一定代表服务端未计费。"
        ) from None
    finally:
        connection.close()

    if len(raw) > _MAX_RESPONSE_BYTES:
        raise DeepSeekConnectionError("服务返回的数据过大，本次请求已停止读取。")
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("expected response object")
        return _redact_response(data, key)
    except (ValueError, UnicodeError, RecursionError):
        raise DeepSeekConnectionError("服务返回的数据格式不正确，请把此提示告诉我。") from None


def probe_connection(project_root: Path) -> dict:
    """Send one short greeting to DeepSeek. No retries, redirects, or orders."""
    payload = _request_completion(project_root, {
        "model": MODEL,
        "messages": [{"role": "user", "content": "你好，请只回复：连接成功"}],
        "thinking": {"type": "disabled"},
        "max_tokens": 64,
        "stream": False,
    })
    try:
        reply = payload["choices"][0]["message"]["content"]
        if not isinstance(reply, str) or not reply.strip():
            raise ValueError("missing text reply")
    except (ValueError, KeyError, IndexError, TypeError, UnicodeError):
        raise DeepSeekConnectionError("服务未返回可用的文字回复，请把此提示告诉我。") from None
    usage = payload.get("usage")
    usage = usage if isinstance(usage, dict) else {}
    return {
        "status": "connected",
        "model": MODEL,
        "reply": reply,
        "usage": {
            name: value for name in ("prompt_tokens", "completion_tokens")
            if isinstance(value := usage.get(name), int) and not isinstance(value, bool)
        },
    }


def chat_completion(
    project_root: Path,
    messages: list[dict],
    tools: list[dict],
    *,
    allow_tools: bool = True,
) -> dict:
    """Return a validated assistant message for the bounded teaching agent."""
    payload = _request_completion(project_root, {
        "model": MODEL,
        "messages": messages,
        "tools": tools,
        "tool_choice": "auto" if allow_tools else "none",
        "thinking": {"type": "disabled"},
        "max_tokens": 800,
        "stream": False,
    })
    try:
        choice = payload["choices"][0]
        reason = choice["finish_reason"]
        message = choice["message"]
        if reason not in {"stop", "tool_calls"}:
            raise ValueError("incomplete response")
        if message["role"] != "assistant":
            raise ValueError("invalid response role")
        content = message.get("content")
        calls = message.get("tool_calls") or []
        if content is not None and not isinstance(content, str):
            raise ValueError("invalid text")
        if not isinstance(calls, list) or len(calls) > 1:
            raise ValueError("only one tool call per message is supported")
        if calls and not allow_tools:
            raise ValueError("unexpected additional tool call")
        if bool(calls) != (reason == "tool_calls"):
            raise ValueError("inconsistent finish reason")
        clean = {"role": "assistant", "content": content}
        if calls:
            call = calls[0]
            function = call["function"]
            fields = (call["id"], function["name"], function["arguments"])
            if call["type"] != "function" or any(not isinstance(item, str) or not item for item in fields):
                raise ValueError("invalid tool call")
            clean["tool_calls"] = [{
                "id": call["id"], "type": "function",
                "function": {"name": function["name"], "arguments": function["arguments"]},
            }]
        elif not content or not content.strip():
            raise ValueError("empty answer")
        return clean
    except (KeyError, IndexError, TypeError, ValueError):
        raise DeepSeekConnectionError(
            "模型回复不完整或工具调用格式不正确，未执行该回复中的新操作。请简化需求后重试。"
        ) from None
