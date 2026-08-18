from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
from typing import Any

from .models import (
    AccessorySpec,
    Face,
    Job,
    MaterialKey,
    PanelOverride,
    ProcessSettings,
    ProductSpec,
    StockSpec,
)
from .schema_validation import validate_job_payload

VALID_FACES = ("top", "bottom", "front", "back", "left", "right")


class InputError(ValueError):
    pass


def _mm_decimal_to_units(value: object, field: str) -> int:
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise InputError(f"{field}: expected a millimetre number") from exc
    scaled = decimal_value * 100
    if scaled != scaled.to_integral_value():
        raise InputError(f"{field}: use at most two decimal places")
    units = int(scaled)
    return units


def mm_to_units(value: object, field: str) -> int:
    units = _mm_decimal_to_units(value, field)
    if units <= 0:
        raise InputError(f"{field}: must be greater than zero")
    return units


def mm_to_nonnegative_units(value: object, field: str) -> int:
    units = _mm_decimal_to_units(value, field)
    if units < 0:
        raise InputError(f"{field}: must be zero or greater")
    return units


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise InputError(f"{field}: expected an object")
    return value


def _list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise InputError(f"{field}: expected a list")
    return value


def _required_text(raw: dict[str, Any], name: str, field: str) -> str:
    value = raw.get(name)
    if not isinstance(value, str) or not value.strip():
        raise InputError(f"{field}.{name}: required non-empty text")
    return value.strip()


def _positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise InputError(f"{field}: must be a positive integer")
    return value


def _boolean(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise InputError(f"{field}: expected true or false")
    return value


def _material_key(raw: dict[str, Any], field: str, rotation_allowed: bool) -> MaterialKey:
    direction = raw.get("stock_direction")
    if direction is None:
        direction = "free" if rotation_allowed else "length"
    if not isinstance(direction, str) or not direction.strip():
        raise InputError(f"{field}.stock_direction: required non-empty text")
    return MaterialKey(
        material=_required_text(raw, "material", field),
        thickness=mm_to_units(raw.get("thickness_mm"), f"{field}.thickness_mm"),
        surface=_required_text(raw, "surface", field),
        stock_direction=direction.strip(),
    )


def _parse_product(value: Any, index: int) -> ProductSpec:
    field = f"products[{index}]"
    raw = _mapping(value, field)
    rotation_allowed = _boolean(raw.get("rotation_allowed"), f"{field}.rotation_allowed")
    basis = raw.get("dimension_basis")
    if basis not in ("outer", "inner"):
        raise InputError(f"{field}.dimension_basis: expected 'outer' or 'inner'")
    faces_raw = _list(raw.get("faces"), f"{field}.faces")
    if not faces_raw:
        raise InputError(f"{field}.faces: select at least one face")
    if any(face not in VALID_FACES for face in faces_raw):
        raise InputError(f"{field}.faces: allowed values are {', '.join(VALID_FACES)}")
    if len(set(faces_raw)) != len(faces_raw):
        raise InputError(f"{field}.faces: duplicate face")
    return ProductSpec(
        order_id=_required_text(raw, "order_id", field),
        product_id=_required_text(raw, "product_id", field),
        quantity=_positive_int(raw.get("quantity"), f"{field}.quantity"),
        length=mm_to_units(raw.get("length_mm"), f"{field}.length_mm"),
        width=mm_to_units(raw.get("width_mm"), f"{field}.width_mm"),
        height=mm_to_units(raw.get("height_mm"), f"{field}.height_mm"),
        dimension_basis=basis,
        faces=tuple(faces_raw),
        material_key=_material_key(raw, field, rotation_allowed),
        rotation_allowed=rotation_allowed,
    )


def _parse_accessory(value: Any, index: int) -> AccessorySpec:
    field = f"accessories[{index}]"
    raw = _mapping(value, field)
    rotation_allowed = _boolean(raw.get("rotation_allowed"), f"{field}.rotation_allowed")
    return AccessorySpec(
        order_id=_required_text(raw, "order_id", field),
        product_id=_required_text(raw, "product_id", field),
        name=_required_text(raw, "name", field),
        quantity=_positive_int(raw.get("quantity"), f"{field}.quantity"),
        width=mm_to_units(raw.get("width_mm"), f"{field}.width_mm"),
        height=mm_to_units(raw.get("height_mm"), f"{field}.height_mm"),
        material_key=_material_key(raw, field, rotation_allowed),
        rotation_allowed=rotation_allowed,
    )


def _parse_panel_override(value: Any, index: int) -> PanelOverride:
    field = f"panel_overrides[{index}]"
    raw = _mapping(value, field)
    rotation_allowed = _boolean(raw.get("rotation_allowed"), f"{field}.rotation_allowed")
    face = raw.get("face")
    if face not in VALID_FACES:
        raise InputError(f"{field}.face: allowed values are {', '.join(VALID_FACES)}")
    return PanelOverride(
        order_id=_required_text(raw, "order_id", field),
        product_id=_required_text(raw, "product_id", field),
        face=face,
        width=mm_to_units(raw.get("width_mm"), f"{field}.width_mm"),
        height=mm_to_units(raw.get("height_mm"), f"{field}.height_mm"),
        quantity=_positive_int(raw.get("quantity"), f"{field}.quantity"),
        material_key=_material_key(raw, field, rotation_allowed),
        rotation_allowed=rotation_allowed,
    )


def _parse_stock(value: Any, index: int) -> StockSpec:
    field = f"stocks[{index}]"
    raw = _mapping(value, field)
    kind = raw.get("kind")
    if kind not in ("standard", "remnant"):
        raise InputError(f"{field}.kind: expected 'standard' or 'remnant'")
    rotation_allowed = raw.get("stock_direction", "free") == "free"
    return StockSpec(
        stock_id=_required_text(raw, "stock_id", field),
        kind=kind,
        quantity=_positive_int(raw.get("quantity"), f"{field}.quantity"),
        width=mm_to_units(raw.get("width_mm"), f"{field}.width_mm"),
        height=mm_to_units(raw.get("height_mm"), f"{field}.height_mm"),
        material_key=_material_key(raw, field, rotation_allowed),
    )


def _parse_settings(value: Any) -> ProcessSettings:
    field = "settings"
    raw = _mapping(value, field)
    return ProcessSettings(
        edge_margin=mm_to_nonnegative_units(raw.get("edge_margin_mm"), f"{field}.edge_margin_mm"),
        part_gap=mm_to_units(raw.get("part_gap_mm"), f"{field}.part_gap_mm"),
        kerf=mm_to_units(raw.get("kerf_mm"), f"{field}.kerf_mm"),
        min_remnant_width=mm_to_units(raw.get("min_remnant_width_mm"), f"{field}.min_remnant_width_mm"),
        min_remnant_height=mm_to_units(raw.get("min_remnant_height_mm"), f"{field}.min_remnant_height_mm"),
    )


def _parse_job(value: Any) -> Job:
    raw = _mapping(value, "job")
    mode = raw.get("mode")
    if mode not in ("fast", "deep"):
        raise InputError("mode: expected 'fast' or 'deep'")
    products_raw = _list(raw.get("products"), "products")
    if len(products_raw) > 100:
        raise InputError("products: first version supports at most 100 products")
    accessories_raw = _list(raw.get("accessories"), "accessories")
    overrides_raw = _list(raw.get("panel_overrides"), "panel_overrides")
    stocks_raw = _list(raw.get("stocks"), "stocks")
    if not products_raw and not accessories_raw:
        raise InputError("job: provide at least one product or accessory")
    if not stocks_raw:
        raise InputError("stocks: provide at least one stock specification")
    products = tuple(_parse_product(item, index) for index, item in enumerate(products_raw))
    accessories = tuple(_parse_accessory(item, index) for index, item in enumerate(accessories_raw))
    overrides = tuple(_parse_panel_override(item, index) for index, item in enumerate(overrides_raw))
    stocks = tuple(_parse_stock(item, index) for index, item in enumerate(stocks_raw))
    override_keys = [(item.order_id, item.product_id, item.face) for item in overrides]
    if len(set(override_keys)) != len(override_keys):
        raise InputError("panel_overrides: duplicate order/product/face override")
    product_keys = {(item.order_id, item.product_id) for item in products}
    for item in overrides:
        if (item.order_id, item.product_id) not in product_keys:
            raise InputError(f"panel_overrides: unknown product {item.order_id}/{item.product_id}")
    allow_panel_splitting = raw.get("allow_panel_splitting", False)
    if not isinstance(allow_panel_splitting, bool):
        raise InputError("allow_panel_splitting: expected true or false")
    provisional_notice = raw.get("provisional_notice", "")
    if not isinstance(provisional_notice, str):
        raise InputError("provisional_notice: expected text")
    return Job(
        batch_name=_required_text(raw, "batch_name", "job"),
        mode=mode,
        settings=_parse_settings(raw.get("settings")),
        products=products,
        accessories=accessories,
        panel_overrides=overrides,
        stocks=stocks,
        allow_panel_splitting=allow_panel_splitting,
        provisional_notice=provisional_notice.strip(),
    )


def load_job(path: Path) -> Job:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InputError(f"input file: {exc}") from exc
    try:
        validate_job_payload(raw)
    except ValueError as exc:
        raise InputError(str(exc)) from exc
    return _parse_job(raw)
