"""Local tool interface; no model, network connection, or API key is required."""

from __future__ import annotations

import json
import math
from importlib.resources import files
from pathlib import Path
from uuid import uuid4

from jsonschema import Draft202012Validator

from .channel_batch_job import parse_channel_batch_job
from .channel_batch_pipeline import generate_channel_batch_plan, plan_payload


CHANNEL_JOB_SCHEMA = json.loads(
    files("cutting_layout").joinpath("schemas", "channel-agent-job.schema.json").read_text(
        encoding="utf-8"
    )
)
_VALIDATOR = Draft202012Validator(CHANNEL_JOB_SCHEMA)
_FIELD_NAMES = {
    "demand": "零件长度与数量",
    "stock_lengths_mm": "原料长度（mm）",
    "kerf_mm": "锯缝（mm）",
    "max_stack": "经确认的最大叠切根数",
}
REVIEW_NOTICE = (
    "本结果为下料计划辅助资料。实际切割前，须由合格人员复核尺寸口径、"
    "型材方向、锯缝与端头余量、焊接和装配间隙、设备能力及吊装安全。"
    "本工具不生成已批准的 NC/G-code。"
)


def plan_cutting(
    job: dict,
    *,
    output_root: str | Path = "output/agent-plans",
    time_limit_seconds: float = 2.0,
) -> dict:
    """Plan one group of identical profiles; never mix sizes or materials.

    Only ``job`` is intended for model-supplied parameters. The application
    controls output_root and the per-solver-stage time limit. The time limit
    is not a deadline for the whole request. All returned values support JSON.
    """
    if not isinstance(job, dict):
        return {"status": "invalid_input", "message": "订单必须是包含字段的数据对象。"}
    demand = job.get("demand")
    if any(not isinstance(key, str) for key in job) or (
        isinstance(demand, dict) and any(not isinstance(key, str) for key in demand)
    ):
        return {"status": "invalid_input", "message": "字段名称及 demand 中的长度键必须是字符串。"}

    missing = [name for name in CHANNEL_JOB_SCHEMA["required"] if job.get(name) is None]
    if missing:
        return {
            "status": "needs_input",
            "missing_fields": missing,
            "message": "请补充：" + "、".join(_FIELD_NAMES[name] for name in missing),
        }

    # Agent input is stricter than the legacy CLI: no silent process defaults
    # or extra fields that the calculator would ignore.
    error = next(_VALIDATOR.iter_errors(job), None)
    if error is not None:
        field = ".".join(map(str, error.absolute_path)) or "job"
        return {
            "status": "invalid_input",
            "message": f"订单参数不合法：{field}: {error.message}",
        }
    try:
        parsed_job = parse_channel_batch_job(job)
    except ValueError as exc:
        return {"status": "invalid_input", "message": str(exc)}

    if (
        isinstance(time_limit_seconds, bool)
        or not isinstance(time_limit_seconds, (int, float))
        or not math.isfinite(time_limit_seconds)
        or time_limit_seconds <= 0
    ):
        return {"status": "execution_error", "message": "工具的求解时间限制必须为正数。"}

    run_id = uuid4().hex
    try:
        output_dir = Path(output_root).resolve() / run_id
        plan, pages, csv_path, json_path = generate_channel_batch_plan(
            parsed_job, output_dir, time_limit_seconds=time_limit_seconds,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        return {
            "status": "execution_error",
            "message": f"计算或导出失败：{exc}",
        }

    return {
        "status": "success",
        "run_id": run_id,
        "review_status": "pending",
        "message": "下料方案已生成，等待人工复核。",
        **plan_payload(plan, parsed_job),
        "files": {
            "input": str(output_dir / "input.json"),
            "images": [str(page) for page in pages],
            "csv": str(csv_path),
            "json": str(json_path),
        },
        "notice": REVIEW_NOTICE,
    }
