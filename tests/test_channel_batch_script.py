import json

from scripts.generate_channel_batch_plan import generate


def test_generate_accepts_custom_stock_lengths(tmp_path):
    job_path = tmp_path / "job.json"
    job_path.write_text(
        json.dumps(
            {
                "demand": {"1200": 6, "1800": 6},
                "stock_lengths_mm": [4000, 5000],
                "max_stack": 6,
                "min_bars": 1,
                "max_bars": 20,
            }
        ),
        encoding="utf-8",
    )
    plan, pages, csv_path, json_path = generate(
        job_path, tmp_path / "out", time_limit_seconds=2
    )
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["summary"]["stock_lengths_mm"] == [4000, 5000]
    assert payload["summary"]["finished_length_mm"] == 18000
    assert plan.bar_count == 6
    assert pages and csv_path.exists()
