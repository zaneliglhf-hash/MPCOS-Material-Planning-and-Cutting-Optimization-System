import pytest
from PIL import Image

from cutting_layout.rendering import _font, color_for_product, render_previews


def test_rendering_uses_bundled_noto_sans_sc_font():
    family, _ = _font(20).getname()
    assert family == "Noto Sans SC"


def test_product_color_is_stable_and_distinct():
    assert color_for_product("BOX-A") == color_for_product("BOX-A")
    assert color_for_product("BOX-A") != color_for_product("BOX-B")


def test_render_creates_readable_sheet_and_overview_images(valid_plan, tmp_path):
    paths = render_previews(valid_plan, tmp_path)
    assert {path.name for path in paths} == {"sheet-001-S-001.png", "preview-overview.png"}
    for path in paths:
        with Image.open(path) as image:
            assert image.width >= 800
            assert image.height >= 500
            assert image.mode == "RGB"


def test_different_products_use_different_fills(valid_plan, tmp_path):
    paths = render_previews(valid_plan, tmp_path)
    sheet_path = next(path for path in paths if path.name.startswith("sheet-"))
    with Image.open(sheet_path) as image:
        colors = image.getcolors(maxcolors=image.width * image.height)
    assert colors is not None
    dominant = sorted(colors, reverse=True)[:10]
    assert len({color for _, color in dominant}) >= 3


def test_render_creates_a3_sheet_and_image_first_overview(split_valid_plan, tmp_path):
    paths = render_previews(split_valid_plan, tmp_path)
    sheet_paths = [path for path in paths if path.name.startswith("sheet-")]
    assert sheet_paths[0].name.startswith("sheet-001-")
    assert paths[-1].name == "preview-overview.png"
    with Image.open(sheet_paths[0]) as image:
        assert image.size == (3307, 2339)
        assert image.info.get("dpi") == pytest.approx((200, 200), rel=0.01)


def test_sheet_image_contains_warning_text_pixels(split_valid_plan, tmp_path):
    path = render_previews(split_valid_plan, tmp_path)[0]
    with Image.open(path) as image:
        warning_band = image.crop((0, 0, image.width, 180))
        assert len(warning_band.getcolors(maxcolors=warning_band.width * warning_band.height)) > 2


def test_render_removes_stale_numbered_sheet_images(valid_plan, tmp_path):
    stale = tmp_path / "sheet-999-old.png"
    stale.write_bytes(b"old")
    render_previews(valid_plan, tmp_path)
    assert not stale.exists()
