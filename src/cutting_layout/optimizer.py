from dataclasses import dataclass, replace
from math import ceil, hypot
from random import Random
from time import perf_counter
from typing import Callable, Iterable

from .expansion import group_panels
from .geometry import PackedSheet, SplitMode, new_packed_sheet, try_place
from .models import (
    Job,
    LayoutMetrics,
    LayoutPlan,
    MaterialKey,
    Panel,
    Placement,
    RemnantRect,
    SheetInstance,
    StockSpec,
)

TIME_LIMIT_SECONDS = {"fast": 30.0, "deep": 300.0}

Ordering = Callable[[Panel], tuple]
ORDERINGS: tuple[Ordering, ...] = (
    lambda panel: (-(panel.width * panel.height), -max(panel.width, panel.height), panel.panel_id),
    lambda panel: (-max(panel.width, panel.height), -(panel.width * panel.height), panel.panel_id),
    lambda panel: (-min(panel.width, panel.height), -(panel.width * panel.height), panel.panel_id),
    lambda panel: (-(panel.width + panel.height), -max(panel.width, panel.height), panel.panel_id),
)


class OptimizationError(ValueError):
    pass


@dataclass(frozen=True)
class _PackedCandidate:
    packed_sheets: tuple[PackedSheet, ...]
    metrics: LayoutMetrics
    remnants: tuple[RemnantRect, ...]


def _sheet_instances(
    stocks: Iterable[StockSpec],
    material_key: MaterialKey,
    group_number: int,
) -> tuple[SheetInstance, ...]:
    instances: list[SheetInstance] = []
    for stock in sorted(stocks, key=lambda item: (item.kind, item.width * item.height, item.stock_id)):
        if stock.material_key != material_key:
            continue
        for index in range(1, stock.quantity + 1):
            sheet_id = f"G{group_number:02d}-{stock.stock_id}-{index:03d}"
            instances.append(
                SheetInstance(
                    sheet_id,
                    stock.stock_id,
                    stock.kind,
                    stock.width,
                    stock.height,
                    stock.material_key,
                )
            )
    return tuple(instances)


def _panel_fits_sheet(panel: Panel, sheet: SheetInstance, edge_margin: int) -> bool:
    usable_width = sheet.width - 2 * edge_margin
    usable_height = sheet.height - 2 * edge_margin
    if panel.width <= usable_width and panel.height <= usable_height:
        return True
    return (
        panel.rotation_allowed
        and panel.height <= usable_width
        and panel.width <= usable_height
    )


def _format_mm(units: int) -> str:
    return f"{units / 100:.2f} mm"


def _check_oversize(
    panels: tuple[Panel, ...],
    sheets: tuple[SheetInstance, ...],
    edge_margin: int,
) -> None:
    for panel in panels:
        if any(_panel_fits_sheet(panel, sheet, edge_margin) for sheet in sheets):
            continue
        if panel.rotation_allowed:
            orientations = ((panel.width, panel.height), (panel.height, panel.width))
        else:
            orientations = ((panel.width, panel.height),)
        required_width, required_height = min(
            ((width + 2 * edge_margin, height + 2 * edge_margin) for width, height in orientations),
            key=lambda dimensions: (dimensions[0] * dimensions[1], dimensions),
        )
        raise OptimizationError(
            f"{panel.panel_id}: does not fit any compatible stock; minimum effective sheet "
            f"{_format_mm(required_width)} x {_format_mm(required_height)}"
        )


def _result_quality(result: PackedSheet) -> tuple:
    free_area = sum(rect.width * rect.height for rect in result.free_rects)
    placement = result.placements[-1]
    return (
        free_area,
        len(result.free_rects),
        result.sheet.sheet_id,
        placement.y,
        placement.x,
        placement.rotation,
    )


def _place_on_opened(
    opened: list[PackedSheet],
    panel: Panel,
    split_mode: SplitMode,
) -> bool:
    candidates: list[tuple[tuple, int, PackedSheet]] = []
    for index, packed in enumerate(opened):
        result = try_place(packed, panel, split_mode)
        if result is not None:
            candidates.append((_result_quality(result), index, result))
    if not candidates:
        return False
    _, index, result = min(candidates)
    opened[index] = result
    return True


def _open_sheet_for_panel(
    unopened: list[SheetInstance],
    panel: Panel,
    split_mode: SplitMode,
    job: Job,
) -> PackedSheet | None:
    for kind in ("remnant", "standard"):
        candidates: list[tuple[tuple, int, PackedSheet]] = []
        for index, sheet in enumerate(unopened):
            if sheet.kind != kind:
                continue
            result = try_place(new_packed_sheet(sheet, job.settings), panel, split_mode)
            if result is not None:
                candidates.append(
                    (
                        (sheet.width * sheet.height, _result_quality(result), sheet.sheet_id),
                        index,
                        result,
                    )
                )
        if candidates:
            _, index, result = min(candidates)
            unopened.pop(index)
            return result
    return None


def _pack_candidate(
    job: Job,
    ordered_panels: tuple[Panel, ...],
    sheets: tuple[SheetInstance, ...],
    split_mode: SplitMode,
) -> tuple[tuple[PackedSheet, ...], tuple[Panel, ...]]:
    opened: list[PackedSheet] = []
    unopened = list(sheets)
    for panel_index, panel in enumerate(ordered_panels):
        if _place_on_opened(opened, panel, split_mode):
            continue
        opened_sheet = _open_sheet_for_panel(unopened, panel, split_mode, job)
        if opened_sheet is None:
            return tuple(opened), ordered_panels[panel_index:]
        opened.append(opened_sheet)
    return tuple(opened), ()


def _candidate_orders(
    panels: tuple[Panel, ...], mode: str
) -> tuple[tuple[tuple[Panel, ...], SplitMode], ...]:
    candidates: list[tuple[tuple[Panel, ...], SplitMode]] = []
    for ordering in ORDERINGS:
        ordered = tuple(sorted(panels, key=ordering))
        candidates.append((ordered, "shorter_leftover"))
        candidates.append((ordered, "longer_leftover"))
    if mode == "deep":
        stable = list(sorted(panels, key=lambda panel: panel.panel_id))
        for seed in range(24):
            shuffled = stable.copy()
            Random(seed).shuffle(shuffled)
            split_mode: SplitMode = "shorter_leftover" if seed % 2 == 0 else "longer_leftover"
            candidates.append((tuple(shuffled), split_mode))
    return tuple(candidates)


def _extract_remnants(job: Job, packed_sheets: tuple[PackedSheet, ...]) -> tuple[RemnantRect, ...]:
    gap = job.settings.clearance
    remnants: list[RemnantRect] = []
    for packed in packed_sheets:
        for free in packed.free_rects:
            width = free.width - gap
            height = free.height - gap
            if (
                width >= job.settings.min_remnant_width
                and height >= job.settings.min_remnant_height
            ):
                remnants.append(RemnantRect(packed.sheet.sheet_id, free.x, free.y, width, height))
    return tuple(sorted(remnants, key=lambda item: (item.sheet_id, item.y, item.x)))


def _nearest_neighbour_distance(points: list[tuple[float, float]]) -> float:
    if len(points) < 2:
        return 0.0
    remaining = sorted(points)
    current = remaining.pop(0)
    total = 0.0
    while remaining:
        next_index, next_point = min(
            enumerate(remaining),
            key=lambda item: (hypot(current[0] - item[1][0], current[1] - item[1][1]), item[1]),
        )
        total += hypot(current[0] - next_point[0], current[1] - next_point[1])
        current = next_point
        remaining.pop(next_index)
    return total


def _metrics(
    panels: tuple[Panel, ...],
    packed_sheets: tuple[PackedSheet, ...],
    remnants: tuple[RemnantRect, ...],
) -> LayoutMetrics:
    panel_by_id = {panel.panel_id: panel for panel in panels}
    opened_sheets = tuple(packed.sheet for packed in packed_sheets)
    placements = tuple(placement for packed in packed_sheets for placement in packed.placements)
    opened_area = sum(sheet.width * sheet.height for sheet in opened_sheets)
    panel_area = sum(panel.width * panel.height for panel in panels)
    centres_by_sheet: dict[str, list[tuple[float, float]]] = {}
    sheets_by_product: dict[str, set[str]] = {}
    for placement in placements:
        centres_by_sheet.setdefault(placement.sheet_id, []).append(
            (placement.x + placement.width / 2, placement.y + placement.height / 2)
        )
        product = panel_by_id[placement.panel_id].product_id
        sheets_by_product.setdefault(product, set()).add(placement.sheet_id)
    rapid_travel = sum(_nearest_neighbour_distance(points) for points in centres_by_sheet.values())
    dispersion = sum(max(0, len(sheet_ids) - 1) for sheet_ids in sheets_by_product.values())
    return LayoutMetrics(
        new_standard_sheets=sum(sheet.kind == "standard" for sheet in opened_sheets),
        remnants_used=sum(sheet.kind == "remnant" for sheet in opened_sheets),
        opened_area=opened_area,
        panel_area=panel_area,
        waste_area=opened_area - panel_area,
        reusable_remnant_area=sum(item.width * item.height for item in remnants),
        rapid_travel=rapid_travel,
        product_dispersion=dispersion,
    )


def _candidate_tie_break(candidate: _PackedCandidate) -> tuple:
    placements = sorted(
        (placement for packed in candidate.packed_sheets for placement in packed.placements),
        key=lambda placement: placement.panel_id,
    )
    return tuple(
        (
            placement.panel_id,
            placement.sheet_id,
            placement.x,
            placement.y,
            placement.rotation,
        )
        for placement in placements
    )


def _estimate_additional_sheets(
    job: Job,
    unplaced: tuple[Panel, ...],
    standard_specs: tuple[StockSpec, ...],
) -> tuple[int, tuple[str, ...]]:
    if not standard_specs:
        return len(unplaced), ()
    usable_areas = [
        max(1, (stock.width - 2 * job.settings.edge_margin) * (stock.height - 2 * job.settings.edge_margin))
        for stock in standard_specs
    ]
    largest_usable_area = max(usable_areas)
    count = max(1, ceil(sum(panel.width * panel.height for panel in unplaced) / largest_usable_area))
    fitting_ids = tuple(
        stock.stock_id
        for stock in standard_specs
        if any(
            panel.width <= stock.width - 2 * job.settings.edge_margin
            and panel.height <= stock.height - 2 * job.settings.edge_margin
            for panel in unplaced
        )
    )
    return count, fitting_ids


def _optimize_group(
    job: Job,
    panels: tuple[Panel, ...],
    sheets: tuple[SheetInstance, ...],
    deadline: float,
) -> tuple[_PackedCandidate, bool]:
    _check_oversize(panels, sheets, job.settings.edge_margin)
    candidates: list[_PackedCandidate] = []
    best_unplaced: tuple[Panel, ...] | None = None
    time_limit_reached = False
    for candidate_index, (ordered, split_mode) in enumerate(_candidate_orders(panels, job.mode)):
        if candidate_index > 0 and perf_counter() >= deadline:
            time_limit_reached = True
            break
        packed_sheets, unplaced = _pack_candidate(job, ordered, sheets, split_mode)
        if unplaced:
            if best_unplaced is None or len(unplaced) < len(best_unplaced):
                best_unplaced = unplaced
            continue
        remnants = _extract_remnants(job, packed_sheets)
        candidates.append(_PackedCandidate(packed_sheets, _metrics(panels, packed_sheets, remnants), remnants))
    if not candidates:
        unplaced = best_unplaced or panels
        standard_specs = tuple(
            stock
            for stock in job.stocks
            if stock.material_key == panels[0].material_key and stock.kind == "standard"
        )
        count, stock_ids = _estimate_additional_sheets(job, unplaced, standard_specs)
        suggested = ", ".join(stock_ids) if stock_ids else "no compatible standard specification"
        raise OptimizationError(
            f"inventory shortage; unplaced panels: {len(unplaced)}; "
            f"suggested additional sheets: {count} using {suggested}"
        )
    best = min(candidates, key=lambda candidate: (candidate.metrics.score(), _candidate_tie_break(candidate)))
    return best, time_limit_reached


def _combine_metrics(metrics: tuple[LayoutMetrics, ...]) -> LayoutMetrics:
    return LayoutMetrics(
        new_standard_sheets=sum(item.new_standard_sheets for item in metrics),
        remnants_used=sum(item.remnants_used for item in metrics),
        opened_area=sum(item.opened_area for item in metrics),
        panel_area=sum(item.panel_area for item in metrics),
        waste_area=sum(item.waste_area for item in metrics),
        reusable_remnant_area=sum(item.reusable_remnant_area for item in metrics),
        rapid_travel=sum(item.rapid_travel for item in metrics),
        product_dispersion=sum(item.product_dispersion for item in metrics),
    )


def optimize(job: Job, panels: tuple[Panel, ...]) -> LayoutPlan:
    if not panels:
        raise OptimizationError("batch contains no panels")
    stock_ids = [stock.stock_id for stock in job.stocks]
    if len(set(stock_ids)) != len(stock_ids):
        raise OptimizationError("stock IDs must be unique")
    deadline = perf_counter() + TIME_LIMIT_SECONDS[job.mode]
    grouped = group_panels(panels)
    best_groups: list[_PackedCandidate] = []
    time_limit_reached = False
    for group_number, (material_key, group) in enumerate(grouped.items(), start=1):
        sheets = _sheet_instances(job.stocks, material_key, group_number)
        best, reached = _optimize_group(job, group, sheets, deadline)
        best_groups.append(best)
        time_limit_reached = time_limit_reached or reached
    packed_sheets = tuple(packed for candidate in best_groups for packed in candidate.packed_sheets)
    sheets = tuple(sorted((packed.sheet for packed in packed_sheets), key=lambda sheet: sheet.sheet_id))
    placements = tuple(
        sorted(
            (placement for packed in packed_sheets for placement in packed.placements),
            key=lambda placement: placement.panel_id,
        )
    )
    remnants = tuple(
        sorted(
            (remnant for candidate in best_groups for remnant in candidate.remnants),
            key=lambda remnant: (remnant.sheet_id, remnant.y, remnant.x),
        )
    )
    note = "validated deterministic heuristic; global optimum not proven"
    if time_limit_reached:
        note += "; time limit reached"
    combined_metrics = _combine_metrics(tuple(candidate.metrics for candidate in best_groups))
    panel_by_id = {panel.panel_id: panel for panel in panels}
    product_sheets: dict[str, set[str]] = {}
    for placement in placements:
        product_id = panel_by_id[placement.panel_id].product_id
        product_sheets.setdefault(product_id, set()).add(placement.sheet_id)
    combined_metrics = replace(
        combined_metrics,
        product_dispersion=sum(max(0, len(sheet_ids) - 1) for sheet_ids in product_sheets.values()),
    )
    return LayoutPlan(
        batch_name=job.batch_name,
        mode=job.mode,
        heuristic_note=note,
        settings=job.settings,
        panels=tuple(sorted(panels, key=lambda panel: panel.panel_id)),
        sheets=sheets,
        placements=placements,
        remnants=remnants,
        metrics=combined_metrics,
    )
