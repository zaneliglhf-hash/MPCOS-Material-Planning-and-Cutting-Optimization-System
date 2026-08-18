from dataclasses import dataclass
from typing import Literal

from .models import Panel, Placement, ProcessSettings, SheetInstance

SplitMode = Literal["shorter_leftover", "longer_leftover"]


@dataclass(frozen=True, order=True)
class FreeRect:
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True)
class PackedSheet:
    sheet: SheetInstance
    settings: ProcessSettings
    free_rects: tuple[FreeRect, ...]
    placements: tuple[Placement, ...] = ()


def new_packed_sheet(sheet: SheetInstance, settings: ProcessSettings) -> PackedSheet:
    gap = settings.clearance
    width = sheet.width - 2 * settings.edge_margin + gap
    height = sheet.height - 2 * settings.edge_margin + gap
    if width <= gap or height <= gap:
        raise ValueError(f"{sheet.sheet_id}: edge margin leaves no usable area")
    return PackedSheet(
        sheet,
        settings,
        (FreeRect(settings.edge_margin, settings.edge_margin, width, height),),
    )


def _orientations(panel: Panel):
    yield panel.width, panel.height, 0
    if panel.rotation_allowed and panel.width != panel.height:
        yield panel.height, panel.width, 90


def try_place(sheet: PackedSheet, panel: Panel, split_mode: SplitMode) -> PackedSheet | None:
    gap = sheet.settings.clearance
    candidates = []
    for free_index, free in enumerate(sheet.free_rects):
        for width, height, rotation in _orientations(panel):
            padded_width, padded_height = width + gap, height + gap
            if padded_width <= free.width and padded_height <= free.height:
                area_left = free.width * free.height - padded_width * padded_height
                short_left = min(free.width - padded_width, free.height - padded_height)
                candidates.append(
                    ((area_left, short_left, free.y, free.x, rotation), free_index, width, height, rotation)
                )
    if not candidates:
        return None

    _, free_index, width, height, rotation = min(candidates)
    free = sheet.free_rects[free_index]
    padded_width, padded_height = width + gap, height + gap
    horizontal_first = (free.width - padded_width) > (free.height - padded_height)
    if split_mode == "longer_leftover":
        horizontal_first = not horizontal_first

    if horizontal_first:
        pieces = (
            FreeRect(
                free.x + padded_width,
                free.y,
                free.width - padded_width,
                padded_height,
            ),
            FreeRect(
                free.x,
                free.y + padded_height,
                free.width,
                free.height - padded_height,
            ),
        )
    else:
        pieces = (
            FreeRect(
                free.x + padded_width,
                free.y,
                free.width - padded_width,
                free.height,
            ),
            FreeRect(
                free.x,
                free.y + padded_height,
                padded_width,
                free.height - padded_height,
            ),
        )

    remaining = list(sheet.free_rects[:free_index] + sheet.free_rects[free_index + 1:])
    remaining.extend(piece for piece in pieces if piece.width > gap and piece.height > gap)
    placement = Placement(
        panel.panel_id,
        sheet.sheet.sheet_id,
        free.x,
        free.y,
        width,
        height,
        rotation,
    )
    return PackedSheet(
        sheet=sheet.sheet,
        settings=sheet.settings,
        free_rects=tuple(sorted(remaining)),
        placements=sheet.placements + (placement,),
    )
