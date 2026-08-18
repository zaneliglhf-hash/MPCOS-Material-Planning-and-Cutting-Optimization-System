from collections import Counter
from importlib.resources import as_file, files
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A3, landscape
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from .models import LayoutPlan

PDF_FONT_RESOURCE = ("fonts", "NotoSansSC-wght.ttf")


def _register_font() -> str:
    name = "CuttingLayoutCJK"
    if name in pdfmetrics.getRegisteredFontNames():
        return name
    resource = files("cutting_layout").joinpath(*PDF_FONT_RESOURCE)
    with as_file(resource) as font_path:
        pdfmetrics.registerFont(TTFont(name, str(font_path)))
    return name


def _mm(units: int) -> str:
    return f"{units / 100:.2f}".rstrip("0").rstrip(".")


def _draw_image_fit(pdf, image_path: Path, x: float, y: float, width: float, height: float) -> None:
    image = ImageReader(str(image_path))
    image_width, image_height = image.getSize()
    scale = min(width / image_width, height / image_height)
    drawn_width = image_width * scale
    drawn_height = image_height * scale
    pdf.drawImage(
        image,
        x + (width - drawn_width) / 2,
        y + (height - drawn_height) / 2,
        drawn_width,
        drawn_height,
        preserveAspectRatio=True,
        mask="auto",
    )


def _footer(pdf, font_name: str, plan: LayoutPlan, page: int, total: int) -> None:
    page_width, _ = landscape(A3)
    pdf.setFont(font_name, 9)
    pdf.setFillColor(colors.HexColor("#435164"))
    pdf.drawCentredString(page_width / 2, 18, f"{plan.batch_name}    第 {page}/{total} 页")


def export_pdf(plan: LayoutPlan, preview_paths: tuple[Path, ...], path: Path) -> Path:
    sheet_previews = [item for item in preview_paths if item.name.startswith("sheet-")]
    overview = next((item for item in preview_paths if item.name == "preview-overview.png"), None)
    if len(sheet_previews) != len(plan.sheets) or overview is None:
        raise ValueError("preview count does not match sheet count")
    path.parent.mkdir(parents=True, exist_ok=True)
    page_size = landscape(A3)
    page_width, page_height = page_size
    font_name = _register_font()
    total_pages = 1 + len(plan.sheets)
    pdf = canvas.Canvas(str(path), pagesize=page_size, pageCompression=1)
    pdf.setTitle(f"{plan.batch_name} A3 cutting layout")

    pdf.setFillColor(colors.HexColor("#B42025") if plan.provisional_notice else colors.HexColor("#1F4E78"))
    pdf.rect(0, page_height - 46, page_width, 46, fill=1, stroke=0)
    pdf.setFillColor(colors.white)
    pdf.setFont(font_name, 22)
    pdf.drawCentredString(page_width / 2, page_height - 31, plan.provisional_notice or "板材切割排版报告")
    pdf.setFillColor(colors.HexColor("#17324D"))
    pdf.setFont(font_name, 22)
    pdf.drawString(35, page_height - 79, f"批次总览：{plan.batch_name}")
    utilization = plan.metrics.panel_area / plan.metrics.opened_area if plan.metrics.opened_area else 0
    counts = Counter(f"{_mm(sheet.width)}×{_mm(sheet.height)}" for sheet in plan.sheets)
    count_text = "；".join(f"{size} {count}张" for size, count in sorted(counts.items()))
    pdf.setFont(font_name, 12)
    pdf.drawString(35, page_height - 105, f"板材 {len(plan.sheets)} 张（{count_text}）  分片 {len(plan.panels)} 件  焊缝 {plan.weld_seams} 条")
    pdf.drawString(35, page_height - 126, f"利用率 {utilization:.2%}  废料 {plan.metrics.waste_area / 10_000_000_000:.2f} 平方米  分片策略 {plan.split_strategy}")
    _draw_image_fit(pdf, overview, 30, 38, page_width - 60, page_height - 180)
    _footer(pdf, font_name, plan, 1, total_pages)
    pdf.showPage()

    for page_index, (sheet, preview) in enumerate(zip(plan.sheets, sheet_previews, strict=True), start=2):
        pdf.setFillColor(colors.HexColor("#B42025") if plan.provisional_notice else colors.HexColor("#1F4E78"))
        pdf.rect(0, page_height - 38, page_width, 38, fill=1, stroke=0)
        pdf.setFillColor(colors.white)
        pdf.setFont(font_name, 18)
        pdf.drawCentredString(page_width / 2, page_height - 26, plan.provisional_notice or "板材切割排版")
        pdf.setFillColor(colors.HexColor("#17324D"))
        pdf.setFont(font_name, 14)
        pdf.drawString(30, page_height - 61, f"板材 {page_index - 1:03d}：{sheet.sheet_id}    {_mm(sheet.width)}×{_mm(sheet.height)} mm")
        _draw_image_fit(pdf, preview, 24, 32, page_width - 48, page_height - 105)
        _footer(pdf, font_name, plan, page_index, total_pages)
        pdf.showPage()
    pdf.save()
    return path
