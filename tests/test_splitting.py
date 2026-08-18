from cutting_layout.models import Job, MaterialKey, Panel, ProcessSettings, StockSpec
from cutting_layout.splitting import generate_split_plans, validate_split_reconstruction

KEY = MaterialKey("普通铁板", 300, "普通", "free")
SETTINGS = ProcessSettings(0, 300, 300, 20_000, 20_000)
STOCKS = (
    StockSpec("STD-6000x1500", "standard", 100, 600_000, 150_000, KEY),
    StockSpec("STD-6000x1250", "standard", 100, 600_000, 125_000, KEY),
)


def make_job():
    return Job("预排版", "fast", SETTINGS, (), (), (), STOCKS, True, "3 毫米暂定，禁止直接下料")


def make_panel(width=300_600, height=250_600):
    return Panel(
        "O-P-top-001", "O", "P", "top", 1, width, height, KEY, True, "generated",
        "O-P-top-001", width, height, 1, 1, "O-P-top-001",
    )


def test_oversize_face_has_three_minimum_seam_alternatives():
    plans = generate_split_plans(make_job(), (make_panel(),))
    assert [plan.strategy for plan in plans] == ["balanced", "prefer_1250", "prefer_1500"]
    assert {plan.weld_seams for plan in plans} == {1}
    assert {len(plan.panels) for plan in plans} == {2}
    assert all(not validate_split_reconstruction(plan.panels) for plan in plans)


def test_balanced_parts_reconstruct_parent_and_fit_stock():
    plan = generate_split_plans(make_job(), (make_panel(),))[0]
    assert sorted(panel.height for panel in plan.panels) == [125_300, 125_300]
    assert {panel.parent_panel_id for panel in plan.panels} == {"O-P-top-001"}
    assert [panel.piece_index for panel in plan.panels] == [1, 2]


def test_fitting_face_remains_one_piece_in_every_strategy():
    panel = make_panel(300_600, 130_000)
    plans = generate_split_plans(make_job(), (panel,))
    assert len(plans) == 1
    assert len(plans[0].panels) == 1 and plans[0].weld_seams == 0


def test_reconstruction_detects_missing_piece():
    plan = generate_split_plans(make_job(), (make_panel(),))[0]
    errors = validate_split_reconstruction(plan.panels[:1])
    assert errors and "O-P-top-001" in errors[0]
