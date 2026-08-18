from collections import Counter, defaultdict

from .models import LayoutPlan, Placement
from .splitting import validate_split_reconstruction


class PlanValidationError(ValueError):
    def __init__(self, errors: list[str]):
        self.errors = tuple(errors)
        super().__init__("; ".join(errors))


def rectangles_overlap(first: Placement, second: Placement, clearance: int) -> bool:
    return not (
        first.x + first.width + clearance <= second.x
        or second.x + second.width + clearance <= first.x
        or first.y + first.height + clearance <= second.y
        or second.y + second.height + clearance <= first.y
    )


def validate_plan(plan: LayoutPlan) -> None:
    errors: list[str] = []
    errors.extend(
        f"split reconstruction: {message}"
        for message in validate_split_reconstruction(plan.panels)
    )
    panel_ids = [panel.panel_id for panel in plan.panels]
    sheet_ids = [sheet.sheet_id for sheet in plan.sheets]
    if len(set(panel_ids)) != len(panel_ids):
        errors.append("duplicate panel IDs in plan")
    if len(set(sheet_ids)) != len(sheet_ids):
        errors.append("duplicate sheet IDs in plan")

    panel_by_id = {panel.panel_id: panel for panel in plan.panels}
    sheet_by_id = {sheet.sheet_id: sheet for sheet in plan.sheets}
    placement_counts = Counter(placement.panel_id for placement in plan.placements)

    for panel_id in panel_ids:
        count = placement_counts[panel_id]
        if count == 0:
            errors.append(f"{panel_id}: missing placement")
        elif count > 1:
            errors.append(f"{panel_id}: duplicate placement count {count}")
    for placement in plan.placements:
        panel = panel_by_id.get(placement.panel_id)
        sheet = sheet_by_id.get(placement.sheet_id)
        if panel is None:
            errors.append(f"{placement.panel_id}: placement refers to unknown panel")
            continue
        if sheet is None:
            errors.append(f"{placement.panel_id}: placement refers to unknown sheet {placement.sheet_id}")
            continue
        if panel.material_key != sheet.material_key:
            errors.append(f"{placement.panel_id}: material mismatch with {sheet.sheet_id}")
        expected_dimensions = (
            (panel.width, panel.height)
            if placement.rotation == 0
            else (panel.height, panel.width)
        )
        if (placement.width, placement.height) != expected_dimensions:
            errors.append(f"{placement.panel_id}: placement dimensions do not match rotation")
        if placement.rotation not in (0, 90):
            errors.append(f"{placement.panel_id}: unsupported rotation {placement.rotation}")
        if placement.rotation == 90 and not panel.rotation_allowed:
            errors.append(f"{placement.panel_id}: illegal rotation for direction-locked panel")
        margin = plan.settings.edge_margin
        if (
            placement.x < margin
            or placement.y < margin
            or placement.x + placement.width > sheet.width - margin
            or placement.y + placement.height > sheet.height - margin
        ):
            errors.append(f"{placement.panel_id}: violates sheet edge boundary on {sheet.sheet_id}")

    placements_by_sheet: defaultdict[str, list[Placement]] = defaultdict(list)
    for placement in plan.placements:
        placements_by_sheet[placement.sheet_id].append(placement)
    for sheet_id, placements in placements_by_sheet.items():
        for index, first in enumerate(placements):
            for second in placements[index + 1:]:
                if rectangles_overlap(first, second, plan.settings.clearance):
                    errors.append(f"{sheet_id}: overlap or clearance violation between {first.panel_id} and {second.panel_id}")

    for remnant in plan.remnants:
        sheet = sheet_by_id.get(remnant.sheet_id)
        if sheet is None:
            errors.append(f"remnant refers to unknown sheet {remnant.sheet_id}")
            continue
        if (
            remnant.width <= 0
            or remnant.height <= 0
            or remnant.x < plan.settings.edge_margin
            or remnant.y < plan.settings.edge_margin
            or remnant.x + remnant.width > sheet.width - plan.settings.edge_margin
            or remnant.y + remnant.height > sheet.height - plan.settings.edge_margin
        ):
            errors.append(f"{remnant.sheet_id}: invalid remnant boundary")

    opened_area = sum(sheet.width * sheet.height for sheet in plan.sheets)
    panel_area = sum(panel.width * panel.height for panel in plan.panels)
    reusable_area = sum(remnant.width * remnant.height for remnant in plan.remnants)
    if plan.metrics.opened_area != opened_area:
        errors.append("opened area metric does not match sheets")
    if plan.metrics.panel_area != panel_area:
        errors.append("panel area metric does not match panels")
    if plan.metrics.waste_area != opened_area - panel_area:
        errors.append("waste area metric does not match opened minus panel area")
    if plan.metrics.reusable_remnant_area != reusable_area:
        errors.append("reusable remnant area metric does not match remnants")
    if plan.metrics.new_standard_sheets != sum(sheet.kind == "standard" for sheet in plan.sheets):
        errors.append("standard sheet metric does not match sheets")
    if plan.metrics.remnants_used != sum(sheet.kind == "remnant" for sheet in plan.sheets):
        errors.append("remnant usage metric does not match sheets")

    product_sheets: defaultdict[str, set[str]] = defaultdict(set)
    for placement in plan.placements:
        panel = panel_by_id.get(placement.panel_id)
        if panel is not None:
            product_sheets[panel.product_id].add(placement.sheet_id)
    expected_dispersion = sum(max(0, len(items) - 1) for items in product_sheets.values())
    if plan.metrics.product_dispersion != expected_dispersion:
        errors.append("product dispersion metric does not match placements")

    if errors:
        raise PlanValidationError(errors)
