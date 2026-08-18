from dataclasses import replace

import pytest

from cutting_layout.models import MaterialKey
from cutting_layout.validation import PlanValidationError, validate_plan


def test_valid_plan_passes(valid_plan):
    validate_plan(valid_plan)


def test_overlap_is_rejected(valid_plan):
    first, second = valid_plan.placements
    broken = replace(valid_plan, placements=(first, replace(second, x=first.x, y=first.y)))
    with pytest.raises(PlanValidationError, match="overlap"):
        validate_plan(broken)


def test_missing_panel_is_rejected(valid_plan):
    broken = replace(valid_plan, placements=valid_plan.placements[:-1])
    with pytest.raises(PlanValidationError, match="missing placement"):
        validate_plan(broken)


def test_illegal_rotation_is_rejected(valid_plan):
    locked = replace(valid_plan.panels[0], rotation_allowed=False)
    rotated = replace(
        valid_plan.placements[0],
        width=locked.height,
        height=locked.width,
        rotation=90,
    )
    broken = replace(
        valid_plan,
        panels=(locked,) + valid_plan.panels[1:],
        placements=(rotated,) + valid_plan.placements[1:],
    )
    with pytest.raises(PlanValidationError, match="rotation"):
        validate_plan(broken)


def test_boundary_violation_is_rejected(valid_plan):
    first = replace(valid_plan.placements[0], x=0)
    broken = replace(valid_plan, placements=(first,) + valid_plan.placements[1:])
    with pytest.raises(PlanValidationError, match="edge boundary"):
        validate_plan(broken)


def test_material_mismatch_is_rejected(valid_plan):
    wrong_key = MaterialKey("304", 200, "plain", "free")
    wrong_panel = replace(valid_plan.panels[0], material_key=wrong_key)
    broken = replace(valid_plan, panels=(wrong_panel,) + valid_plan.panels[1:])
    with pytest.raises(PlanValidationError, match="material mismatch"):
        validate_plan(broken)


def test_incorrect_area_metric_is_rejected(valid_plan):
    broken_metrics = replace(valid_plan.metrics, panel_area=1)
    broken = replace(valid_plan, metrics=broken_metrics)
    with pytest.raises(PlanValidationError, match="panel area metric"):
        validate_plan(broken)


def test_validation_rejects_incomplete_split_reconstruction(valid_plan):
    panel = valid_plan.panels[0]
    broken = replace(panel, parent_width=panel.width * 2, piece_count=2)
    plan = replace(valid_plan, panels=(broken, *valid_plan.panels[1:]))
    with pytest.raises(PlanValidationError, match="split reconstruction"):
        validate_plan(plan)
