from dataclasses import dataclass
from typing import Literal

Face = Literal["top", "bottom", "front", "back", "left", "right"]
Mode = Literal["fast", "deep"]


@dataclass(frozen=True, order=True)
class MaterialKey:
    material: str
    thickness: int
    surface: str
    stock_direction: str


@dataclass(frozen=True)
class ProcessSettings:
    edge_margin: int
    part_gap: int
    kerf: int
    min_remnant_width: int
    min_remnant_height: int

    @property
    def clearance(self) -> int:
        return max(self.part_gap, self.kerf)


@dataclass(frozen=True)
class ProductSpec:
    order_id: str
    product_id: str
    quantity: int
    length: int
    width: int
    height: int
    dimension_basis: Literal["outer", "inner"]
    faces: tuple[Face, ...]
    material_key: MaterialKey
    rotation_allowed: bool


@dataclass(frozen=True)
class AccessorySpec:
    order_id: str
    product_id: str
    name: str
    quantity: int
    width: int
    height: int
    material_key: MaterialKey
    rotation_allowed: bool


@dataclass(frozen=True)
class StockSpec:
    stock_id: str
    kind: Literal["standard", "remnant"]
    quantity: int
    width: int
    height: int
    material_key: MaterialKey


@dataclass(frozen=True)
class PanelOverride:
    order_id: str
    product_id: str
    face: Face
    width: int
    height: int
    quantity: int
    material_key: MaterialKey
    rotation_allowed: bool


@dataclass(frozen=True)
class Job:
    batch_name: str
    mode: Mode
    settings: ProcessSettings
    products: tuple[ProductSpec, ...]
    accessories: tuple[AccessorySpec, ...]
    panel_overrides: tuple[PanelOverride, ...]
    stocks: tuple[StockSpec, ...]
    allow_panel_splitting: bool = False
    provisional_notice: str = ""


@dataclass(frozen=True)
class Panel:
    panel_id: str
    order_id: str
    product_id: str
    name: str
    instance_no: int
    width: int
    height: int
    material_key: MaterialKey
    rotation_allowed: bool
    source: Literal["generated", "override", "accessory"]
    parent_panel_id: str = ""
    parent_width: int = 0
    parent_height: int = 0
    piece_index: int = 1
    piece_count: int = 1
    seam_group: str = ""


@dataclass(frozen=True)
class SheetInstance:
    sheet_id: str
    stock_id: str
    kind: Literal["standard", "remnant"]
    width: int
    height: int
    material_key: MaterialKey


@dataclass(frozen=True)
class Placement:
    panel_id: str
    sheet_id: str
    x: int
    y: int
    width: int
    height: int
    rotation: Literal[0, 90]


@dataclass(frozen=True)
class RemnantRect:
    sheet_id: str
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True)
class LayoutMetrics:
    new_standard_sheets: int
    remnants_used: int
    opened_area: int
    panel_area: int
    waste_area: int
    reusable_remnant_area: int
    rapid_travel: float
    product_dispersion: int

    def score(self) -> tuple[int, int, int, int, float, int]:
        return (
            self.new_standard_sheets,
            -self.remnants_used,
            self.waste_area,
            -self.reusable_remnant_area,
            self.rapid_travel,
            self.product_dispersion,
        )


@dataclass(frozen=True)
class LayoutPlan:
    batch_name: str
    mode: Mode
    heuristic_note: str
    settings: ProcessSettings
    panels: tuple[Panel, ...]
    sheets: tuple[SheetInstance, ...]
    placements: tuple[Placement, ...]
    remnants: tuple[RemnantRect, ...]
    metrics: LayoutMetrics
    provisional_notice: str = ""
    split_strategy: str = "none"
    weld_seams: int = 0
