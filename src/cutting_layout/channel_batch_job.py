from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ChannelBatchJob:
    demand: Counter[int]
    kerf: int = 3
    stock_lengths: tuple[int, ...] = (6000, 9000)
    max_stack: int = 6
    min_bars: int = 1
    max_bars: int = 1000
    title: str = "槽钢批量叠切方案"
    baseline_batches: int = 0
    baseline_strokes: int = 0


def _positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field} must be a positive integer")
    return value


def load_channel_batch_job(path: str | Path) -> ChannelBatchJob:
    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read job JSON: {source}") from exc
    if not isinstance(payload, dict):
        raise ValueError("job JSON must be an object")

    raw_demand = payload.get("demand")
    if not isinstance(raw_demand, dict) or not raw_demand:
        raise ValueError("demand must be a non-empty object")
    demand: Counter[int] = Counter()
    for raw_length, raw_count in raw_demand.items():
        try:
            length = int(raw_length)
        except (TypeError, ValueError) as exc:
            raise ValueError("demand lengths must be integers") from exc
        demand[_positive_int(length, "demand length")] = _positive_int(
            raw_count, "demand quantity"
        )

    raw_stocks = payload.get("stock_lengths_mm", [6000, 9000])
    if not isinstance(raw_stocks, list) or not raw_stocks:
        raise ValueError("stock_lengths_mm must be a non-empty list")
    stock_lengths = tuple(sorted({_positive_int(value, "stock length") for value in raw_stocks}))
    kerf = payload.get("kerf_mm", 3)
    if isinstance(kerf, bool) or not isinstance(kerf, int) or kerf < 0:
        raise ValueError("kerf_mm must be a non-negative integer")
    max_stack = payload.get("max_stack", 6)
    if isinstance(max_stack, bool) or not isinstance(max_stack, int) or not 1 <= max_stack <= 100:
        raise ValueError("max_stack must be between 1 and 100")
    min_bars = payload.get("min_bars", 1)
    max_bars = payload.get("max_bars", max(1000, sum(demand.values())))
    if isinstance(min_bars, bool) or not isinstance(min_bars, int) or min_bars < 1:
        raise ValueError("min_bars must be positive")
    if isinstance(max_bars, bool) or not isinstance(max_bars, int) or max_bars < min_bars:
        raise ValueError("max_bars must be >= min_bars")
    if max(stock_lengths) < max(demand) + kerf:
        raise ValueError("stock_lengths_mm cannot fit the longest demanded piece")
    return ChannelBatchJob(
        demand=demand,
        kerf=kerf,
        stock_lengths=stock_lengths,
        max_stack=max_stack,
        min_bars=min_bars,
        max_bars=max_bars,
        title=str(payload.get("title", "槽钢批量叠切方案")),
        baseline_batches=int(payload.get("baseline_batches", 0)),
        baseline_strokes=int(payload.get("baseline_strokes", 0)),
    )
