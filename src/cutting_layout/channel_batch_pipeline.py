"""Shared channel-cutting calculation and export for CLI and agent tools."""

from __future__ import annotations

import json
from pathlib import Path

from .channel_batch import ChannelBatchPlan, validate_batch_plan
from .channel_batch_job import ChannelBatchJob
from .channel_batch_optimizer import improve_channel_batch_plan, optimize_channel_batches
from .channel_batch_rendering import render_channel_batch_pages, write_channel_batch_csv
from .output_transaction import OutputTransaction


def plan_payload(plan: ChannelBatchPlan, job: ChannelBatchJob) -> dict:
    return {
        "summary": {
            "solver_status": plan.solver_status,
            "batch_count": plan.batch_count,
            "bar_count": plan.bar_count,
            "saw_strokes": plan.saw_strokes,
            "procurement": dict(sorted(plan.procurement_counts.items())),
            "stock_lengths_mm": list(job.stock_lengths),
            "kerf_mm": job.kerf,
            "total_stock_mm": plan.total_stock,
            "finished_length_mm": plan.total_finished,
            "kerf_total_mm": plan.total_kerf,
            "offcut_mm": plan.total_offcut,
            "utilization_percent": round(plan.utilization_percent, 4),
            "baseline_batch_savings": max(0, job.baseline_batches - plan.batch_count),
            "baseline_stroke_savings": max(0, job.baseline_strokes - plan.saw_strokes),
        },
        "batches": [
            {
                "batch": number,
                "stock_length_mm": batch.stock_length,
                "bars": batch.multiplicity,
                "cuts_mm": list(batch.pieces_per_bar),
                "saw_strokes": batch.cuts,
                "used_per_bar_mm": batch.used_per_bar,
                "offcut_per_bar_mm": batch.offcut_per_bar,
            }
            for number, batch in enumerate(plan.batches, 1)
        ],
    }


def generate_channel_batch_plan(
    job: ChannelBatchJob,
    output_dir: Path,
    *,
    time_limit_seconds: float = 300.0,
) -> tuple[ChannelBatchPlan, list[Path], Path, Path]:
    plan = optimize_channel_batches(
        job.demand, kerf=job.kerf, max_stack=job.max_stack,
        min_bars=job.min_bars, max_bars=job.max_bars,
        stock_lengths=job.stock_lengths, time_limit_seconds=time_limit_seconds,
    )
    plan = improve_channel_batch_plan(
        job.demand, plan, min_bars=job.min_bars, max_bars=job.max_bars,
        max_stack=job.max_stack, stock_lengths=job.stock_lengths,
        time_limit_seconds=time_limit_seconds,
    )
    validate_batch_plan(plan, job.demand)
    if not job.min_bars <= plan.bar_count <= job.max_bars:
        raise RuntimeError("optimized plan is outside the requested bar range")
    if any(batch.multiplicity > job.max_stack for batch in plan.batches):
        raise RuntimeError("optimized plan exceeds the requested stack limit")

    output_dir = Path(output_dir)
    # Publish the entire export together, preserving old files on failure.
    with OutputTransaction(output_dir) as transaction:
        staging = transaction.staging_dir
        pages = render_channel_batch_pages(
            plan, staging, job.title,
            baseline_batches=job.baseline_batches,
            baseline_strokes=job.baseline_strokes,
        )
        csv_path = write_channel_batch_csv(plan, staging / "channel-batch-cutting.csv")
        json_path = staging / "channel-batch-cutting.json"
        json_path.write_text(
            json.dumps(plan_payload(plan, job), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        # Save the actual parameters used, including non-process defaults.
        input_payload = {
            "demand": {str(length): count for length, count in sorted(job.demand.items())},
            "kerf_mm": job.kerf,
            "stock_lengths_mm": list(job.stock_lengths),
            "max_stack": job.max_stack,
            "min_bars": job.min_bars,
            "max_bars": job.max_bars,
            "title": job.title,
            "baseline_batches": job.baseline_batches,
            "baseline_strokes": job.baseline_strokes,
        }
        (staging / "input.json").write_text(
            json.dumps(input_payload, ensure_ascii=False, indent=2), encoding="utf-8",
        )
        transaction.commit()

    return (
        plan,
        [output_dir / page.name for page in pages],
        output_dir / csv_path.name,
        output_dir / json_path.name,
    )
