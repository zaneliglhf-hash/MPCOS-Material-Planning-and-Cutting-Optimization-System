import json

import pytest

from cutting_layout.channel_batch_job import load_channel_batch_job


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
