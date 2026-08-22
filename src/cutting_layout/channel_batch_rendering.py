from __future__ import annotations

import csv
import math
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .channel_batch import ChannelBatchPlan


PAGE_SIZE = (2480, 1754)
ROWS_PER_PAGE = 10
COLORS = (
    "#3b82f6",
    "#10b981",
    "#f59e0b",
    "#ef4444",
    "#8b5cf6",
    "#06b6d4",
    "#f97316",
    "#84cc16",
    "#ec4899",
    "#6366f1",
)


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    candidates = (
        Path(r"C:\Windows\Fonts\msyhbd.ttc" if bold else r"C:\Windows\Fonts\msyh.ttc"),
        Path(r"C:\Windows\Fonts\simhei.ttf"),
    )
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default()


def write_channel_batch_csv(
    plan: ChannelBatchPlan,
    output_path: str | Path,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "批次",
                "原料长度(mm)",
                "同批根数",
                "单根切割顺序(mm)",
                "单根件数",
                "本批落锯次数",
                "单根锯缝(mm)",
                "单根余料(mm)",
                "本批成品数量",
                "本批原料总长(mm)",
                "本批余料总长(mm)",
            ]
        )
        for number, batch in enumerate(plan.batches, 1):
            writer.writerow(
                [
                    number,
                    batch.stock_length,
                    batch.multiplicity,
                    "+".join(map(str, batch.pieces_per_bar)),
                    len(batch.pieces_per_bar),
                    batch.cuts,
                    batch.cuts * batch.kerf,
                    batch.offcut_per_bar,
                    batch.cuts * batch.multiplicity,
                    batch.stock_length * batch.multiplicity,
                    batch.offcut_per_bar * batch.multiplicity,
                ]
            )
    return path


def _draw_page(
    plan: ChannelBatchPlan,
    batches: tuple,
    *,
    page_number: int,
    page_count: int,
    title: str,
    output_path: Path,
    baseline_batches: int,
    baseline_strokes: int,
) -> None:
    width, height = PAGE_SIZE
    image = Image.new("RGB", PAGE_SIZE, "#f8fafc")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, width, 190), fill="#0f172a")
    draw.text((65, 28), title, font=_font(46, True), fill="white")
    draw.text(
        (2050, 42),
        f"第 {page_number}/{page_count} 页",
        font=_font(30, True),
        fill="#bfdbfe",
    )

    procurement = plan.procurement_counts
    handling_saved = max(0, baseline_batches - plan.batch_count)
    strokes_saved = max(0, baseline_strokes - plan.saw_strokes)
    procurement_text = " + ".join(
        f"{length}×{count}根" for length, count in sorted(procurement.items(), reverse=True)
    )
    summary = (
        f"进料：{procurement_text} = {plan.bar_count}根    "
        f"上下料：{plan.batch_count}批（省{handling_saved}批）    "
        f"落锯：{plan.saw_strokes}次（省{strokes_saved}次）"
    )
    draw.text((65, 100), summary, font=_font(23, True), fill="#dbeafe")
    detail = (
        f"成品：{sum(len(batch.pieces_per_bar) * batch.multiplicity for batch in plan.batches)}件    "
        f"锯缝：{plan.total_kerf}mm    总余料：{plan.total_offcut}mm    "
        f"成材利用率：{plan.utilization_percent:.2f}%"
    )
    draw.text((65, 144), detail, font=_font(20), fill="#cbd5e1")

    top = 210
    row_height = 111
    bar_left, bar_right = 330, 2130
    bar_width = bar_right - bar_left
    for row, (absolute_index, batch) in enumerate(batches):
        y = top + row * row_height
        draw.rounded_rectangle(
            (25, y, width - 25, y + row_height - 8),
            radius=10,
            fill="#ffffff",
            outline="#cbd5e1",
            width=2,
        )
        draw.text((45, y + 20), f"批{absolute_index:02d}", font=_font(27, True), fill="#0f172a")
        draw.text(
            (145, y + 14),
            f"×{batch.multiplicity}根",
            font=_font(31, True),
            fill="#b91c1c",
        )
        draw.text(
            (150, y + 59),
            f"原料{batch.stock_length}",
            font=_font(18, True),
            fill="#334155",
        )

        bar_y1, bar_y2 = y + 14, y + 56
        draw.rounded_rectangle(
            (bar_left, bar_y1, bar_right, bar_y2),
            radius=7,
            fill="#e2e8f0",
            outline="#64748b",
            width=2,
        )
        cursor = bar_left
        scale = bar_width / max(batch.stock_length, 1)
        for piece_index, piece in enumerate(batch.pieces_per_bar):
            segment_width = piece * scale
            x2 = cursor + segment_width
            color = COLORS[(absolute_index + piece_index) % len(COLORS)]
            draw.rectangle((cursor, bar_y1 + 1, x2, bar_y2 - 1), fill=color)
            if segment_width >= 70:
                label = str(piece)
                label_font = _font(17, True)
                bbox = draw.textbbox((0, 0), label, font=label_font)
                draw.text(
                    (
                        cursor + (segment_width - (bbox[2] - bbox[0])) / 2,
                        bar_y1 + 8,
                    ),
                    label,
                    font=label_font,
                    fill="white",
                )
            cursor = x2 + batch.kerf * scale

        sequence = " + ".join(map(str, batch.pieces_per_bar))
        draw.text(
            (bar_left, y + 65),
            f"连续切：{sequence}",
            font=_font(18),
            fill="#334155",
        )
        draw.text(
            (2160, y + 17),
            f"落锯{batch.cuts}次",
            font=_font(19, True),
            fill="#1d4ed8",
        )
        draw.text(
            (2160, y + 55),
            f"单根余{batch.offcut_per_bar}",
            font=_font(18, True),
            fill="#166534" if batch.offcut_per_bar <= 300 else "#b91c1c",
        )

    draw.rectangle((0, height - 76, width, height), fill="#e2e8f0")
    draw.text(
        (55, height - 55),
        "操作：按批次整批上料并对齐；同批所有槽钢连续切完后整批下料，中途不拆批。净尺寸已按每件3mm锯缝核算。",
        font=_font(20, True),
        fill="#7f1d1d",
    )
    image.save(output_path, dpi=(150, 150), optimize=True)


def render_channel_batch_pages(
    plan: ChannelBatchPlan,
    output_dir: str | Path,
    title: str,
    *,
    baseline_batches: int = 35,
    baseline_strokes: int = 129,
) -> list[Path]:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    safe_title = re.sub(r"[\\/:*?\"<>|]+", "_", title).strip() or "channel-batch-plan"
    page_count = math.ceil(plan.batch_count / ROWS_PER_PAGE)
    paths: list[Path] = []
    indexed = tuple(enumerate(plan.batches, 1))
    for page_number in range(1, page_count + 1):
        start = (page_number - 1) * ROWS_PER_PAGE
        page_batches = indexed[start : start + ROWS_PER_PAGE]
        path = directory / f"{safe_title}_A3_第{page_number}页.png"
        _draw_page(
            plan,
            page_batches,
            page_number=page_number,
            page_count=page_count,
            title=title,
            output_path=path,
            baseline_batches=baseline_batches,
            baseline_strokes=baseline_strokes,
        )
        paths.append(path)
    return paths
