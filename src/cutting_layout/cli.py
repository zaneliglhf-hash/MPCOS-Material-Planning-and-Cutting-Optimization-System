import argparse
import json
from pathlib import Path
import sys

from . import __version__
from .expansion import ExpansionError
from .formats import ALL_FORMATS, parse_formats
from .input_loader import InputError
from .optimizer import OptimizationError
from .pipeline import ExportError, run_pipeline
from .validation import PlanValidationError


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cutting-layout",
        description="Generate mixed-product rectangular cutting layouts.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run", help="generate layout outputs from a JSON job")
    run.add_argument("input", type=Path, help="input JSON path")
    run.add_argument("--output", type=Path, required=True, help="output directory")
    run.add_argument(
        "--formats",
        default=",".join(sorted(ALL_FORMATS)),
        help="comma-separated output formats: png,dxf,xlsx,pdf,json",
    )
    return parser


def _print_error(message: str, code: int) -> None:
    print(json.dumps({"status": "error", "code": code, "error": message}, ensure_ascii=False), file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command != "run":
        _print_error(f"unsupported command: {args.command}", 2)
        return 2
    try:
        formats = parse_formats(args.formats)
    except ValueError as exc:
        _print_error(str(exc), 2)
        return 2
    try:
        bundle = run_pipeline(args.input, args.output, formats)
    except (InputError, ExpansionError, OptimizationError, PlanValidationError) as exc:
        _print_error(str(exc), 2)
        return 2
    except ExportError as exc:
        _print_error(str(exc), 3)
        return 3
    except Exception as exc:
        _print_error(f"unexpected internal error: {exc}", 3)
        return 3
    response = {"status": "success"}
    for key, path in (
        ("result_json", bundle.result_json),
        ("preview", bundle.overview_path),
        ("dxf", bundle.dxf_path),
        ("excel", bundle.excel_path),
        ("pdf", bundle.pdf_path),
    ):
        if path is not None:
            response[key] = str(path.resolve())
    print(json.dumps(response, ensure_ascii=False, indent=2))
    return 0
