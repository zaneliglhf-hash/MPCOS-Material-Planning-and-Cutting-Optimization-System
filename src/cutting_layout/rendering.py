from collections import Counter
from functools import lru_cache
from hashlib import sha256
from importlib.resources import as_file, files
from pathlib import Path
import re

from PIL import Image, ImageDraw, ImageFont

from .models import LayoutPlan, SheetInstance

A3_LANDSCAPE_PX = (3307, 2339)
WARNING_COLOR = (180, 32, 37)
BUNDLED_FONT_RESOURCE = ("fonts", "NotoSansSC-wght.ttf")


def color_for_product(product_id: str) -> tuple[int, int, int]:
    digest = sha256(product_id.encode("utf-8")).digest()
    return tuple(100 + value % 121 for value in digest[:3])


@lru_cache(maxsize=None)
def _font(size: int):
    resource = files("cutting_layout").joinpath(*BUNDLED_FONT_RESOURCE)
    with as_file(resource) as font_path:
        return ImageFont.truetype(str(font_path), size=size)


def _mm(units: int) -> str:
    return f"{units / 100:.2f}".rstrip("0").rstrip(".")


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_") or "sheet"


def _draw_dashed_rectangle(draw, box, fill=(100, 108, 120), width=4, dash=18):
    left, top, right, bottom = box
    for start in range(left, right, dash * 2):
        draw.line((start, top, min(start + dash, right), top), fill=fill, width=width)
        draw.line((start, bottom, min(start + dash, right), bottom), fill=fill, width=width)
    for start in range(top, bottom, dash * 2):
        draw.line((left, start, left, min(start + dash, bottom)), fill=fill, width=width)
        draw.line((right, start, right, min(start + dash, bottom)), fill=fill, width=width)


def _fit_font(draw, text, max_width, max_height, sizes=(34, 29, 24, 20)):
    for size in sizes:
        font = _font(size)
        box = draw.multiline_textbbox((0, 0), text, font=font, align="center", spacing=4)
        if box[2] - box[0] <= max_width and box[3] - box[1] <= max_height:
            return font
    return _font(18)


def _render_sheet(plan: LayoutPlan, sheet: SheetInstance, page_no: int, path: Path) -> Path:
    image = Image.new("RGB", A3_LANDSCAPE_PX, (240, 244, 249))
    draw = ImageDraw.Draw(image)
    warning = plan.provisional_notice or "排版结果"
    draw.rectangle((0, 0, image.width, 128), fill=WARNING_COLOR if plan.provisional_notice else (31, 78, 120))
    draw.text((image.width / 2, 64), warning, font=_font(46), fill="white", anchor="mm")

    panel_by_id = {panel.panel_id: panel for panel in plan.panels}
    placements = [placement for placement in plan.placements if placement.sheet_id == sheet.sheet_id]
    utilization = sum(p.width * p.height for p in placements) / (sheet.width * sheet.height)
    metadata = (
        f"板材 {page_no:03d}  {sheet.sheet_id}    规格 {_mm(sheet.width)} × {_mm(sheet.height)} mm    "
        f"分片 {len(placements)} 件    利用率 {utilization:.2%}"
    )
    draw.text((100, 188), metadata, font=_font(34), fill=(25, 38, 54), anchor="lm")

    diagram_left, diagram_top = 130, 280
    diagram_width, diagram_height = 3047, 770
    scale = min(diagram_width / sheet.width, diagram_height / sheet.height)
    stock_width = round(sheet.width * scale)
    stock_height = round(sheet.height * scale)
    origin_x = diagram_left + (diagram_width - stock_width) // 2
    origin_y = diagram_top + (diagram_height - stock_height) // 2
    draw.rectangle((origin_x, origin_y, origin_x + stock_width, origin_y + stock_height), fill="white", outline=(15, 23, 32), width=7)

    for placement in placements:
        panel = panel_by_id[placement.panel_id]
        box = (
            origin_x + round(placement.x * scale),
            origin_y + round(placement.y * scale),
            origin_x + round((placement.x + placement.width) * scale),
            origin_y + round((placement.y + placement.height) * scale),
        )
        fill = color_for_product(panel.product_id)
        outline = tuple(max(0, value - 65) for value in fill)
        draw.rectangle(box, fill=fill, outline=outline, width=5)
        piece = f"P{panel.piece_index}/{panel.piece_count}" if panel.piece_count > 1 else "整片"
        text = f"{panel.product_id}\n{panel.name}  {piece}\n{_mm(panel.width)}×{_mm(panel.height)}"
        font = _fit_font(draw, text, box[2] - box[0] - 12, box[3] - box[1] - 12)
        draw.multiline_text(((box[0] + box[2]) / 2, (box[1] + box[3]) / 2), text, font=font, fill=(15, 24, 34), anchor="mm", align="center", spacing=4)

    for remnant in (item for item in plan.remnants if item.sheet_id == sheet.sheet_id):
        box = (
            origin_x + round(remnant.x * scale), origin_y + round(remnant.y * scale),
            origin_x + round((remnant.x + remnant.width) * scale),
            origin_y + round((remnant.y + remnant.height) * scale),
        )
        _draw_dashed_rectangle(draw, box)

    draw.text((130, 1120), "本板分片清单（按箱体/箱面追溯）", font=_font(32), fill=(31, 78, 120))
    rows = []
    for placement in placements:
        panel = panel_by_id[placement.panel_id]
        rows.append(
            f"{panel.panel_id}  |  {_mm(panel.width)}×{_mm(panel.height)}  |  "
            f"完整面 {panel.parent_panel_id or panel.panel_id}  |  P{panel.piece_index}/{panel.piece_count}  |  旋转{placement.rotation}°"
        )
    columns = 2
    column_width = 1510
    line_height = 48
    max_rows = 19
    for index, row in enumerate(rows[: columns * max_rows]):
        column = index // max_rows
        line = index % max_rows
        draw.text((130 + column * column_width, 1170 + line * line_height), row, font=_font(20), fill=(42, 51, 64))
    if len(rows) > columns * max_rows:
        draw.text((image.width - 140, 2160), f"另有 {len(rows) - columns * max_rows} 件，详见Excel", font=_font(22), fill=WARNING_COLOR, anchor="ra")

    footer = (
        f"批次：{plan.batch_name}    第 {page_no}/{len(plan.sheets)} 张板    "
        f"分片策略：{plan.split_strategy}    总焊缝：{plan.weld_seams}    图例：彩色=切割件，灰色虚线=可保留余料"
    )
    draw.line((90, 2260, image.width - 90, 2260), fill=(170, 180, 192), width=2)
    draw.text((image.width / 2, 2295), footer, font=_font(21), fill=(49, 60, 73), anchor="mm")
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, "PNG", optimize=True, dpi=(200, 200))
    return path


def _render_overview(plan: LayoutPlan, sheet_paths: tuple[Path, ...], path: Path) -> Path:
    thumb_width, thumb_height = 1000, 706
    columns = 3
    rows = max(1, (len(sheet_paths) + columns - 1) // columns)
    header_height = 430
    height = header_height + rows * (thumb_height + 80) + 80
    image = Image.new("RGB", (3307, height), (234, 239, 245))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, image.width, 110), fill=WARNING_COLOR if plan.provisional_notice else (31, 78, 120))
    draw.text((image.width / 2, 55), plan.provisional_notice or "板材切割排版总览", font=_font(42), fill="white", anchor="mm")
    utilization = plan.metrics.panel_area / plan.metrics.opened_area if plan.metrics.opened_area else 0
    stock_counts = Counter(f"{_mm(sheet.width)}×{_mm(sheet.height)}" for sheet in plan.sheets)
    counts = "；".join(f"{size}：{count}张" for size, count in sorted(stock_counts.items()))
    draw.text((90, 155), f"批次：{plan.batch_name}", font=_font(38), fill=(23, 34, 48))
    draw.text((90, 215), f"共 {len(plan.sheets)} 张板 | {len(plan.panels)} 个切割分片 | {plan.weld_seams} 条拼焊缝 | 总利用率 {utilization:.2%}", font=_font(30), fill=(43, 54, 69))
    draw.text((90, 270), f"板材：{counts} | 废料 {plan.metrics.waste_area / 10_000_000_000:.2f} 平方米 | 分片策略 {plan.split_strategy}", font=_font(27), fill=(43, 54, 69))
    product_ids = sorted({panel.product_id for panel in plan.panels})
    x = 90
    for product_id in product_ids:
        draw.rectangle((x, 340, x + 40, 380), fill=color_for_product(product_id), outline=(40, 40, 40))
        draw.text((x + 50, 360), product_id, font=_font(20), fill=(43, 54, 69), anchor="lm")
        x += max(300, 70 + draw.textlength(product_id, font=_font(20)))
        if x > image.width - 350:
            break

    for index, sheet_path in enumerate(sheet_paths):
        with Image.open(sheet_path) as source:
            thumb = source.convert("RGB")
            thumb.thumbnail((thumb_width, thumb_height), Image.Resampling.LANCZOS)
        column, row = index % columns, index // columns
        x0 = 60 + column * 1090
        y0 = header_height + row * (thumb_height + 80)
        image.paste(thumb, (x0 + (thumb_width - thumb.width) // 2, y0))
        draw.text((x0 + thumb_width / 2, y0 + thumb_height + 30), f"第 {index + 1:03d} 张板", font=_font(25), fill=(35, 45, 58), anchor="mm")
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, "PNG", optimize=True, dpi=(150, 150))
    return path


def render_previews(plan: LayoutPlan, output_dir: Path) -> tuple[Path, ...]:
    output_dir.mkdir(parents=True, exist_ok=True)
    for stale in output_dir.glob("sheet-*.png"):
        stale.unlink()
    sheet_paths = tuple(
        _render_sheet(plan, sheet, index, output_dir / f"sheet-{index:03d}-{_safe_name(sheet.sheet_id)}.png")
        for index, sheet in enumerate(plan.sheets, start=1)
    )
    overview = _render_overview(plan, sheet_paths, output_dir / "preview-overview.png")
    return sheet_paths + (overview,)
