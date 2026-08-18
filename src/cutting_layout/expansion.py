from collections import defaultdict
from dataclasses import replace

from .models import Job, MaterialKey, Panel, ProductSpec


class ExpansionError(ValueError):
    pass


def _with_parent_trace(panel: Panel) -> Panel:
    return replace(
        panel,
        parent_panel_id=panel.panel_id,
        parent_width=panel.width,
        parent_height=panel.height,
        seam_group=panel.panel_id,
    )


def _face_dimensions(product: ProductSpec) -> dict[str, tuple[int, int]]:
    t = product.material_key.thickness
    if product.dimension_basis == "outer":
        return {
            "top": (product.length, product.width),
            "bottom": (product.length, product.width),
            "front": (product.length, product.height - 2 * t),
            "back": (product.length, product.height - 2 * t),
            "left": (product.width - 2 * t, product.height - 2 * t),
            "right": (product.width - 2 * t, product.height - 2 * t),
        }
    return {
        "top": (product.length + 2 * t, product.width + 2 * t),
        "bottom": (product.length + 2 * t, product.width + 2 * t),
        "front": (product.length + 2 * t, product.height),
        "back": (product.length + 2 * t, product.height),
        "left": (product.width, product.height),
        "right": (product.width, product.height),
    }


def expand_job(job: Job) -> tuple[Panel, ...]:
    panels: list[Panel] = []
    overrides = {(item.order_id, item.product_id, item.face): item for item in job.panel_overrides}
    used_overrides: set[tuple[str, str, str]] = set()
    for product in job.products:
        dimensions = _face_dimensions(product)
        for name in product.faces:
            key = (product.order_id, product.product_id, name)
            override = overrides.get(key)
            if override:
                used_overrides.add(key)
            width, height = (override.width, override.height) if override else dimensions[name]
            if width <= 0 or height <= 0:
                raise ExpansionError(
                    f"{product.order_id}-{product.product_id}-{name}: compensated dimension is not positive"
                )
            quantity = override.quantity if override else product.quantity
            material_key = override.material_key if override else product.material_key
            rotation_allowed = override.rotation_allowed if override else product.rotation_allowed
            source = "override" if override else "generated"
            for instance_no in range(1, quantity + 1):
                panel_id = f"{product.order_id}-{product.product_id}-{name}-{instance_no:03d}"
                panels.append(
                    _with_parent_trace(Panel(
                        panel_id,
                        product.order_id,
                        product.product_id,
                        name,
                        instance_no,
                        width,
                        height,
                        material_key,
                        rotation_allowed,
                        source,
                    ))
                )
    unused_overrides = set(overrides) - used_overrides
    if unused_overrides:
        order_id, product_id, face = sorted(unused_overrides)[0]
        raise ExpansionError(f"{order_id}-{product_id}-{face}: override targets a face not selected by the product")
    for accessory in job.accessories:
        for instance_no in range(1, accessory.quantity + 1):
            panel_id = f"{accessory.order_id}-{accessory.product_id}-{accessory.name}-{instance_no:03d}"
            panels.append(
                _with_parent_trace(Panel(
                    panel_id,
                    accessory.order_id,
                    accessory.product_id,
                    accessory.name,
                    instance_no,
                    accessory.width,
                    accessory.height,
                    accessory.material_key,
                    accessory.rotation_allowed,
                    "accessory",
                ))
            )
    if len(panels) > 2_000:
        raise ExpansionError(f"batch expands to {len(panels)} panels; first version limit is 2000")
    panel_ids = [panel.panel_id for panel in panels]
    if len(set(panel_ids)) != len(panel_ids):
        raise ExpansionError("expanded panel IDs are not unique; check duplicate product or accessory identifiers")
    return tuple(panels)


def group_panels(panels: tuple[Panel, ...]) -> dict[MaterialKey, tuple[Panel, ...]]:
    grouped: defaultdict[MaterialKey, list[Panel]] = defaultdict(list)
    for panel in panels:
        grouped[panel.material_key].append(panel)
    return {
        key: tuple(sorted(items, key=lambda panel: panel.panel_id))
        for key, items in sorted(grouped.items())
    }
