import json
from importlib.resources import files
from typing import Iterable

from jsonschema import Draft202012Validator


def _format_path(parts: Iterable[object]) -> str:
    path = ""
    for part in parts:
        path += (
            f"[{part}]"
            if isinstance(part, int)
            else ("." if path else "") + str(part)
        )
    return path or "job"


def validate_job_payload(payload: object) -> None:
    schema_path = files("cutting_layout").joinpath(
        "schemas", "cutting-layout-job.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    errors = sorted(
        validator.iter_errors(payload),
        key=lambda item: tuple(str(part) for part in item.absolute_path),
    )
    if errors:
        error = errors[0]
        raise ValueError(f"{_format_path(error.absolute_path)}: {error.message}")
