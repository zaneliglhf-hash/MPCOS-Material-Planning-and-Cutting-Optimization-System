from collections import defaultdict
from dataclasses import dataclass, replace
from math import ceil

from .models import Job, Panel, StockSpec

STRATEGIES = ("balanced", "prefer_1250", "prefer_1500")


@dataclass(frozen=True)
class SplitPlan:
    panels: tuple[Panel, ...]
    strategy: str
    weld_seams: int


def _fits_dimensions(width: int, height: int, stock: StockSpec, margin: int, rotation: bool) -> bool:
    usable_width = stock.width - 2 * margin
    usable_height = stock.height - 2 * margin
    if width <= usable_width and height <= usable_height:
        return True
    return rotation and height <= usable_width and width <= usable_height


def _compatible_stocks(job: Job, panel: Panel) -> tuple[StockSpec, ...]:
    return tuple(stock for stock in job.stocks if stock.material_key == panel.material_key)


def _panel_fits(job: Job, panel: Panel) -> bool:
    return any(
        _fits_dimensions(panel.width, panel.height, stock, job.settings.edge_margin, panel.rotation_allowed)
        for stock in _compatible_stocks(job, panel)
    )


def _strip_sizes(total: int, count: int, strategy: str) -> tuple[int, ...]:
    if strategy == "balanced":
        base, extra = divmod(total, count)
        return tuple(base + (1 if index < extra else 0) for index in range(count))
    preferred = 125_000 if strategy == "prefer_1250" else 150_000
    leading = [preferred] * (count - 1)
    remainder = total - sum(leading)
    if remainder <= 0 or remainder > 150_000:
        return _strip_sizes(total, count, "balanced")
    return tuple(leading + [remainder])


def _axis_candidate(job: Job, panel: Panel, axis: str, strategy: str) -> tuple[tuple[int, ...], tuple[Panel, ...]] | None:
    compatible = _compatible_stocks(job, panel)
    if not compatible:
        return None
    split_total = panel.width if axis == "width" else panel.height
    maximum_strip = max(
        min(stock.width, stock.height) - 2 * job.settings.edge_margin
        for stock in compatible
    )
    if maximum_strip <= 0:
        return None
    piece_count = ceil(split_total / maximum_strip)
    if piece_count <= 1:
        return None
    sizes = _strip_sizes(split_total, piece_count, strategy)
    pieces: list[Panel] = []
    for piece_index, size in enumerate(sizes, start=1):
        width = size if axis == "width" else panel.width
        height = panel.height if axis == "width" else size
        if not any(
            _fits_dimensions(width, height, stock, job.settings.edge_margin, panel.rotation_allowed)
            for stock in compatible
        ):
            return None
        pieces.append(
            replace(
                panel,
                panel_id=f"{panel.parent_panel_id or panel.panel_id}-P{piece_index:02d}of{piece_count:02d}",
                name=f"{panel.name} P{piece_index}/{piece_count}",
                width=width,
                height=height,
                parent_panel_id=panel.parent_panel_id or panel.panel_id,
                parent_width=panel.parent_width or panel.width,
                parent_height=panel.parent_height or panel.height,
                piece_index=piece_index,
                piece_count=piece_count,
                seam_group=panel.seam_group or panel.panel_id,
            )
        )
    return sizes, tuple(pieces)


def _split_panel(job: Job, panel: Panel, strategy: str) -> tuple[Panel, ...]:
    if _panel_fits(job, panel):
        return (panel,)
    candidates: list[tuple[tuple, tuple[Panel, ...]]] = []
    for axis in ("height", "width"):
        candidate = _axis_candidate(job, panel, axis, strategy)
        if candidate is None:
            continue
        _, pieces = candidate
        candidates.append(
            (
                (
                    len(pieces),
                    max(piece.width * piece.height for piece in pieces),
                    axis,
                ),
                pieces,
            )
        )
    if not candidates:
        return (panel,)
    return min(candidates, key=lambda item: item[0])[1]


def generate_split_plans(job: Job, panels: tuple[Panel, ...]) -> tuple[SplitPlan, ...]:
    if not job.allow_panel_splitting or all(_panel_fits(job, panel) for panel in panels):
        return (SplitPlan(panels, "none", 0),)
    plans: list[SplitPlan] = []
    seen: set[tuple] = set()
    for strategy in STRATEGIES:
        pieces = tuple(piece for panel in panels for piece in _split_panel(job, panel, strategy))
        signature = tuple(
            (piece.parent_panel_id, piece.piece_index, piece.width, piece.height)
            for piece in pieces
        )
        if signature in seen:
            continue
        seen.add(signature)
        weld_seams = sum(max(0, group[0].piece_count - 1) for group in _groups(pieces).values())
        plans.append(SplitPlan(pieces, strategy, weld_seams))
    return tuple(plans)


def _groups(panels: tuple[Panel, ...]) -> dict[str, list[Panel]]:
    groups: defaultdict[str, list[Panel]] = defaultdict(list)
    for panel in panels:
        groups[panel.parent_panel_id or panel.panel_id].append(panel)
    return dict(groups)


def validate_split_reconstruction(panels: tuple[Panel, ...]) -> tuple[str, ...]:
    errors: list[str] = []
    for parent_id, pieces in sorted(_groups(panels).items()):
        expected_count = pieces[0].piece_count
        parent_width = pieces[0].parent_width or pieces[0].width
        parent_height = pieces[0].parent_height or pieces[0].height
        seam_group = pieces[0].seam_group or parent_id
        if len(pieces) != expected_count:
            errors.append(f"{parent_id}: expected {expected_count} pieces, found {len(pieces)}")
            continue
        if sorted(piece.piece_index for piece in pieces) != list(range(1, expected_count + 1)):
            errors.append(f"{parent_id}: split piece sequence is incomplete or duplicated")
            continue
        if any(
            piece.piece_count != expected_count
            or (piece.parent_width or piece.width) != parent_width
            or (piece.parent_height or piece.height) != parent_height
            or (piece.seam_group or parent_id) != seam_group
            for piece in pieces
        ):
            errors.append(f"{parent_id}: split trace fields disagree")
            continue
        if expected_count == 1:
            valid = pieces[0].width == parent_width and pieces[0].height == parent_height
        else:
            vertical = all(piece.width == parent_width for piece in pieces) and sum(
                piece.height for piece in pieces
            ) == parent_height
            horizontal = all(piece.height == parent_height for piece in pieces) and sum(
                piece.width for piece in pieces
            ) == parent_width
            valid = vertical or horizontal
        if not valid:
            errors.append(f"{parent_id}: pieces do not reconstruct {parent_width / 100:g} x {parent_height / 100:g} mm")
    return tuple(errors)
