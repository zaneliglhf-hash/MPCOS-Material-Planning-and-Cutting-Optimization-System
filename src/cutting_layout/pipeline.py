from dataclasses import dataclass, replace
import json
import os
from pathlib import Path
import shutil
from typing import Callable

from .export_dxf import export_dxf
from .export_excel import export_excel
from .export_pdf import export_pdf
from .expansion import expand_job
from .formats import ALL_FORMATS
from .input_loader import load_job
from .models import LayoutPlan, MaterialKey
from .optimizer import optimize
from .output_transaction import OutputTransaction
from .rendering import render_previews
from .splitting import generate_split_plans
from .validation import validate_plan


class ExportError(RuntimeError):
    pass


@dataclass(frozen=True)
class OutputBundle:
    output_dir: Path
    result_json: Path | None
    overview_path: Path | None
    dxf_path: Path | None
    excel_path: Path | None
    pdf_path: Path | None


def _mm(units: int) -> float:
    return units / 100.0


def _material_dict(key: MaterialKey) -> dict:
    return {
        "material": key.material,
        "thickness_mm": _mm(key.thickness),
        "surface": key.surface,
        "stock_direction": key.stock_direction,
    }


def _result_payload(plan: LayoutPlan) -> dict:
    parent_face_ids = {panel.parent_panel_id or panel.panel_id for panel in plan.panels}
    return {
        "batch_name": plan.batch_name,
        "mode": plan.mode,
        "heuristic_note": plan.heuristic_note,
        "provisional_notice": plan.provisional_notice,
        "split_strategy": plan.split_strategy,
        "weld_seams": plan.weld_seams,
        "parent_face_count": len(parent_face_ids),
        "settings": {
            "edge_margin_mm": _mm(plan.settings.edge_margin),
            "part_gap_mm": _mm(plan.settings.part_gap),
            "kerf_mm": _mm(plan.settings.kerf),
            "effective_clearance_mm": _mm(plan.settings.clearance),
            "min_remnant_width_mm": _mm(plan.settings.min_remnant_width),
            "min_remnant_height_mm": _mm(plan.settings.min_remnant_height),
        },
        "metrics": {
            "new_standard_sheets": plan.metrics.new_standard_sheets,
            "remnants_used": plan.metrics.remnants_used,
            "opened_area_m2": plan.metrics.opened_area / 10_000_000_000,
            "panel_area_m2": plan.metrics.panel_area / 10_000_000_000,
            "waste_area_m2": plan.metrics.waste_area / 10_000_000_000,
            "reusable_remnant_area_m2": plan.metrics.reusable_remnant_area / 10_000_000_000,
            "rapid_travel_mm": _mm(round(plan.metrics.rapid_travel)),
            "product_dispersion": plan.metrics.product_dispersion,
        },
        "panel_count": len(plan.panels),
        "placement_count": len(plan.placements),
        "materials": [_material_dict(key) for key in sorted({panel.material_key for panel in plan.panels})],
        "panels": [
            {
                "panel_id": panel.panel_id,
                "order_id": panel.order_id,
                "product_id": panel.product_id,
                "name": panel.name,
                "source": panel.source,
                "width_mm": _mm(panel.width),
                "height_mm": _mm(panel.height),
                "rotation_allowed": panel.rotation_allowed,
                "parent_panel_id": panel.parent_panel_id or panel.panel_id,
                "parent_width_mm": _mm(panel.parent_width or panel.width),
                "parent_height_mm": _mm(panel.parent_height or panel.height),
                "piece_index": panel.piece_index,
                "piece_count": panel.piece_count,
                "seam_group": panel.seam_group or panel.panel_id,
                **_material_dict(panel.material_key),
            }
            for panel in plan.panels
        ],
        "sheets": [
            {
                "sheet_id": sheet.sheet_id,
                "stock_id": sheet.stock_id,
                "kind": sheet.kind,
                "width_mm": _mm(sheet.width),
                "height_mm": _mm(sheet.height),
                **_material_dict(sheet.material_key),
            }
            for sheet in plan.sheets
        ],
        "placements": [
            {
                "panel_id": placement.panel_id,
                "sheet_id": placement.sheet_id,
                "x_mm": _mm(placement.x),
                "y_mm": _mm(placement.y),
                "width_mm": _mm(placement.width),
                "height_mm": _mm(placement.height),
                "rotation": placement.rotation,
            }
            for placement in plan.placements
        ],
        "remnants": [
            {
                "sheet_id": remnant.sheet_id,
                "x_mm": _mm(remnant.x),
                "y_mm": _mm(remnant.y),
                "width_mm": _mm(remnant.width),
                "height_mm": _mm(remnant.height),
            }
            for remnant in plan.remnants
        ],
    }


def select_layout(job, full_panels) -> LayoutPlan:
    candidates: list[LayoutPlan] = []
    errors: list[Exception] = []
    standard_groups: dict[tuple, list] = {}
    remnants = tuple(stock for stock in job.stocks if stock.kind == "remnant")
    for stock in job.stocks:
        if stock.kind != "standard":
            continue
        key = (stock.material_key, stock.width, stock.height)
        standard_groups.setdefault(key, []).append(stock)
    stock_sets = [job.stocks]
    stock_sets.extend(remnants + tuple(group) for group in standard_groups.values())
    seen_stocks: set[tuple[str, ...]] = set()
    for stocks in stock_sets:
        signature = tuple(sorted(stock.stock_id for stock in stocks))
        if signature in seen_stocks:
            continue
        seen_stocks.add(signature)
        candidate_job = replace(job, stocks=tuple(stocks))
        for split in generate_split_plans(candidate_job, full_panels):
            try:
                plan = optimize(candidate_job, split.panels)
                stock_mix = ",".join(sorted({sheet.stock_id for sheet in plan.sheets}))
                plan = replace(
                    plan,
                    provisional_notice=job.provisional_notice,
                    split_strategy=split.strategy,
                    weld_seams=split.weld_seams,
                    heuristic_note=(
                        f"{plan.heuristic_note}; split strategy={split.strategy}; stock mix={stock_mix}"
                    ),
                )
                validate_plan(plan)
                candidates.append(plan)
            except Exception as exc:
                errors.append(exc)
    if not candidates:
        if errors:
            raise errors[0]
        raise RuntimeError("no split layout candidate was generated")
    return min(
        candidates,
        key=lambda plan: (
            plan.weld_seams,
            *plan.metrics.score(),
            plan.split_strategy,
        ),
    )


def _atomic_export(final_path: Path, writer: Callable[[Path], Path], format_name: str) -> Path:
    partial_path = final_path.with_name(f".{final_path.name}.partial")
    if partial_path.exists():
        partial_path.unlink()
    try:
        writer(partial_path)
        os.replace(partial_path, final_path)
    except Exception as exc:
        if partial_path.exists():
            partial_path.unlink()
        raise ExportError(f"{format_name} export failed: {exc}") from exc
    return final_path


def _write_result_json(plan: LayoutPlan, path: Path) -> Path:
    def writer(partial_path: Path) -> Path:
        partial_path.write_text(
            json.dumps(_result_payload(plan), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return partial_path

    return _atomic_export(path, writer, "result.json")


def run_pipeline(
    input_path: Path,
    output_dir: Path,
    formats: frozenset[str] = ALL_FORMATS,
) -> OutputBundle:
    job = load_job(input_path)
    panels = expand_job(job)
    plan = select_layout(job, panels)

    def final_path(staged_path: Path | None, staging_dir: Path) -> Path | None:
        if staged_path is None:
            return None
        return output_dir / staged_path.relative_to(staging_dir)

    try:
        with OutputTransaction(output_dir) as transaction:
            staging_dir = transaction.staging_dir
            previews: tuple[Path, ...] = ()
            overview_path: Path | None = None
            preview_dir = staging_dir / "previews"
            if formats & {"png", "pdf"}:
                try:
                    previews = render_previews(plan, preview_dir)
                except Exception as exc:
                    raise ExportError(f"PNG preview export failed: {exc}") from exc
                if "png" in formats:
                    overview_path = preview_dir / "preview-overview.png"

            dxf_path = None
            if "dxf" in formats:
                dxf_path = _atomic_export(
                    staging_dir / "layout-all.dxf",
                    lambda partial: export_dxf(plan, partial),
                    "DXF",
                )

            excel_path = None
            if "xlsx" in formats:
                excel_path = _atomic_export(
                    staging_dir / "parts.xlsx",
                    lambda partial: export_excel(plan, partial),
                    "Excel",
                )

            pdf_path = None
            if "pdf" in formats:
                try:
                    pdf_path = _atomic_export(
                        staging_dir / "cutting-report.pdf",
                        lambda partial: export_pdf(plan, previews, partial),
                        "PDF",
                    )
                finally:
                    if "png" not in formats:
                        shutil.rmtree(preview_dir, ignore_errors=True)

            result_json = None
            if "json" in formats:
                result_json = _write_result_json(plan, staging_dir / "result.json")

            transaction.commit()
            result_json = final_path(result_json, staging_dir)
            overview_path = final_path(overview_path, staging_dir)
            dxf_path = final_path(dxf_path, staging_dir)
            excel_path = final_path(excel_path, staging_dir)
            pdf_path = final_path(pdf_path, staging_dir)
    except ExportError:
        raise
    except Exception as exc:
        raise ExportError(f"output directory transaction failed: {exc}") from exc

    return OutputBundle(
        output_dir=output_dir,
        result_json=result_json,
        overview_path=overview_path,
        dxf_path=dxf_path,
        excel_path=excel_path,
        pdf_path=pdf_path,
    )
