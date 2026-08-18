import ezdxf

from cutting_layout.export_dxf import export_dxf


def test_dxf_round_trip_contains_sheet_part_label_and_remnant_layers(valid_plan, tmp_path):
    path = export_dxf(valid_plan, tmp_path / "layout-all.dxf")
    doc = ezdxf.readfile(path)
    assert doc.units == ezdxf.units.MM
    assert all(doc.layers.has_entry(name) for name in ("SHEET", "PART", "LABEL", "REMNANT"))
    modelspace = doc.modelspace()
    assert len(modelspace.query('LWPOLYLINE[layer=="SHEET"]')) == len(valid_plan.sheets)
    assert len(modelspace.query('LWPOLYLINE[layer=="PART"]')) == len(valid_plan.placements)
    labels = [entity.dxf.text for entity in modelspace.query('TEXT[layer=="LABEL"]')]
    assert set(panel.panel_id for panel in valid_plan.panels).issubset(labels)


def test_dxf_part_extents_match_placement_dimensions(valid_plan, tmp_path):
    path = export_dxf(valid_plan, tmp_path / "layout-all.dxf")
    doc = ezdxf.readfile(path)
    part_polylines = list(doc.modelspace().query('LWPOLYLINE[layer=="PART"]'))
    first_points = list(part_polylines[0].get_points("xy"))
    xs = [point[0] for point in first_points]
    ys = [point[1] for point in first_points]
    first = valid_plan.placements[0]
    assert round(max(xs) - min(xs), 6) == first.width / 100
    assert round(max(ys) - min(ys), 6) == first.height / 100


def test_dxf_contains_provisional_warning_and_piece_sequence(split_valid_plan, tmp_path):
    doc = ezdxf.readfile(export_dxf(split_valid_plan, tmp_path / "layout.dxf"))
    labels = [entity.dxf.text for entity in doc.modelspace().query('TEXT[layer=="LABEL"]')]
    assert any("禁止直接下料" in value for value in labels)
    assert any("P1/2" in value for value in labels)
