ALL_FORMATS = frozenset({"png", "dxf", "xlsx", "pdf", "json"})


def parse_formats(value: str) -> frozenset[str]:
    selected = frozenset(item.strip().lower() for item in value.split(",") if item.strip())
    if not selected:
        raise ValueError("formats: select at least one output format")
    unknown = sorted(selected - ALL_FORMATS)
    if unknown:
        raise ValueError(f"formats: unsupported values: {', '.join(unknown)}")
    return selected
