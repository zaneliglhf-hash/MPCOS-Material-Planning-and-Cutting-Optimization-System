from __future__ import annotations

from collections import Counter
from dataclasses import dataclass


@dataclass(frozen=True)
class ChannelBatch:
    """One load/unload cycle containing identical stock bars and cuts."""

    stock_length: int
    multiplicity: int
    pieces_per_bar: tuple[int, ...]
    kerf: int = 3
    max_stack: int = 6

    def __post_init__(self) -> None:
        if self.stock_length <= 0:
            raise ValueError("stock length must be positive")
        if self.max_stack < 1:
            raise ValueError("max_stack must be positive")
        if not 1 <= self.multiplicity <= self.max_stack:
            raise ValueError(f"batch multiplicity must be between 1 and {self.max_stack}")
        if not self.pieces_per_bar or any(piece <= 0 for piece in self.pieces_per_bar):
            raise ValueError("pieces_per_bar must contain positive lengths")
        if self.kerf < 0:
            raise ValueError("kerf must be non-negative")

    @property
    def cuts(self) -> int:
        return len(self.pieces_per_bar)

    @property
    def used_per_bar(self) -> int:
        return sum(self.pieces_per_bar) + self.cuts * self.kerf

    @property
    def offcut_per_bar(self) -> int:
        return self.stock_length - self.used_per_bar

    def produced_counts(self) -> Counter[int]:
        per_bar = Counter(self.pieces_per_bar)
        return Counter(
            {
                length: count * self.multiplicity
                for length, count in per_bar.items()
            }
        )


@dataclass(frozen=True)
class ChannelBatchPlan:
    batches: tuple[ChannelBatch, ...]
    kerf: int = 3
    solver_status: str = "verified"

    @property
    def batch_count(self) -> int:
        return len(self.batches)

    @property
    def bar_count(self) -> int:
        return sum(batch.multiplicity for batch in self.batches)

    @property
    def saw_strokes(self) -> int:
        return sum(batch.cuts for batch in self.batches)

    @property
    def total_stock(self) -> int:
        return sum(
            batch.stock_length * batch.multiplicity for batch in self.batches
        )

    @property
    def total_finished(self) -> int:
        return sum(
            sum(batch.pieces_per_bar) * batch.multiplicity
            for batch in self.batches
        )

    @property
    def total_kerf(self) -> int:
        return sum(
            batch.cuts * batch.kerf * batch.multiplicity
            for batch in self.batches
        )

    @property
    def total_offcut(self) -> int:
        return sum(
            batch.offcut_per_bar * batch.multiplicity
            for batch in self.batches
        )

    @property
    def utilization_percent(self) -> float:
        if self.total_stock == 0:
            return 0.0
        return self.total_finished / self.total_stock * 100

    @property
    def procurement_counts(self) -> Counter[int]:
        counts: Counter[int] = Counter()
        for batch in self.batches:
            counts[batch.stock_length] += batch.multiplicity
        return counts


def validate_batch_plan(
    plan: ChannelBatchPlan,
    demand: Counter[int],
) -> None:
    if not plan.batches:
        raise ValueError("batch plan is empty")
    actual: Counter[int] = Counter()
    for batch in plan.batches:
        if batch.kerf != plan.kerf:
            raise ValueError("batch kerf differs from plan kerf")
        if batch.offcut_per_bar < 0:
            raise ValueError("batch exceeds stock length")
        actual.update(batch.produced_counts())
    if actual != demand:
        raise ValueError(
            f"quantity mismatch: extra={actual - demand}, missing={demand - actual}"
        )
