import pytest
from pypdf import PdfReader
from reportlab.lib.pagesizes import A3, landscape

from cutting_layout.export_pdf import export_pdf
from cutting_layout.rendering import render_previews


def test_pdf_contains_summary_sheet_page_and_batch_name(valid_plan, tmp_path):
    previews = render_previews(valid_plan, tmp_path / "preview")
    path = export_pdf(valid_plan, previews, tmp_path / "cutting-report.pdf")
    reader = PdfReader(path)
    assert len(reader.pages) >= 2
    extracted = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert valid_plan.batch_name in extracted
    assert valid_plan.sheets[0].sheet_id in extracted


def test_pdf_embeds_every_sheet_preview(valid_plan, tmp_path):
    previews = render_previews(valid_plan, tmp_path / "preview")
    path = export_pdf(valid_plan, previews, tmp_path / "cutting-report.pdf")
    reader = PdfReader(path)
    image_count = sum(len(page.images) for page in reader.pages)
    assert image_count >= len(valid_plan.sheets)


def test_pdf_is_a3_landscape_with_one_page_per_sheet(split_valid_plan, tmp_path):
    previews = render_previews(split_valid_plan, tmp_path / "preview")
    path = export_pdf(split_valid_plan, previews, tmp_path / "worker-a3.pdf")
    reader = PdfReader(path)
    expected_width, expected_height = landscape(A3)
    assert len(reader.pages) == 1 + len(split_valid_plan.sheets)
    for page in reader.pages:
        assert float(page.mediabox.width) == pytest.approx(expected_width, abs=1)
        assert float(page.mediabox.height) == pytest.approx(expected_height, abs=1)
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert "禁止直接下料" in text
