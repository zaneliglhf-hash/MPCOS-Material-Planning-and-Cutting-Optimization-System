import pytest

from cutting_layout.expansion import ExpansionError, expand_job, group_panels
from cutting_layout.models import Job, MaterialKey, PanelOverride, ProcessSettings, ProductSpec


KEY = MaterialKey("Q235", 200, "plain", "free")
SETTINGS = ProcessSettings(1000, 300, 150, 20_000, 20_000)


def product(basis="outer", faces=("top", "bottom", "front", "back", "left", "right")):
    return ProductSpec("A01", "BOX", 1, 120_000, 80_000, 60_000, basis, faces, KEY, True)


def job_with(item):
    return Job("demo", "fast", SETTINGS, (item,), (), (), ())


def dimensions_by_name(panels):
    return {panel.name: (panel.width, panel.height) for panel in panels}


def test_outer_dimensions_follow_approved_joint_rule():
    dims = dimensions_by_name(expand_job(job_with(product())))
    assert dims == {
        "top": (120_000, 80_000), "bottom": (120_000, 80_000),
        "front": (120_000, 59_600), "back": (120_000, 59_600),
        "left": (79_600, 59_600), "right": (79_600, 59_600),
    }


def test_inner_dimensions_reverse_compensate_thickness():
    dims = dimensions_by_name(expand_job(job_with(product("inner"))))
    assert dims["top"] == (120_400, 80_400)
    assert dims["front"] == (120_400, 60_000)
    assert dims["left"] == (80_000, 60_000)


def test_missing_face_is_not_generated():
    panels = expand_job(job_with(product(faces=("bottom", "front"))))
    assert [panel.name for panel in panels] == ["bottom", "front"]


def test_invalid_compensated_dimension_is_rejected():
    too_short = ProductSpec("A01", "BOX", 1, 10_000, 8_000, 300, "outer", ("front",), KEY, True)
    with pytest.raises(ExpansionError, match="A01-BOX-front"):
        expand_job(job_with(too_short))


def test_grouping_keeps_different_thicknesses_separate():
    panels = expand_job(job_with(product()))
    groups = group_panels(panels)
    assert list(groups) == [KEY]
    assert len(groups[KEY]) == 6


def test_face_override_replaces_dimensions_quantity_and_marks_source():
    override = PanelOverride("A01", "BOX", "left", 70_000, 50_000, 2, KEY, False)
    base = job_with(product(faces=("left",)))
    job = Job(base.batch_name, base.mode, base.settings, base.products, (), (override,), ())
    panels = expand_job(job)
    assert [(panel.width, panel.height, panel.source) for panel in panels] == [
        (70_000, 50_000, "override"), (70_000, 50_000, "override")
    ]


def test_expansion_rejects_more_than_two_thousand_panels():
    oversized = ProductSpec("A01", "BOX", 2001, 120_000, 80_000, 60_000, "outer", ("top",), KEY, True)
    with pytest.raises(ExpansionError, match="limit is 2000"):
        expand_job(job_with(oversized))


def test_expanded_face_is_its_own_unsplit_parent():
    panel = expand_job(job_with(product(faces=("top",))))[0]
    assert panel.parent_panel_id == panel.panel_id
    assert (panel.parent_width, panel.parent_height) == (panel.width, panel.height)
    assert (panel.piece_index, panel.piece_count) == (1, 1)
    assert panel.seam_group == panel.panel_id
