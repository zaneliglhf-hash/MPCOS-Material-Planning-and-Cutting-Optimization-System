import json
import os

import pytest

from cutting_layout import deepseek_connection
from cutting_layout.plan_history import list_plan_history, read_plan_details
from examples import agent_lesson_04


def save_record(root, number, *, bars=6, modified=1700000000):
    folder = root / f"{number:032x}"
    folder.mkdir(parents=True)
    path = folder / "channel-batch-cutting.json"
    path.write_text(json.dumps({"summary": {
        "bar_count": bars, "batch_count": bars // 6, "saw_strokes": bars // 3,
        "offcut_mm": bars * 994, "utilization_percent": 75.0,
    }}), encoding="utf-8")
    os.utime(path, (modified, modified))
    return path


SAVED_JOB = {
    "title": "教学订单 A", "demand": {"1200": 6, "1800": 6},
    "stock_lengths_mm": [4000], "kerf_mm": 3, "max_stack": 6,
}


def save_job(result_path, payload):
    path = result_path.parent / "input.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def no_live_api(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("History must not access the API")
    monkeypatch.setattr(deepseek_connection.http.client, "HTTPSConnection", forbidden)


def test_read_existing_records_sorted_and_limited_without_modification(tmp_path):
    first = save_record(tmp_path, 1)
    latest = save_record(tmp_path, 2, bars=12, modified=1700000010)
    before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in (first, latest)}
    history = list_plan_history(tmp_path, limit=1)
    assert history["total"] == 2 and history["skipped"] == 0
    assert len(history["entries"]) == 1
    entry = history["entries"][0]
    assert entry["run_id"] == latest.parent.name
    assert entry["summary"]["bar_count"] == 12
    assert entry["directory"] == str(latest.parent)
    assert {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in before} == before


def test_search_keeps_same_name_plans_and_finds_older_records_before_limit(tmp_path):
    for number in range(1, 14):
        path = save_record(tmp_path, number, modified=1700000000 + number)
        title = "教学订单 A" if number in (1, 2) else "其他教学订单"
        (path.parent / "input.json").write_text(
            json.dumps({"title": title}, ensure_ascii=False), encoding="utf-8",
        )
    history = list_plan_history(tmp_path, query="教学订单a", limit=1)
    assert history["total"] == 13 and history["matched"] == 2
    assert [entry["run_id"] for entry in history["entries"]] == [f"{2:032x}"]
    all_matches = list_plan_history(tmp_path, query="教学订单 A")
    assert len(all_matches["entries"]) == 2
    assert list_plan_history(tmp_path, query="000D")["entries"][0]["run_id"] == f"{13:032x}"
    assert list_plan_history(tmp_path, query="没有这个名称")["entries"] == []


@pytest.mark.parametrize("bad", [
    "not-json", "[]", '{"summary": []}',
    '{"summary": {"bar_count": true}}',
    json.dumps({"summary": {"bar_count": 6, "batch_count": 1, "saw_strokes": 2,
                            "offcut_mm": 5964, "utilization_percent": float("nan")}}),
    " " * (1024 * 1024 + 1),
])
def test_bad_record_is_skipped_without_hiding_valid_record(tmp_path, bad):
    save_record(tmp_path, 1)
    broken = save_record(tmp_path, 2)
    broken.write_text(bad, encoding="utf-8")
    (tmp_path / "unrelated-directory").mkdir()
    history = list_plan_history(tmp_path)
    assert history["total"] == 1 and history["skipped"] == 1


def test_missing_and_linked_records_do_not_get_read(tmp_path):
    root = tmp_path / "history"
    external = save_record(tmp_path / "elsewhere", 1)
    root.mkdir()
    (root / f"{1:032x}").symlink_to(external.parent, target_is_directory=True)
    linked_file = root / f"{2:032x}"
    linked_file.mkdir()
    (linked_file / "channel-batch-cutting.json").symlink_to(external)
    (root / f"{3:032x}").mkdir()
    history = list_plan_history(root)
    assert history["entries"] == [] and history["skipped"] == 3


def test_empty_directory_errors_and_limit_validation(tmp_path, capsys):
    missing = tmp_path / "no-history-yet"
    assert agent_lesson_04.show_history(missing) == 0
    assert "暂无可读取" in capsys.readouterr().out
    assert not missing.exists()
    file = tmp_path / "not-a-directory"
    file.write_text("test", encoding="utf-8")
    assert agent_lesson_04.show_history(file) == 2
    assert "无法读取" in capsys.readouterr().out
    with pytest.raises(ValueError):
        list_plan_history(tmp_path, limit=0)


def test_history_flag_runs_without_key_or_agent(tmp_path, monkeypatch, capsys):
    root = tmp_path / "output" / "agent-lesson-04"
    save_record(root, 1)
    bad = save_record(root, 2)
    bad.write_text("broken", encoding="utf-8")
    monkeypatch.setattr(agent_lesson_04, "__file__", str(tmp_path / "examples" / "agent_lesson_04.py"))

    def forbidden(*args, **kwargs):
        pytest.fail("Standalone history must not load a key or create an agent")

    monkeypatch.setattr(agent_lesson_04, "load_api_key", forbidden)
    monkeypatch.setattr(agent_lesson_04, "CuttingAgent", forbidden)
    assert agent_lesson_04.main(["--history"]) == 0
    output = capsys.readouterr().out
    assert "原料 6 根" in output and "跳过 1 份" in output
    assert "须人工复核" in output and "不会恢复对话上下文" in output
    assert agent_lesson_04.main(["--history", "--query", f"{1:032x}"]) == 0
    output = capsys.readouterr().out
    assert "匹配 1 份" in output and "原料 6 根" in output
    assert agent_lesson_04.main(["--history", "--query", "不存在的教学订单"]) == 0
    assert "没有找到匹配的方案" in capsys.readouterr().out
    with pytest.raises(SystemExit) as exc:
        agent_lesson_04.main(["--query", "test"])
    assert exc.value.code == 2


def test_history_and_mistyped_commands_bypass_model_and_keep_context(tmp_path, monkeypatch, capsys):
    class LocalAgent:
        def __init__(self, root):
            pass

        def send(self, text):
            pytest.fail("Local commands must not be sent to the model")

        def reset(self):
            pytest.fail("History must not reset the conversation")

    monkeypatch.setattr(agent_lesson_04, "__file__", str(tmp_path / "examples" / "agent_lesson_04.py"))
    monkeypatch.setattr(agent_lesson_04, "CuttingAgent", LocalAgent)
    monkeypatch.setattr(agent_lesson_04, "load_api_key", lambda root: "unused-test-value")
    inputs = iter([
        "/history", "查看历史", "查找方案", "查找方案 教学订单 A",
        "/history 教学订单 A", "查看历史 教学订单 A", "帮助", "/histry",
        "查看方案", "/show", "查看方案 invalid-id", "/show " + "a" * 32, "/exit",
    ])
    monkeypatch.setattr("builtins.input", lambda prompt: next(inputs))
    assert agent_lesson_04.main([]) == 0
    output = capsys.readouterr().out
    assert "暂无可读取" in output and "未知命令" in output
    assert "请提供名称或编号" in output
    assert output.count("没有找到匹配的方案") == 3
    assert output.count("请提供完整方案编号") == 2
    assert "32 位方案编号" in output and "未找到这个方案" in output


def test_read_details_uses_saved_parameters_without_modifying_files(tmp_path):
    result_path = save_record(tmp_path, 0xAB)
    input_path = save_job(result_path, SAVED_JOB)
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in (result_path, input_path)}
    result = read_plan_details(tmp_path, result_path.parent.name.upper())
    assert result["status"] == "ok"
    assert result["entry"]["title"] == "教学订单 A"
    assert result["entry"]["summary"]["bar_count"] == 6
    assert result["parameters"] == {name: value for name, value in SAVED_JOB.items() if name != "title"}
    assert {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in before} == before


@pytest.mark.parametrize("run_id", ["../outside", "/tmp/outside", "a" * 31, "g" * 32])
def test_details_reject_bad_ids_before_file_access(tmp_path, monkeypatch, run_id):
    def forbidden(*args, **kwargs):
        pytest.fail("Invalid IDs must not lead to file reads")
    monkeypatch.setattr("cutting_layout.plan_history._read_entry", forbidden)
    assert read_plan_details(tmp_path, run_id)["status"] == "error"


@pytest.mark.parametrize("missing", ["demand", "stock_lengths_mm", "kerf_mm", "max_stack"])
def test_details_never_invents_missing_process_parameters(tmp_path, missing):
    path = save_record(tmp_path, 1)
    save_job(path, {name: value for name, value in SAVED_JOB.items() if name != missing})
    assert read_plan_details(tmp_path, path.parent.name)["status"] == "error"
    # A readable summary remains available even when the input is incomplete.
    assert list_plan_history(tmp_path)["total"] == 1


def test_details_handles_missing_broken_and_linked_inputs(tmp_path):
    root = tmp_path / "history"
    path = save_record(root, 1)
    assert read_plan_details(root, path.parent.name)["status"] == "error"
    input_path = save_job(path, SAVED_JOB)
    input_path.write_text("not-json", encoding="utf-8")
    assert read_plan_details(root, path.parent.name)["status"] == "error"
    path2 = save_record(root, 2)
    (path2.parent / "input.json").symlink_to(input_path)
    assert read_plan_details(root, path2.parent.name)["status"] == "error"
    (root / f"{3:032x}").symlink_to(path.parent, target_is_directory=True)
    assert read_plan_details(root, f"{3:032x}")["status"] == "error"


def test_details_flag_reads_without_credentials_or_agent(tmp_path, monkeypatch, capsys):
    path = save_record(tmp_path / "output" / "agent-lesson-04", 1)
    save_job(path, SAVED_JOB)
    monkeypatch.setattr(agent_lesson_04, "__file__", str(tmp_path / "examples" / "agent_lesson_04.py"))

    def forbidden(*args, **kwargs):
        pytest.fail("Details must not load credentials or initialize the agent")

    monkeypatch.setattr(agent_lesson_04, "load_api_key", forbidden)
    monkeypatch.setattr(agent_lesson_04, "CuttingAgent", forbidden)
    assert agent_lesson_04.main(["--show", path.parent.name]) == 0
    output = capsys.readouterr().out
    for expected in ("教学订单 A", "1200 mm × 6 件", "1800 mm × 6 件", "4000 mm", "锯缝：3 mm", "叠切上限：6 根"):
        assert expected in output
    assert "须由合格人员复核" in output and "未切换当前对话" in output
    assert agent_lesson_04.main(["--show", "a" * 32]) == 2
    with pytest.raises(SystemExit) as exc:
        agent_lesson_04.main(["--history", "--show", path.parent.name])
    assert exc.value.code == 2
