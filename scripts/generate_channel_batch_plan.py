from __future__ import annotations

import argparse
import json
from pathlib import Path

from cutting_layout.channel_batch_job import load_channel_batch_job
from cutting_layout.channel_batch_pipeline import generate_channel_batch_plan, plan_payload

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_JOB = ROOT / "examples" / "channel_batch_job.json"
DEFAULT_OUTPUT = ROOT / "output" / "channel-cutting-plan-batched"


def generate(job_path: Path = DEFAULT_JOB, output_dir: Path = DEFAULT_OUTPUT, *, time_limit_seconds: float = 300.0):
    job = load_channel_batch_job(job_path)
    return generate_channel_batch_plan(job, output_dir, time_limit_seconds=time_limit_seconds)


def main() -> int:
    parser = argparse.ArgumentParser(description="生成通用槽钢批量叠切人工优先方案")
    parser.add_argument("job", nargs="?", type=Path, default=DEFAULT_JOB,
        help="订单 JSON（默认：examples/channel_batch_job.json）")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="输出目录")
    parser.add_argument("--time-limit", type=float, default=300.0, help="每个求解阶段秒数")
    args = parser.parse_args()
    try:
        plan, pages, csv_path, json_path = generate(args.job, args.output, time_limit_seconds=args.time_limit)
    except (OSError, ValueError, RuntimeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(plan_payload(plan, load_channel_batch_job(args.job))["summary"], ensure_ascii=False, indent=2))
    for path in pages:
        print(path)
    print(csv_path)
    print(json_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
