import json

import pytest

from cutting_layout.channel_batch_job import load_channel_batch_job, parse_channel_batch_job


def test_loads_custom_stock_lengths(tmp_path):
    path = tmp_path / "job.json"
    path.write_text(
        json.dumps({"demand": {"1200": 2}, "stock_lengths_mm": [4000, 5000]}),
        encoding="utf-8",
    )
    job = load_channel_batch_job(path)
    assert job.demand[1200] == 2
    assert job.stock_lengths == (4000, 5000)


@pytest.mark.parametrize(
    "payload",
    [
        {"demand": {"1200": 0}},
        {"demand": {"5000": 1}, "stock_lengths_mm": [4000]},
        {"demand": {"1200": 1}, "stock_lengths_mm": []},
    ],
)
def test_rejects_invalid_jobs(tmp_path, payload):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError):
        load_channel_batch_job(path)


@pytest.mark.parametrize("payload", [
    [],
    {"demand": {}},
    {"demand": {"not-a-length": 1}},
    {"demand": {"1200": 1}, "kerf_mm": True},
    {"demand": {"1200": 1}, "max_stack": 101},
    {"demand": {"1200": 1}, "min_bars": False},
])
def test_file_and_memory_parsers_reject_same_invalid_data(tmp_path, payload):
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError) as memory_error:
        parse_channel_batch_job(payload)
    with pytest.raises(ValueError) as file_error:
        load_channel_batch_job(path)
    assert str(file_error.value) == str(memory_error.value)


@pytest.mark.parametrize("contents", [None, "{broken json"])
def test_unreadable_order_is_a_clear_input_error(tmp_path, contents):
    path = tmp_path / "order.json"
    if contents is not None:
        path.write_text(contents, encoding="utf-8")
    with pytest.raises(ValueError, match="cannot read job JSON"):
        load_channel_batch_job(path)
