"""Read saved plan summaries locally without recalculation or model requests."""

from __future__ import annotations

from datetime import datetime
import json
import math
from pathlib import Path
import re

from .channel_batch_job import parse_channel_batch_job


_RUN_ID = re.compile(r"[0-9a-f]{32}")
_MAX_BYTES = 1024 * 1024


def _read_json(path: Path):
    if path.is_symlink() or not path.is_file():
        raise ValueError("not a regular saved file")
    with path.open("rb") as handle:
        raw = handle.read(_MAX_BYTES + 1)
    if len(raw) > _MAX_BYTES:
        raise ValueError("saved file too large")
    return json.loads(raw)


def _read_title(folder: Path) -> str:
    """Optional metadata must not hide an otherwise readable plan summary."""
    try:
        payload = _read_json(folder / "input.json")
        title = payload.get("title") if isinstance(payload, dict) else None
        if isinstance(title, str):
            # Keep user-supplied names on one terminal line without controls.
            title = " ".join(title.split())
            title = "".join(char for char in title if char.isprintable())[:100].strip()
            return title or "未命名方案"
    except (OSError, ValueError, UnicodeError, RecursionError):
        pass
    return "未命名方案"


def _read_entry(folder: Path) -> dict:
    result_path = folder / "channel-batch-cutting.json"
    if folder.is_symlink():
        raise ValueError("not a saved result directory")
    payload = _read_json(result_path)
    if not isinstance(payload, dict) or not isinstance(payload.get("summary"), dict):
        raise ValueError("missing summary")
    summary = payload["summary"]
    for name, minimum in (("bar_count", 1), ("batch_count", 1), ("saw_strokes", 0), ("offcut_mm", 0)):
        value = summary.get(name)
        if type(value) is not int or value < minimum:
            raise ValueError("invalid count or length")
    utilization = summary.get("utilization_percent")
    if (
        type(utilization) not in (int, float)
        or not 0 <= utilization <= 100
        or not math.isfinite(utilization)
    ):
        raise ValueError("invalid utilization")
    modified = result_path.stat().st_mtime
    return {
        "run_id": folder.name,
        "title": _read_title(folder),
        "modified_at": datetime.fromtimestamp(modified).astimezone().isoformat(timespec="seconds"),
        "modified_timestamp": modified,
        "summary": {name: summary[name] for name in (
            "bar_count", "batch_count", "saw_strokes", "offcut_mm", "utilization_percent",
        )},
        "directory": str(folder),
    }


def list_plan_history(output_root: str | Path, *, limit: int = 10, query: str = "") -> dict:
    """List recent readable summaries; file modification times are not creation times.

    Only UUID-named immediate subdirectories are considered. Reading the summary
    does not certify the plan or the presence of every originally exported file.
    """
    if type(limit) is not int or limit < 1:
        raise ValueError("limit must be a positive integer")
    query = " ".join(query.split())
    keyword = "".join(query.split()).casefold()
    try:
        root = Path(output_root).resolve()
        folders = list(root.iterdir())
    except FileNotFoundError:
        folders = []
    except OSError:
        return {"status": "error", "message": "无法读取历史方案目录，请检查目录和访问权限。"}
    entries = []
    skipped = 0
    for folder in folders:
        if not _RUN_ID.fullmatch(folder.name):
            continue
        try:
            entries.append(_read_entry(folder))
        except (OSError, ValueError, UnicodeError, RecursionError, OverflowError):
            skipped += 1
    entries.sort(key=lambda entry: (entry["modified_timestamp"], entry["run_id"]), reverse=True)
    # Search every readable record before limiting the displayed results.
    matched = [entry for entry in entries if (
        keyword in "".join(entry["title"].split()).casefold()
        or keyword in entry["run_id"].casefold()
    )]
    return {
        "status": "ok", "entries": matched[:limit], "total": len(entries),
        "matched": len(matched), "query": query, "skipped": skipped,
    }


def read_plan_details(output_root: str | Path, run_id: str) -> dict:
    """Read saved inputs and summary for one complete ID; never infer process values."""
    if not isinstance(run_id, str) or not _RUN_ID.fullmatch(run_id.strip().lower()):
        return {"status": "error", "message": "请粘贴完整的 32 位方案编号，可先输入“查看历史”查找。"}
    run_id = run_id.strip().lower()
    try:
        folder = Path(output_root).resolve() / run_id
        if folder.is_symlink():
            raise ValueError("linked directory")
        if not folder.exists():
            return {"status": "error", "message": "未找到这个方案，请先输入“查看历史”核对编号。"}
        entry = _read_entry(folder)
        payload = _read_json(folder / "input.json")
        required = ("demand", "stock_lengths_mm", "kerf_mm", "max_stack")
        if not isinstance(payload, dict) or any(name not in payload for name in required):
            raise ValueError("incomplete saved input")
        job = parse_channel_batch_job(payload)
    except (OSError, ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        return {
            "status": "error",
            "message": "无法读取方案详情：订单参数或结果文件缺失、损坏或格式不正确。可先用“查看历史”核对记录。",
        }
    return {
        "status": "ok", "entry": entry,
        "parameters": {
            "demand": {str(length): count for length, count in sorted(job.demand.items())},
            "stock_lengths_mm": list(job.stock_lengths),
            "kerf_mm": job.kerf, "max_stack": job.max_stack,
        },
    }
