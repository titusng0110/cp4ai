"""Copy converted documents to the macOS clipboard."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import tiktoken

from .cli import convert_one, install_homebrew_dependencies
from .core import DEFAULT_OCR_ENGINE

SOURCE_SUFFIXES = {".docx", ".pdf", ".pptx"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cp2ai",
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
        help="OCR with Tesseract instead of Live Text (installs it if missing)",
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
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    install_homebrew_dependencies(args.ocr_engine)

    sources: list[Path] = []
    for value in args.files:
        path = Path(value).expanduser()
        if not path.is_file():
            print(f"ERROR: not a file: {path}", file=sys.stderr)
            return 1
        if path.suffix.lower() not in SOURCE_SUFFIXES:
            print(f"ERROR: unsupported file type: {path}", file=sys.stderr)
            return 1
        sources.append(path)

    use_ocr = args.ocr_engine != "none"
    jobs = max(1, args.jobs)
    failures = 0

    with tempfile.TemporaryDirectory(prefix="notes4ai_clipboard_") as tmp:
        workdir = Path(tmp)
        planned = [
            (source, workdir / f"{index:04d}.md")
            for index, source in enumerate(sources)
        ]

        if jobs <= 1 or len(planned) == 1:
            for index, (source, output) in enumerate(planned, start=1):
                try:
                    details = convert_one(source, output, use_ocr, args.ocr_engine)
                except Exception as exc:  # noqa: BLE001 - report and continue
                    failures += 1
                    print(f"[{index}/{len(planned)}] FAILED {source}: {exc}", file=sys.stderr)
                else:
                    print(f"[{index}/{len(planned)}] {source} ({details})")
        else:
            workers = min(jobs, len(planned))
            with ProcessPoolExecutor(max_workers=workers) as pool:
                futures = {
                    pool.submit(convert_one, source, output, use_ocr, args.ocr_engine): (
                        index,
                        source,
                    )
                    for index, (source, output) in enumerate(planned, start=1)
                }
                for future in as_completed(futures):
                    index, source = futures[future]
                    try:
                        details = future.result()
                    except Exception as exc:  # noqa: BLE001 - report and continue
                        failures += 1
                        print(
                            f"[{index}/{len(planned)}] FAILED {source}: {exc}",
                            file=sys.stderr,
                        )
                    else:
                        print(f"[{index}/{len(planned)}] {source} ({details})")

        if failures:
            print(f"{failures} file(s) failed; clipboard not changed", file=sys.stderr)
            return 1

        sections = []
        for source, output in planned:
            body = output.read_text(encoding="utf-8").rstrip()
            sections.append(
                f"[{source.name} BEGIN]\n{body}\n[{source.name} END]"
            )
        clipboard = "\n\n".join(sections) + "\n"

    try:
        subprocess.run(["pbcopy"], input=clipboard.encode("utf-8"), check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: could not write to clipboard: {exc}", file=sys.stderr)
        return 1

    tokens = len(tiktoken.get_encoding("cl100k_base").encode(clipboard))
    print("=" * 25)
    print(f"Copied to clipboard! ({len(clipboard)} characters / {tokens} tokens)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
