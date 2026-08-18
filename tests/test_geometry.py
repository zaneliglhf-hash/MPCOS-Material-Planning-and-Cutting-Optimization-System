from cutting_layout.geometry import FreeRect, new_packed_sheet, try_place
from cutting_layout.models import MaterialKey, Panel, ProcessSettings, SheetInstance


KEY = MaterialKey("Q235", 200, "plain", "free")
SETTINGS = ProcessSettings(1_000, 300, 150, 20_000, 20_000)
SHEET = SheetInstance("S-001", "STD", "standard", 100_000, 80_000, KEY)


def panel(panel_id, width, height, rotate=True):
    return Panel(panel_id, "O", "P", "face", 1, width, height, KEY, rotate, "generated")


def test_new_sheet_applies_edge_margin_and_clearance_compensation():
    packed = new_packed_sheet(SHEET, SETTINGS)
    assert packed.free_rects == (FreeRect(1_000, 1_000, 98_300, 78_300),)


def test_place_uses_rotation_when_only_rotated_shape_fits():
    packed = new_packed_sheet(SHEET, SETTINGS)
    placed = try_place(packed, panel("P1", 78_000, 90_000), "shorter_leftover")
    assert placed is not None
    assert placed.placements[0].rotation == 90


def test_direction_locked_panel_does_not_rotate():
    packed = new_packed_sheet(SHEET, SETTINGS)
    assert try_place(packed, panel("P1", 78_000, 90_000, False), "shorter_leftover") is None


def test_two_placed_panels_have_disjoint_real_rectangles():
    first = try_place(new_packed_sheet(SHEET, SETTINGS), panel("P1", 40_000, 30_000), "shorter_leftover")
    second = try_place(first, panel("P2", 40_000, 30_000), "shorter_leftover")
    a, b = second.placements
    assert (
        a.x + a.width + SETTINGS.clearance <= b.x
        or b.x + b.width + SETTINGS.clearance <= a.x
        or a.y + a.height + SETTINGS.clearance <= b.y
        or b.y + b.height + SETTINGS.clearance <= a.y
    )


def test_guillotine_free_rectangles_remain_disjoint():
    packed = new_packed_sheet(SHEET, SETTINGS)
    for index in range(5):
        packed = try_place(packed, panel(f"P{index}", 10_000, 10_000), "longer_leftover")
        assert packed is not None
    for index, first in enumerate(packed.free_rects):
        for second in packed.free_rects[index + 1:]:
            assert (
                first.x + first.width <= second.x
                or second.x + second.width <= first.x
                or first.y + first.height <= second.y
                or second.y + second.height <= first.y
            )
