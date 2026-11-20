"""Copy converted documents to the macOS clipboard."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import __version__
from .core import DEFAULT_OCR_ENGINE
from .md4ai import install_homebrew_dependencies
from .pipeline import (
    BatchFailure,
    check_pandoc,
    check_tesseract,
    convert_batch,
    copy_to_clipboard,
    filter_sources,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cp4ai",
        description=(
            "Convert DOCX/PDF/PPTX files to Markdown and copy the concatenated "
            "result to the clipboard."
        ),
    )
    parser.add_argument("files", nargs="+", help=".docx/.pdf/.pptx files")
    engines = parser.add_mutually_exclusive_group()
    engines.add_argument(
        "--tesseract",
        dest="ocr_engine",
        action="store_const",
        const="tesseract",
        help="OCR with Tesseract instead of Live Text (requires: brew install tesseract)",
    )
    engines.add_argument(
        "--no-ocr",
        dest="ocr_engine",
        action="store_const",
        const="none",
        help="do not OCR images",
    )
    parser.set_defaults(ocr_engine=DEFAULT_OCR_ENGINE)
    parser.add_argument(
        "--jobs",
        type=int,
        default=os.cpu_count() or 1,
        help="parallel worker processes (default: CPU cores)",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def run_cli_progress():
    def _progress(index: int, count: int, source: Path, details: str | None, error: str | None):
        if error:
            print(f"[{index}/{count}] FAILED {source}: {error}", file=sys.stderr)
        else:
            print(f"[{index}/{count}] {source} ({details})")

    return _progress


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    sources, rejected = filter_sources(args.files)
    for item in rejected:
        print(f"ERROR: {item.path}: {item.reason}", file=sys.stderr)
    if rejected:
        return 1
    if not sources:
        print("ERROR: no files to convert", file=sys.stderr)
        return 1

    for problem in (check_pandoc(sources), check_tesseract(args.ocr_engine)):
        if problem:
            print(f"ERROR: {problem}", file=sys.stderr)
            return 1

    install_homebrew_dependencies(args.ocr_engine)

    use_ocr = args.ocr_engine != "none"
    jobs = max(1, args.jobs)
    try:
        result = convert_batch(
            sources,
            engine=args.ocr_engine,
            use_ocr=use_ocr,
            jobs=jobs,
            progress=run_cli_progress(),
        )
    except BatchFailure as exc:
        print(f"{len(exc.errors)} file(s) failed; clipboard not changed", file=sys.stderr)
        return 1

    try:
        copy_to_clipboard(result.markdown)
    except Exception as exc:  # noqa: BLE001 - pbcopy failure
        print(f"ERROR: could not write to clipboard: {exc}", file=sys.stderr)
        return 1

    print("=" * 25)
    print(f"Copied to clipboard! ({result.chars} characters / {result.tokens} tokens)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
