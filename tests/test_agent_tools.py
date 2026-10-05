import json
from collections import Counter
from pathlib import Path

import pytest

from cutting_layout import channel_batch_pipeline
from cutting_layout.agent_tools import CHANNEL_JOB_SCHEMA, plan_cutting
from cutting_layout.channel_batch import ChannelBatch, ChannelBatchPlan
from cutting_layout.channel_batch_job import parse_channel_batch_job
from jsonschema import Draft202012Validator


@pytest.fixture
def tool_job():
    return {
        "demand": {"1200": 6, "1800": 6},
        "stock_lengths_mm": [4000],
        "kerf_mm": 3,
        "max_stack": 6,
        "min_bars": 1,
        "max_bars": 12,
        "title": "Fictional tool test",
    }


@pytest.mark.parametrize("field", ["demand", "stock_lengths_mm", "kerf_mm", "max_stack"])
@pytest.mark.parametrize("set_null", [False, True])
def test_missing_process_parameters_never_use_defaults(tool_job, tmp_path, field, set_null):
    if set_null:
        tool_job[field] = None
    else:
        del tool_job[field]
    root = tmp_path / "plans"
    result = plan_cutting(tool_job, output_root=root)
    assert result["status"] == "needs_input"
    assert result["missing_fields"] == [field]
    assert not root.exists()


@pytest.mark.parametrize("updates", [
    {"demand": {"1200": 0}},
    {"demand": {"1200": True}},
    {"demand": {"1200.5": 1}},
    {"demand": {1200: 1}},
    {"stock_lengths_mm": []},
    {"stock_lengths_mm": [1000]},
    {"kerf_mm": -1},
    {"max_stack": True},
    {"max_stack": 101},
    {"min_bars": 10, "max_bars": 1},
    {"output_root": "../elsewhere"},
    {"review_status": "approved"},
])
def test_invalid_input_produces_no_plan(tool_job, tmp_path, updates):
    result = plan_cutting({**tool_job, **updates}, output_root=tmp_path / "plans")
    assert result["status"] == "invalid_input"
    assert "files" not in result
    assert not (tmp_path / "plans").exists()


def test_non_object_input_is_reported(tmp_path):
    assert plan_cutting([], output_root=tmp_path)["status"] == "invalid_input"


def test_success_preserves_input_files_and_previous_run(tool_job, tmp_path):
    Draft202012Validator.check_schema(CHANNEL_JOB_SCHEMA)
    first = plan_cutting(tool_job, output_root=tmp_path)
    assert first["status"] == "success"
    assert first["review_status"] == "pending"
    assert "人工复核" in first["message"]
    json.dumps(first, ensure_ascii=False, allow_nan=False)

    files = first["files"]
    paths = [Path(files[key]) for key in ("input", "json", "csv")]
    paths.extend(Path(path) for path in files["images"])
    assert all(path.is_file() and path.is_relative_to(tmp_path) for path in paths)
    before = {path: path.read_bytes() for path in paths}
    archived = json.loads(Path(files["input"]).read_text(encoding="utf-8"))
    assert parse_channel_batch_job(archived) == parse_channel_batch_job(tool_job)
    exported = json.loads(Path(files["json"]).read_text(encoding="utf-8"))
    assert exported["batches"] == first["batches"]

    # Independently verify every required piece and total material accounting.
    produced = Counter()
    for batch in first["batches"]:
        for length in batch["cuts_mm"]:
            produced[length] += batch["bars"]
        assert batch["bars"] <= tool_job["max_stack"]
        assert batch["used_per_bar_mm"] <= batch["stock_length_mm"]
    assert produced == Counter({1200: 6, 1800: 6})
    summary = first["summary"]
    assert summary["total_stock_mm"] == (
        summary["finished_length_mm"] + summary["kerf_total_mm"] + summary["offcut_mm"]
    )
    assert summary["bar_count"] == 6

    second = plan_cutting(tool_job, output_root=tmp_path)
    assert second["status"] == "success"
    assert second["run_id"] != first["run_id"]
    assert all(path.read_bytes() == content for path, content in before.items())
    assert sorted(path.name for path in tmp_path.iterdir()) == sorted([
        first["run_id"], second["run_id"],
    ])


def test_solver_failure_is_not_reported_as_success(tool_job, tmp_path, monkeypatch):
    def fail_solver(*args, **kwargs):
        raise RuntimeError("test solver failure")

    monkeypatch.setattr(channel_batch_pipeline, "optimize_channel_batches", fail_solver)
    result = plan_cutting(tool_job, output_root=tmp_path)
    assert result["status"] == "execution_error"
    assert "files" not in result
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("limit", [0, -1, True, float("inf"), float("nan"), "2"])
def test_invalid_host_time_limit_does_not_start_solver(tool_job, tmp_path, limit):
    result = plan_cutting(tool_job, output_root=tmp_path, time_limit_seconds=limit)
    assert result["status"] == "execution_error"
    assert list(tmp_path.iterdir()) == []


def test_failed_export_preserves_existing_directory(tool_job, tmp_path, monkeypatch):
    target = tmp_path / "existing"
    target.mkdir()
    (target / "previous.txt").write_text("keep this plan", encoding="utf-8")

    def fail_csv(*args, **kwargs):
        raise OSError("test disk failure")

    monkeypatch.setattr(channel_batch_pipeline, "write_channel_batch_csv", fail_csv)
    with pytest.raises(OSError, match="test disk failure"):
        channel_batch_pipeline.generate_channel_batch_plan(
            parse_channel_batch_job(tool_job), target, time_limit_seconds=2,
        )
    assert (target / "previous.txt").read_text(encoding="utf-8") == "keep this plan"
    assert list(target.iterdir()) == [target / "previous.txt"]
    assert list(tmp_path.iterdir()) == [target]


@pytest.mark.parametrize("failure", ["quantity", "bar_bound", "stack_bound"])
def test_invalid_solver_output_cannot_be_exported(tool_job, tmp_path, monkeypatch, failure):
    if failure == "quantity":
        bad_plan = ChannelBatchPlan((ChannelBatch(4000, 1, (1200,), kerf=3),), kerf=3)
        expected_error = "quantity mismatch"
    else:
        bad_plan = ChannelBatchPlan((ChannelBatch(4000, 6, (1200, 1800), kerf=3),), kerf=3)
        if failure == "bar_bound":
            tool_job["max_bars"] = 5
            expected_error = "bar range"
        else:
            tool_job["max_stack"] = 5
            expected_error = "stack limit"

    monkeypatch.setattr(channel_batch_pipeline, "optimize_channel_batches", lambda *a, **k: bad_plan)
    monkeypatch.setattr(channel_batch_pipeline, "improve_channel_batch_plan", lambda *a, **k: bad_plan)
    result = plan_cutting(tool_job, output_root=tmp_path)
    assert result["status"] == "execution_error"
    assert expected_error in result["message"]
    assert list(tmp_path.iterdir()) == []
