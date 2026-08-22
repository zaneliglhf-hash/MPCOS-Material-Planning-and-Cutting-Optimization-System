from __future__ import annotations

import argparse
import json
from pathlib import Path

from cutting_layout.channel_batch import ChannelBatchPlan, validate_batch_plan
from cutting_layout.channel_batch_job import load_channel_batch_job
from cutting_layout.channel_batch_optimizer import improve_channel_batch_plan, optimize_channel_batches
from cutting_layout.channel_batch_rendering import render_channel_batch_pages, write_channel_batch_csv

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_JOB = ROOT / "examples" / "channel_batch_job.json"
DEFAULT_OUTPUT = ROOT / "output" / "channel-cutting-plan-batched"


def _plan_payload(plan: ChannelBatchPlan, job) -> dict:
    return {"summary": {
        "solver_status": plan.solver_status, "batch_count": plan.batch_count,
        "bar_count": plan.bar_count, "saw_strokes": plan.saw_strokes,
        "procurement": dict(sorted(plan.procurement_counts.items())),
        "stock_lengths_mm": list(job.stock_lengths), "kerf_mm": job.kerf,
        "total_stock_mm": plan.total_stock, "finished_length_mm": plan.total_finished,
        "kerf_total_mm": plan.total_kerf, "offcut_mm": plan.total_offcut,
        "utilization_percent": round(plan.utilization_percent, 4),
        "baseline_batch_savings": max(0, job.baseline_batches - plan.batch_count),
        "baseline_stroke_savings": max(0, job.baseline_strokes - plan.saw_strokes),
    }, "batches": [{
        "batch": number, "stock_length_mm": batch.stock_length, "bars": batch.multiplicity,
        "cuts_mm": list(batch.pieces_per_bar), "saw_strokes": batch.cuts,
        "used_per_bar_mm": batch.used_per_bar, "offcut_per_bar_mm": batch.offcut_per_bar,
    } for number, batch in enumerate(plan.batches, 1)]}


def generate(job_path: Path = DEFAULT_JOB, output_dir: Path = DEFAULT_OUTPUT, *, time_limit_seconds: float = 300.0):
    job = load_channel_batch_job(job_path)
    plan = optimize_channel_batches(job.demand, kerf=job.kerf, max_stack=job.max_stack,
        min_bars=job.min_bars, max_bars=job.max_bars, stock_lengths=job.stock_lengths,
        time_limit_seconds=time_limit_seconds)
    plan = improve_channel_batch_plan(job.demand, plan, min_bars=job.min_bars,
        max_bars=job.max_bars, max_stack=job.max_stack, stock_lengths=job.stock_lengths,
        time_limit_seconds=time_limit_seconds)
    validate_batch_plan(plan, job.demand)
    if not job.min_bars <= plan.bar_count <= job.max_bars:
        raise RuntimeError("optimized plan is outside the requested bar range")
    if any(batch.multiplicity > job.max_stack for batch in plan.batches):
        raise RuntimeError("optimized plan exceeds the requested stack limit")
    output_dir.mkdir(parents=True, exist_ok=True)
    pages = render_channel_batch_pages(plan, output_dir, job.title,
        baseline_batches=job.baseline_batches, baseline_strokes=job.baseline_strokes)
    csv_path = write_channel_batch_csv(plan, output_dir / "channel-batch-cutting.csv")
    json_path = output_dir / "channel-batch-cutting.json"
    json_path.write_text(json.dumps(_plan_payload(plan, job), ensure_ascii=False, indent=2), encoding="utf-8")
    return plan, pages, csv_path, json_path


def main() -> int:
    parser = argparse.ArgumentParser(description="生成通用槽钢批量叠切人工优先方案")
    parser.add_argument("job", nargs="?", type=Path, default=DEFAULT_JOB,
        help="订单 JSON（默认：examples/channel_batch_job.json）")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="输出目录")
    parser.add_argument("--time-limit", type=float, default=300.0, help="每个求解阶段秒数")
    args = parser.parse_args()
    try:
        plan, pages, csv_path, json_path = generate(args.job, args.output, time_limit_seconds=args.time_limit)
    except (ValueError, RuntimeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(_plan_payload(plan, load_channel_batch_job(args.job))["summary"], ensure_ascii=False, indent=2))
    for path in pages:
        print(path)
    print(csv_path)
    print(json_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
