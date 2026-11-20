"""Command-line interface for md4ai."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from . import __version__
from .core import TESSDATA_DIR, convert_docx, convert_pdf, convert_pptx
from .pipeline import check_pandoc, check_tesseract

SOURCE_SUFFIXES = {".docx", ".pdf", ".pptx"}
HOMEBREW_COMMANDS = (
    ("emf2svg-conv", "libemf2svg"),
    ("rsvg-convert", "librsvg"),
)


def install_homebrew_dependencies(engine: str) -> None:
    """Install the niche vector-image helpers when OCR is enabled.

    Pandoc and Tesseract are deliberately not installed here: CLI users
    supply Pandoc themselves, and Tesseract is opt-in via ``--tesseract``.
    """
    if engine == "none" or sys.platform != "darwin" or os.environ.get("CP4AI_SKIP_SETUP"):
        return
    brew = shutil.which("brew")
    if not brew:
        return
    missing = [
        package
        for command, package in HOMEBREW_COMMANDS
        if not shutil.which(command)
    ]
    if not missing:
        return
    print(f"Installing Homebrew dependencies: {' '.join(missing)}", flush=True)
    subprocess.run([brew, "install", *missing], check=False)


def collect_sources(target: Path, recursive: bool) -> list[Path]:
    if target.is_file():
        if target.suffix.lower() not in SOURCE_SUFFIXES:
            raise ValueError(f"unsupported file type: {target} (expected .docx, .pdf or .pptx)")
        return [target]
    if target.is_dir():
        if not recursive:
            raise ValueError(f"{target} is a directory; pass -r/--recursive")
        sources = [
            path
            for path in target.rglob("*")
            if path.is_file()
            and path.suffix.lower() in SOURCE_SUFFIXES
            and not path.name.startswith("~$")
        ]
        return sorted(sources, key=lambda path: path.as_posix().lower())
    raise ValueError(f"not found: {target}")


def out_is_directory(raw: str, path: Path) -> bool:
    if path.exists() and path.is_dir():
        return True
    if raw.endswith("/") or raw.endswith(os.sep):
        return True
    return path.suffix.lower() != ".md"


def plan_outputs(
    sources: list[Path],
    target: Path,
    out_value: str | None,
) -> list[tuple[Path, Path]]:
    if out_value is None:
        return [(source, source.with_name(source.name + ".md")) for source in sources]

    out_path = Path(out_value).expanduser()
    if target.is_dir():
        if not out_is_directory(out_value, out_path):
            raise ValueError("--out must be a directory when converting a directory")
        return [
            (
                source,
                out_path / source.relative_to(target).parent / (source.name + ".md"),
            )
            for source in sources
        ]

    source = sources[0]
    if out_is_directory(out_value, out_path):
        return [(source, out_path / (source.name + ".md"))]
    return [(source, out_path)]


def check_outputs(planned: list[tuple[Path, Path]], force: bool) -> None:
    outputs = [output for _, output in planned]
    if len(set(outputs)) != len(outputs):
        raise ValueError("multiple inputs map to the same output path")

    directories = [output for output in outputs if output.exists() and output.is_dir()]
    if directories:
        raise ValueError(
            "output path is a directory: "
            + ", ".join(str(path) for path in directories)
        )

    existing = [output for output in outputs if output.exists()]
    if existing and not force:
        listing = "\n".join(f"  {path}" for path in existing)
        raise ValueError(
            "refusing to overwrite existing output (use -f/--force):\n" + listing
        )


def convert_one(source: Path, output: Path, use_ocr: bool, engine: str) -> str:
    if source.suffix.lower() == ".docx":
        return convert_docx(source, output, TESSDATA_DIR, engine, use_ocr)
    if source.suffix.lower() == ".pptx":
        return convert_pptx(source, output, TESSDATA_DIR, engine, use_ocr)
    return convert_pdf(source, output, use_ocr, TESSDATA_DIR, engine)


def run_conversions(
    planned: list[tuple[Path, Path]],
    use_ocr: bool,
    engine: str,
    jobs: int,
) -> int:
    for _, output in planned:
        output.parent.mkdir(parents=True, exist_ok=True)

    failures = 0
    total = len(planned)
    if jobs <= 1 or total == 1:
        for index, (source, output) in enumerate(planned, start=1):
            try:
                details = convert_one(source, output, use_ocr, engine)
            except Exception as exc:  # noqa: BLE001 - keep the batch going
                failures += 1
                print(f"[{index}/{total}] FAILED {source}: {exc}", file=sys.stderr)
            else:
                print(f"[{index}/{total}] {source} -> {output} ({details})")
        return failures

    workers = min(jobs, total)
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(convert_one, source, output, use_ocr, engine): (source, output)
            for source, output in planned
        }
        for index, future in enumerate(as_completed(futures), start=1):
            source, output = futures[future]
            try:
                details = future.result()
            except Exception as exc:  # noqa: BLE001 - keep the batch going
                failures += 1
                print(f"[{index}/{total}] FAILED {source}: {exc}", file=sys.stderr)
            else:
                print(f"[{index}/{total}] {source} -> {output} ({details})")
    return failures


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="md4ai",
        description=(
            "Convert DOCX, PDF and PPTX files to recall-first Markdown. "
            "By default a.pdf becomes a.pdf.md next to it."
        ),
    )
    parser.add_argument("target", type=Path, help=".docx/.pdf/.pptx file, or a directory with -r")
    parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="convert every .docx/.pdf/.pptx under a directory",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="overwrite existing Markdown output",
    )
    parser.add_argument(
        "-o",
        "--out",
        default=None,
        help=(
            "write to this .md file, or to this directory preserving structure "
            "(created if needed)"
        ),
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=os.cpu_count() or 1,
        help="parallel worker processes (default: CPU cores)",
    )
    engines = parser.add_mutually_exclusive_group()
    engines.add_argument(
        "--livetext",
        dest="ocr_engine",
        action="store_const",
        const="livetext",
        help="OCR with Apple Live Text via ocrmac (default)",
    )
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
    parser.set_defaults(ocr_engine="livetext")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    target = args.target.expanduser()
    try:
        sources = collect_sources(target, args.recursive)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if not sources:
        print(f"ERROR: no .docx/.pdf/.pptx files found under {target}", file=sys.stderr)
        return 1

    for problem in (check_pandoc(sources), check_tesseract(args.ocr_engine)):
        if problem:
            print(f"ERROR: {problem}", file=sys.stderr)
            return 1

    install_homebrew_dependencies(args.ocr_engine)

    try:
        planned = plan_outputs(sources, target, args.out)
        check_outputs(planned, args.force)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    use_ocr = args.ocr_engine != "none"
    failures = run_conversions(planned, use_ocr, args.ocr_engine, max(1, args.jobs))
    if failures:
        print(f"{failures} file(s) failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
