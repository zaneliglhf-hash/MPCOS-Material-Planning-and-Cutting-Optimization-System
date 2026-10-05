from copy import deepcopy
import json
from pathlib import Path

import pytest

from cutting_layout import cutting_agent, deepseek_connection
from cutting_layout.cutting_agent import CuttingAgent, TOOL_DEFINITION
from cutting_layout.deepseek_connection import DeepSeekConnectionError, chat_completion
from examples import agent_lesson_04


JOB = {
    "demand": {"1200": 6, "1800": 6},
    "stock_lengths_mm": [4000], "kerf_mm": 3, "max_stack": 6,
    "min_bars": 1, "max_bars": 12,
    "title": "Fictional conversation test",
}


@pytest.fixture(autouse=True)
def no_live_api(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Conversation tests must not access the live API")
    monkeypatch.setattr(deepseek_connection.http.client, "HTTPSConnection", forbidden)


def answer(text):
    return {"role": "assistant", "content": text}


def tool_call(job, *, name="plan_cutting", arguments=None, call_id="call-test"):
    return {
        "role": "assistant", "content": None,
        "tool_calls": [{
            "id": call_id, "type": "function",
            "function": {"name": name, "arguments": arguments if arguments is not None else json.dumps(job)},
        }],
    }


class FakeModel:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []

    def __call__(self, root, messages, tools, *, allow_tools):
        self.requests.append({"messages": deepcopy(messages), "allow_tools": allow_tools})
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return deepcopy(response)


def test_clarification_then_real_calculation_with_conversation_history(tmp_path):
    model = FakeModel([
        tool_call({"demand": JOB["demand"]}, call_id="missing"),
        answer("请补充原料长度、锯缝和已确认的最大叠切根数。"),
        tool_call(JOB, call_id="ready"), answer("计算完成，等待人工复核。"),
    ])
    agent = CuttingAgent(tmp_path, complete=model)
    first = agent.send("虚构订单，同规格同材质槽钢，1200 毫米和 1800 毫米各 6 件，帮我下料。")
    assert first["tool_result"]["status"] == "needs_input"
    assert not (tmp_path / "output").exists()
    second = agent.send("原料 4000 毫米，锯缝 3 毫米，确认最大叠切 6 根。")
    result = second["tool_result"]
    assert result["status"] == "success" and result["review_status"] == "pending"
    assert result["summary"]["bar_count"] == 6
    assert result["summary"]["batch_count"] == 1
    assert result["summary"]["saw_strokes"] == 2
    assert Path(result["files"]["json"]).is_file()
    assert all(Path(path).is_file() for path in result["files"]["images"])
    assert [request["allow_tools"] for request in model.requests] == [True, False, True, False]
    assert any(message["role"] == "user" and "各 6 件" in message["content"]
               for message in model.requests[2]["messages"])
    feedback = json.loads(model.requests[-1]["messages"][-1]["content"])
    assert feedback["summary"]["bar_count"] == 6
    assert "files" not in feedback and str(tmp_path) not in json.dumps(feedback)
    assert model.requests[-1]["messages"][-1]["tool_call_id"] == "ready"
    assert agent.api_calls == 4


def test_ordinary_question_does_not_invoke_tool(tmp_path):
    model = FakeModel([answer("锯缝是切割时损耗的宽度。")])
    agent = CuttingAgent(tmp_path, complete=model)
    result = agent.send("什么是锯缝？")
    assert result["tool_result"] is None and agent.api_calls == 1
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("call", [
    tool_call({}, name="run_shell", arguments='{"command": "not permitted"}'),
    tool_call({}, arguments="invalid JSON"),
    tool_call({}, arguments='{"demand": {"1200": 1, "1200": 2}}'),
    tool_call({**JOB, "output_root": "/other-location"}),
    tool_call({**JOB, "review_status": "approved"}),
    tool_call({**JOB, "demand": {"1200": 1, "1200\n": 2}}),
    tool_call([]),
])
def test_bad_or_unauthorized_calls_do_not_execute(tmp_path, call):
    model = FakeModel([call, answer("请检查参数。")])
    result = CuttingAgent(tmp_path, complete=model).send("测试非法调用")
    assert result["tool_result"]["status"] == "invalid_input"
    assert not (tmp_path / "output").exists()


def test_explanation_failure_preserves_generated_files(tmp_path):
    model = FakeModel([tool_call(JOB), DeepSeekConnectionError("测试网络失败")])
    agent = CuttingAgent(tmp_path, complete=model)
    turn = agent.send("虚构完整订单")
    assert turn["status"] == "error"
    assert turn["tool_result"]["status"] == "success"
    assert Path(turn["tool_result"]["files"]["json"]).is_file()
    assert agent.messages[-1]["role"] == "tool"
    assert agent.messages[-2]["tool_calls"][0]["id"] == agent.messages[-1]["tool_call_id"]


def test_first_request_failure_restores_history_but_counts_attempt(tmp_path):
    agent = CuttingAgent(tmp_path, complete=FakeModel([DeepSeekConnectionError("测试网络失败")]))
    before = deepcopy(agent.messages)
    assert agent.send("你好")["status"] == "error"
    assert agent.messages == before and agent.api_calls == 1


def test_tool_execution_error_does_not_send_local_paths_to_model(tmp_path, monkeypatch):
    local_error = {"status": "execution_error", "message": f"cannot write {tmp_path}/private-file"}
    monkeypatch.setattr(cutting_agent, "plan_cutting", lambda *a, **k: local_error)
    model = FakeModel([tool_call(JOB), answer("请检查本地导出错误。")])
    result = CuttingAgent(tmp_path, complete=model).send("测试")
    assert result["tool_result"] == local_error
    assert str(tmp_path) not in json.dumps(model.requests[-1]["messages"])


def test_limits_stop_before_network_and_reset_keeps_call_budget(tmp_path):
    agent = CuttingAgent(tmp_path, complete=FakeModel([]))
    assert agent.send("")["status"] == "error"
    assert agent.send("长" * 2001)["status"] == "error"
    agent.messages.append(answer("长" * 20000))
    assert agent.send("你好")["status"] == "limit"
    agent.api_calls = 19
    agent.reset()
    assert len(agent.messages) == 1 and agent.api_calls == 19
    assert agent.send("你好")["status"] == "limit"


def test_client_posts_tool_schema_and_preserves_call_id(tmp_path, monkeypatch):
    requests = []
    message = tool_call(JOB, call_id="call-123")

    def fake_request(root, payload):
        requests.append(payload)
        return {"choices": [{"finish_reason": "tool_calls", "message": message}]}

    monkeypatch.setattr(deepseek_connection, "_request_completion", fake_request)
    result = chat_completion(tmp_path, [answer("测试")], [TOOL_DEFINITION])
    assert result == message
    assert requests[0]["thinking"] == {"type": "disabled"}
    assert requests[0]["tool_choice"] == "auto"
    assert requests[0]["max_tokens"] == 800
    assert requests[0]["tools"][0]["function"]["name"] == "plan_cutting"
    assert "output_root" not in requests[0]["tools"][0]["function"]["parameters"]["properties"]


@pytest.mark.parametrize("reason,message,allow", [
    ("length", tool_call(JOB), True),
    ("content_filter", answer(""), True),
    ("stop", {"role": "system", "content": "bad role"}, True),
    ("stop", {"role": "assistant", "content": {}}, True),
    ("stop", answer(""), True),
    ("tool_calls", tool_call(JOB), False),
    ("stop", tool_call(JOB), True),
    ("tool_calls", answer("missing call"), True),
    ("tool_calls", {**tool_call(JOB), "tool_calls": [*tool_call(JOB)["tool_calls"]] * 2}, True),
    ("tool_calls", {"role": "assistant", "content": None, "tool_calls": [{"id": "bad"}]}, True),
    ("tool_calls", tool_call({}, arguments=""), True),
])
def test_invalid_model_output_is_rejected_before_dispatch(tmp_path, monkeypatch, reason, message, allow):
    monkeypatch.setattr(deepseek_connection, "_request_completion", lambda *a, **k: {
        "choices": [{"finish_reason": reason, "message": message}],
    })
    with pytest.raises(DeepSeekConnectionError):
        chat_completion(tmp_path, [], [TOOL_DEFINITION], allow_tools=allow)


def test_final_explanation_disables_tools(tmp_path, monkeypatch):
    def fake_request(root, payload):
        assert payload["tool_choice"] == "none"
        return {"choices": [{"finish_reason": "stop", "message": answer("请人工复核。")}]}
    monkeypatch.setattr(deepseek_connection, "_request_completion", fake_request)
    assert chat_completion(tmp_path, [], [TOOL_DEFINITION], allow_tools=False)["content"] == "请人工复核。"


def test_terminal_shows_computed_values_and_files_independently(capsys):
    result = {
        "status": "success", "run_id": "00000000000000000000000000000001", "summary": {
            "bar_count": 6, "batch_count": 1, "saw_strokes": 2,
            "offcut_mm": 5964, "utilization_percent": 75,
        },
        "files": {"input": "input.json", "csv": "result.csv", "json": "result.json", "images": ["page.png"]},
    }
    agent_lesson_04.show_tool_result(result)
    output = capsys.readouterr().out
    assert "工具实算：原料 6 根" in output
    assert "等待人工复核" in output and "page.png" in output and "result.json" in output
    agent_lesson_04.show_tool_result(None)
    assert "本轮未运行" in capsys.readouterr().out
    agent_lesson_04.show_tool_result({"status": "needs_input", "message": "请补充锯缝"})
    assert "请补充锯缝" in capsys.readouterr().out
