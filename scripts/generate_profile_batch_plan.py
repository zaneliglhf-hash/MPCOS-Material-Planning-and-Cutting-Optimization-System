from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path

from cutting_layout.channel_batch import validate_batch_plan
from cutting_layout.channel_batch_optimizer import improve_channel_batch_plan, optimize_channel_batches
from cutting_layout.channel_batch_rendering import render_channel_batch_pages, write_channel_batch_csv


def _capacity(width: int, height: int, clamp_width: int, clamp_height: int) -> int:
    return max(
        (clamp_width // width) * (clamp_height // height),
        (clamp_width // height) * (clamp_height // width),
    )


def _load(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("profiles"), list):
        raise ValueError("job must contain a profiles list")
    kerf = payload.get("kerf_mm", 3)
    stock_length = payload.get("stock_length_mm", 6000)
    machines = payload.get("machines", [])
    if not machines or any(not all(key in machine for key in ("name", "clamp_width_mm", "clamp_height_mm")) for machine in machines):
        raise ValueError("machines must define name, clamp_width_mm, clamp_height_mm")
    return {"kerf": kerf, "stock_length": stock_length, "machines": machines, "profiles": payload["profiles"]}


def generate(job_path: Path, output_dir: Path, *, time_limit_seconds: float = 30.0) -> Path:
    job = _load(job_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    summaries = []
    for profile in job["profiles"]:
        name = str(profile["name"])
        width, height = int(profile["width_mm"]), int(profile["height_mm"])
        demand = Counter({int(length): int(count) for length, count in profile["demand"].items()})
        capacities = {
            machine["name"]: _capacity(width, height, int(machine["clamp_width_mm"]), int(machine["clamp_height_mm"]))
            for machine in job["machines"]
        }
        max_stack = max(capacities.values())
        plan = optimize_channel_batches(demand, kerf=job["kerf"], max_stack=max_stack,
            min_bars=1, max_bars=sum(demand.values()), stock_lengths=(job["stock_length"],),
            time_limit_seconds=time_limit_seconds)
        plan = improve_channel_batch_plan(demand, plan, min_bars=1, max_bars=sum(demand.values()),
            max_stack=max_stack, stock_lengths=(job["stock_length"],), time_limit_seconds=time_limit_seconds)
        validate_batch_plan(plan, demand)
        profile_dir = output_dir / name
        profile_dir.mkdir(parents=True, exist_ok=True)
        render_channel_batch_pages(plan, profile_dir, f"{name}方管下料 / {name} tube",
            baseline_batches=0, baseline_strokes=0)
        write_channel_batch_csv(plan, profile_dir / "cutting.csv")
        batches = []
        for number, batch in enumerate(plan.batches, 1):
            machine = next((machine_name for machine_name, capacity in sorted(capacities.items(), key=lambda item: item[1]) if batch.multiplicity <= capacity), max(capacities, key=capacities.get))
            batches.append({"batch": number, "machine": machine, "bars": batch.multiplicity,
                "stock_length_mm": batch.stock_length, "cuts_mm": list(batch.pieces_per_bar),
                "saw_strokes": batch.cuts, "offcut_per_bar_mm": batch.offcut_per_bar})
        summary = {"profile": name, "size_mm": [width, height], "capacities": capacities,
            "batch_count": plan.batch_count, "bar_count": plan.bar_count, "saw_strokes": plan.saw_strokes,
            "offcut_mm": plan.total_offcut, "utilization_percent": round(plan.utilization_percent, 4), "batches": batches}
        (profile_dir / "cutting.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        summaries.append(summary)
    summary_path = output_dir / "profile-cutting-summary.json"
    summary_path.write_text(json.dumps({"stock_length_mm": job["stock_length"], "kerf_mm": job["kerf"], "profiles": summaries}, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate batch cutting plans for square/rectangular tubes")
    parser.add_argument("job", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--time-limit", type=float, default=30.0)
    args = parser.parse_args()
    try:
        print(generate(args.job, args.output, time_limit_seconds=args.time_limit))
    except (OSError, ValueError, RuntimeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
