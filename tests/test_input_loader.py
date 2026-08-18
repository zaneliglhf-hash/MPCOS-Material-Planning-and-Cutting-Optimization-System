import json
from pathlib import Path

import pytest

from cutting_layout.input_loader import InputError, load_job, mm_to_units


def write_job(tmp_path: Path, overrides: dict | None = None) -> Path:
    payload = {
        "batch_name": "mixed-demo",
        "mode": "fast",
        "settings": {
            "edge_margin_mm": 10,
            "part_gap_mm": 3,
            "kerf_mm": 1.5,
            "min_remnant_width_mm": 200,
            "min_remnant_height_mm": 200,
        },
        "products": [{
            "order_id": "A01", "product_id": "BOX-A", "quantity": 2,
            "length_mm": 1200, "width_mm": 800, "height_mm": 600,
            "dimension_basis": "outer", "faces": ["top", "bottom", "front", "back", "left", "right"],
            "material": "Q235", "thickness_mm": 2, "surface": "plain",
            "rotation_allowed": True,
        }],
        "accessories": [],
        "panel_overrides": [],
        "stocks": [{
            "stock_id": "STD-2500x2050", "kind": "standard", "quantity": 5,
            "width_mm": 2500, "height_mm": 2050, "material": "Q235",
            "thickness_mm": 2, "surface": "plain", "stock_direction": "free",
        }],
    }
    if overrides:
        payload.update(overrides)
    path = tmp_path / "job.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_mm_to_units_accepts_two_decimal_places():
    assert mm_to_units("12.34", "width") == 1234


def test_mm_to_units_rejects_excess_precision():
    with pytest.raises(InputError, match="width.*two decimal places"):
        mm_to_units("12.345", "width")


def test_load_job_normalizes_dimensions_and_material_key(tmp_path):
    job = load_job(write_job(tmp_path))
    assert job.batch_name == "mixed-demo"
    assert job.products[0].length == 120_000
    assert job.products[0].material_key.thickness == 200
    assert job.settings.clearance == 300


def test_load_job_reports_field_path_for_invalid_quantity(tmp_path):
    path = write_job(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["products"][0]["quantity"] = 0
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(InputError, match=r"products\[0\]\.quantity"):
        load_job(path)


def test_load_job_parses_a_traceable_face_override(tmp_path):
    path = write_job(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["panel_overrides"] = [{
        "order_id": "A01", "product_id": "BOX-A", "face": "left",
        "width_mm": 790, "height_mm": 590, "quantity": 3,
        "material": "Q235", "thickness_mm": 2, "surface": "plain",
        "stock_direction": "free", "rotation_allowed": False,
    }]
    path.write_text(json.dumps(payload), encoding="utf-8")
    job = load_job(path)
    assert job.panel_overrides[0].face == "left"
    assert job.panel_overrides[0].width == 79_000
    assert job.panel_overrides[0].quantity == 3


def test_load_job_parses_provisional_split_controls(tmp_path):
    path = write_job(tmp_path, {
        "allow_panel_splitting": True,
        "provisional_notice": "3 毫米暂定，禁止直接下料",
    })
    job = load_job(path)
    assert job.allow_panel_splitting is True
    assert job.provisional_notice == "3 毫米暂定，禁止直接下料"


def test_split_control_requires_boolean(tmp_path):
    path = write_job(tmp_path, {"allow_panel_splitting": "yes"})
    with pytest.raises(InputError, match="allow_panel_splitting"):
        load_job(path)


def test_edge_margin_allows_zero(tmp_path):
    path = write_job(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["settings"]["edge_margin_mm"] = 0
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    assert load_job(path).settings.edge_margin == 0


def test_schema_rejects_unknown_top_level_field(tmp_path):
    path = write_job(tmp_path, {"unexpected": True})
    with pytest.raises(InputError, match=r"job.*unexpected"):
        load_job(path)


def test_schema_reports_nested_numeric_path(tmp_path):
    path = write_job(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["products"][0]["thickness_mm"] = 0
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(InputError, match=r"products\[0\]\.thickness_mm"):
        load_job(path)
