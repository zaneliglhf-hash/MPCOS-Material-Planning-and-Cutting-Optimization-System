from pathlib import Path

import ezdxf
from ezdxf.enums import TextEntityAlignment

from .models import LayoutPlan


def _mm(units: int) -> float:
    return units / 100.0


def _rectangle_points(x: float, y: float, width: float, height: float):
    return (
        (x, y),
        (x + width, y),
        (x + width, y + height),
        (x, y + height),
    )


def _sheet_origins(plan: LayoutPlan) -> dict[str, tuple[float, float]]:
    origins: dict[str, tuple[float, float]] = {}
    x = 0.0
    y = 0.0
    row_height = 0.0
    wrap_width = 12_000.0
    gap = 500.0
    for sheet in plan.sheets:
        width = _mm(sheet.width)
        height = _mm(sheet.height)
        if x > 0 and x + width > wrap_width:
            x = 0.0
            y += row_height + gap
            row_height = 0.0
        origins[sheet.sheet_id] = (x, y)
        x += width + gap
        row_height = max(row_height, height)
    return origins


def export_dxf(plan: LayoutPlan, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = ezdxf.new("R2010", setup=True)
    doc.units = ezdxf.units.MM
    layer_specs = {
        "SHEET": 7,
        "PART": 3,
        "LABEL": 2,
        "REMNANT": 8,
    }
    for name, color in layer_specs.items():
        if not doc.layers.has_entry(name):
            attributes = {"color": color}
            if name == "REMNANT" and doc.linetypes.has_entry("DASHED"):
                attributes["linetype"] = "DASHED"
            doc.layers.add(name, dxfattribs=attributes)

    modelspace = doc.modelspace()
    origins = _sheet_origins(plan)
    panel_by_id = {panel.panel_id: panel for panel in plan.panels}

    if plan.provisional_notice:
        modelspace.add_text(
            plan.provisional_notice,
            dxfattribs={"layer": "LABEL", "height": 40.0, "color": 1},
        ).set_placement((0.0, -120.0), align=TextEntityAlignment.BOTTOM_LEFT)

    for sheet in plan.sheets:
        origin_x, origin_y = origins[sheet.sheet_id]
        width, height = _mm(sheet.width), _mm(sheet.height)
        modelspace.add_lwpolyline(
            _rectangle_points(origin_x, origin_y, width, height),
            close=True,
            dxfattribs={"layer": "SHEET"},
        )
        modelspace.add_text(
            f"{sheet.sheet_id} | {sheet.material_key.material} | {_mm(sheet.material_key.thickness):g}mm | {width:g}x{height:g}",
            dxfattribs={"layer": "LABEL", "height": 18.0},
        ).set_placement((origin_x, origin_y - 30.0), align=TextEntityAlignment.BOTTOM_LEFT)

    for placement in plan.placements:
        panel = panel_by_id[placement.panel_id]
        origin_x, origin_y = origins[placement.sheet_id]
        x = origin_x + _mm(placement.x)
        y = origin_y + _mm(placement.y)
        width = _mm(placement.width)
        height = _mm(placement.height)
        modelspace.add_lwpolyline(
            _rectangle_points(x, y, width, height),
            close=True,
            dxfattribs={"layer": "PART"},
        )
        text_height = max(5.0, min(30.0, min(width, height) / 12.0))
        centre = (x + width / 2, y + height / 2)
        modelspace.add_text(
            panel.panel_id,
            dxfattribs={"layer": "LABEL", "height": text_height},
        ).set_placement(centre, align=TextEntityAlignment.MIDDLE_CENTER)
        piece_suffix = f" | P{panel.piece_index}/{panel.piece_count}" if panel.piece_count > 1 else ""
        modelspace.add_text(
            f"{_mm(panel.width):g} x {_mm(panel.height):g} mm{piece_suffix} | R{placement.rotation}",
            dxfattribs={"layer": "LABEL", "height": max(4.0, text_height * 0.65)},
        ).set_placement(
            (centre[0], centre[1] - text_height * 1.4),
            align=TextEntityAlignment.MIDDLE_CENTER,
        )

    for remnant in plan.remnants:
        origin_x, origin_y = origins[remnant.sheet_id]
        modelspace.add_lwpolyline(
            _rectangle_points(
                origin_x + _mm(remnant.x),
                origin_y + _mm(remnant.y),
                _mm(remnant.width),
                _mm(remnant.height),
            ),
            close=True,
            dxfattribs={"layer": "REMNANT"},
        )

    doc.saveas(path)
    return path
