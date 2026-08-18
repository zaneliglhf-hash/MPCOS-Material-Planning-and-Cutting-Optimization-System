import json

import pytest

from cutting_layout.expansion import expand_job
from cutting_layout.input_loader import load_job
from cutting_layout.models import (
    LayoutMetrics,
    LayoutPlan,
    MaterialKey,
    Panel,
    Placement,
    ProcessSettings,
    SheetInstance,
)
from cutting_layout.pipeline import select_layout


@pytest.fixture
def valid_plan():
    key = MaterialKey("Q235", 200, "plain", "free")
    settings = ProcessSettings(100, 100, 100, 500, 500)
    panels = (
        Panel("O-A-top-001", "O", "A", "top", 1, 3000, 2000, key, True, "generated"),
        Panel("O-B-top-001", "O", "B", "top", 1, 3000, 2000, key, True, "generated"),
    )
    sheet = SheetInstance("S-001", "STD", "standard", 10000, 10000, key)
    placements = (
        Placement(panels[0].panel_id, sheet.sheet_id, 100, 100, 3000, 2000, 0),
        Placement(panels[1].panel_id, sheet.sheet_id, 3200, 100, 3000, 2000, 0),
    )
    metrics = LayoutMetrics(1, 0, 100_000_000, 12_000_000, 88_000_000, 0, 3100.0, 0)
    return LayoutPlan(
        "fixture-batch",
        "fast",
        "validated deterministic heuristic; global optimum not proven",
        settings,
        panels,
        (sheet,),
        placements,
        (),
        metrics,
    )


@pytest.fixture
def capacity_job_path(tmp_path):
    payload = {
        "batch_name": "capacity-2000",
        "mode": "fast",
        "settings": {
            "edge_margin_mm": 10,
            "part_gap_mm": 3,
            "kerf_mm": 1.5,
            "min_remnant_width_mm": 200,
            "min_remnant_height_mm": 200,
        },
        "products": [],
        "accessories": [
            {
                "order_id": f"O-{index:03d}",
                "product_id": f"P-{index:03d}",
                "name": "panel",
                "quantity": 20,
                "width_mm": 100,
                "height_mm": 100,
                "material": "Q235",
                "thickness_mm": 2,
                "surface": "plain",
                "stock_direction": "free",
                "rotation_allowed": True,
            }
            for index in range(100)
        ],
        "panel_overrides": [],
        "stocks": [{
            "stock_id": "STD-2500x2050",
            "kind": "standard",
            "quantity": 10,
            "width_mm": 2500,
            "height_mm": 2050,
            "material": "Q235",
            "thickness_mm": 2,
            "surface": "plain",
            "stock_direction": "free",
        }],
    }
    path = tmp_path / "capacity.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


@pytest.fixture
def oversize_job_path(tmp_path):
    payload = {
        "batch_name": "超宽测试",
        "mode": "fast",
        "allow_panel_splitting": True,
        "provisional_notice": "3 毫米暂定，禁止直接下料",
        "settings": {
            "edge_margin_mm": 0, "part_gap_mm": 3, "kerf_mm": 3,
            "min_remnant_width_mm": 200, "min_remnant_height_mm": 200,
        },
        "products": [],
        "accessories": [{
            "order_id": "O", "product_id": "P", "name": "top", "quantity": 1,
            "width_mm": 3006, "height_mm": 2506, "material": "普通铁板",
            "thickness_mm": 3, "surface": "普通", "stock_direction": "free",
            "rotation_allowed": True,
        }],
        "panel_overrides": [],
        "stocks": [
            {"stock_id": "STD-6000x1500", "kind": "standard", "quantity": 5,
             "width_mm": 6000, "height_mm": 1500, "material": "普通铁板",
             "thickness_mm": 3, "surface": "普通", "stock_direction": "free"},
            {"stock_id": "STD-6000x1250", "kind": "standard", "quantity": 5,
             "width_mm": 6000, "height_mm": 1250, "material": "普通铁板",
             "thickness_mm": 3, "surface": "普通", "stock_direction": "free"},
        ],
    }
    path = tmp_path / "oversize.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.fixture
def split_valid_plan(oversize_job_path):
    job = load_job(oversize_job_path)
    return select_layout(job, expand_job(job))
