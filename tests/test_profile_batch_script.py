import json

from scripts.generate_profile_batch_plan import _capacity, generate


def test_capacity_uses_both_orientations():
    assert _capacity(120, 80, 300, 350) == 8
    assert _capacity(100, 50, 300, 350) == 21


def test_profile_job_writes_machine_assignment(tmp_path):
    job = {
        "stock_length_mm": 6000,
        "kerf_mm": 3,
        "machines": [
            {"name": "small", "clamp_width_mm": 300, "clamp_height_mm": 350},
            {"name": "large", "clamp_width_mm": 400, "clamp_height_mm": 500},
        ],
        "profiles": [
            {"name": "100x100x4", "width_mm": 100, "height_mm": 100,
             "demand": {"2080": 2}},
        ],
    }
    job_path = tmp_path / "job.json"
    job_path.write_text(json.dumps(job), encoding="utf-8")
    summary_path = generate(job_path, tmp_path / "out", time_limit_seconds=2)
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert payload["profiles"][0]["capacities"] == {"small": 9, "large": 20}
    assert payload["profiles"][0]["batches"][0]["machine"] == "small"
