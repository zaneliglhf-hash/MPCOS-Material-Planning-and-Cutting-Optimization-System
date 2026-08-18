import pytest

from cutting_layout.models import Job, MaterialKey, Panel, ProcessSettings, StockSpec
from cutting_layout.optimizer import OptimizationError, optimize


KEY = MaterialKey("Q235", 200, "plain", "free")
SETTINGS = ProcessSettings(100, 100, 100, 2_000, 2_000)


def make_job(stocks, mode="fast"):
    return Job("batch", mode, SETTINGS, (), (), (), tuple(stocks))


def part(panel_id, product, width, height, key=KEY, rotation=True):
    return Panel(
        panel_id, panel_id.split("-")[0], product, "face", 1,
        width, height, key, rotation, "generated",
    )


def stock(stock_id, kind, quantity, width=10_000, height=10_000, key=KEY):
    return StockSpec(stock_id, kind, quantity, width, height, key)


def test_mixes_different_products_on_same_sheet():
    panels = (part("A-1", "A", 4_000, 4_000), part("B-1", "B", 4_000, 4_000))
    plan = optimize(make_job([stock("STD", "standard", 1)]), panels)
    assert plan.metrics.new_standard_sheets == 1
    assert len({placement.sheet_id for placement in plan.placements}) == 1
    assert {placement.panel_id for placement in plan.placements} == {"A-1", "B-1"}


def test_prefers_remnant_when_standard_sheet_count_is_unchanged():
    panels = (part("A-1", "A", 4_000, 4_000),)
    plan = optimize(
        make_job([stock("REM", "remnant", 1, 5_000, 5_000), stock("STD", "standard", 1)]),
        panels,
    )
    assert plan.metrics.new_standard_sheets == 0
    assert plan.metrics.remnants_used == 1


def test_reports_oversize_panel_with_required_dimensions():
    panels = (part("A-oversize", "A", 20_000, 4_000),)
    with pytest.raises(OptimizationError, match="A-oversize.*minimum effective sheet"):
        optimize(make_job([stock("STD", "standard", 2)]), panels)


def test_reports_inventory_shortage_without_dropping_parts():
    panels = tuple(part(f"A-{i}", "A", 9_000, 9_000) for i in range(3))
    with pytest.raises(OptimizationError, match="unplaced panels: 2.*suggested additional sheets"):
        optimize(make_job([stock("STD", "standard", 1)]), panels)


def test_same_input_produces_same_coordinates():
    panels = tuple(part(f"A-{i}", "A", 3_000 + i * 10, 2_000) for i in range(8))
    job = make_job([stock("STD", "standard", 4)])
    assert optimize(job, panels).placements == optimize(job, panels).placements


def test_time_limit_returns_first_valid_candidate_with_explicit_note(monkeypatch):
    import cutting_layout.optimizer as optimizer

    monkeypatch.setitem(optimizer.TIME_LIMIT_SECONDS, "deep", 0.0)
    panels = (part("A-1", "A", 4_000, 4_000),)
    plan = optimize(make_job([stock("STD", "standard", 1)], mode="deep"), panels)
    assert "time limit reached" in plan.heuristic_note


def test_incompatible_materials_use_different_sheets():
    stainless = MaterialKey("304", 150, "2B", "free")
    panels = (
        part("A-1", "A", 4_000, 4_000),
        part("B-1", "B", 4_000, 4_000, key=stainless),
    )
    job = make_job([
        stock("Q235", "standard", 1),
        stock("SS304", "standard", 1, key=stainless),
    ])
    plan = optimize(job, panels)
    assert len({placement.sheet_id for placement in plan.placements}) == 2


def test_dispersion_is_recomputed_after_material_groups_are_combined():
    stainless = MaterialKey("304", 150, "2B", "free")
    panels = (
        part("A-1", "SAME-PRODUCT", 4_000, 4_000),
        part("A-2", "SAME-PRODUCT", 4_000, 4_000, key=stainless),
    )
    job = make_job([
        stock("Q235", "standard", 1),
        stock("SS304", "standard", 1, key=stainless),
    ])
    plan = optimize(job, panels)
    assert plan.metrics.product_dispersion == 1


def test_direction_locked_oversize_panel_is_not_rotated_to_fit():
    panels = (part("A-locked", "A", 9_000, 11_000, rotation=False),)
    with pytest.raises(OptimizationError, match="A-locked"):
        optimize(make_job([stock("STD", "standard", 1, width=12_000, height=10_000)]), panels)
