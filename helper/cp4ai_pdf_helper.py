#!/usr/bin/env python3
"""PDF text extraction and OCR-region rasterisation for Copy 4 AI.

This helper is the only Python code in the app.  It does not OCR: it returns
the PyMuPDF Markdown for every page plus pre-merged PNG crops of the regions
that may contain text.  The Swift app runs Vision OCR and assembles the final
document.

Commands
--------
probe   --input X.pdf              page and OCR-region counts, for progress
extract --input X.pdf --output DIR page Markdown + region PNGs + document.json

The JSON schema is versioned with ``schema``.  stdout carries JSON only; all
diagnostics go to stderr.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

import pymupdf

pymupdf.use_layout(True)

SCHEMA = 1
IMAGE_MIN_WIDTH = 80.0
IMAGE_MIN_HEIGHT = 40.0
PAGE_AREA_MIN = 0.008
BACKGROUND_AREA = 0.85
MERGE_GAP = 6.0
DPI = 300
TOKEN_RE = re.compile(r"[a-z0-9]{2,}")


def token_set(text: str) -> set[str]:
    return set(TOKEN_RE.findall(text.lower()))


def merge_boxes(boxes: list[pymupdf.Rect], gap: float = MERGE_GAP) -> list[pymupdf.Rect]:
    """Merge neighbouring image fragments (e.g. a table split across images)."""
    pending = [pymupdf.Rect(box) for box in boxes]
    pending = [box for box in pending if not box.is_empty]
    while True:
        merged: list[pymupdf.Rect] = []
        changed = False
        for box in pending:
            for index, existing in enumerate(merged):
                expanded = pymupdf.Rect(
                    existing.x0 - gap,
                    existing.y0 - gap,
                    existing.x1 + gap,
                    existing.y1 + gap,
                )
                if expanded.intersects(box):
                    merged[index] = existing | box
                    changed = True
                    break
            else:
                merged.append(box)
        if not changed:
            return merged
        pending = merged


def page_image_boxes(
    page: pymupdf.Page,
) -> tuple[list[pymupdf.Rect], list[pymupdf.Rect]]:
    page_area = page.rect.get_area()
    foreground: list[pymupdf.Rect] = []
    background: list[pymupdf.Rect] = []
    for info in page.get_image_info(xrefs=True):
        box = pymupdf.Rect(info["bbox"]) & page.rect
        if box.is_empty or box.width < IMAGE_MIN_WIDTH or box.height < IMAGE_MIN_HEIGHT:
            continue
        if box.get_area() < page_area * PAGE_AREA_MIN:
            continue
        if box.width / max(box.height, 1) > 20 or box.height / max(box.width, 1) > 20:
            continue
        if box.get_area() >= page_area * BACKGROUND_AREA:
            background.append(box)
        else:
            foreground.append(box)
    return foreground, background


def page_plan(page: pymupdf.Page) -> dict:
    foreground, background = page_image_boxes(page)
    foreground = merge_boxes(foreground)
    background = merge_boxes(background)
    return {
        "foreground": [list(box) for box in foreground],
        "background": [list(box) for box in background],
    }


def render_region(page: pymupdf.Page, box, path: Path) -> dict:
    pix = page.get_pixmap(clip=pymupdf.Rect(box), dpi=DPI, alpha=False)
    pix.save(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {
        "file": path.name,
        "bbox": list(box),
        "sha256": digest,
    }


def page_ocr_jobs(plan: dict, native_text: str) -> int:
    jobs = len(plan["foreground"])
    if plan["background"] and len(token_set(native_text)) < 40:
        jobs += len(plan["background"])
    return jobs


def probe(path: Path) -> dict:
    with pymupdf.open(path) as doc:
        pages = []
        jobs = 0
        for page in doc:
            plan = page_plan(page)
            jobs += page_ocr_jobs(plan, page.get_text())
            pages.append(
                {
                    "number": page.number + 1,
                    "foreground": len(plan["foreground"]),
                    "background": len(plan["background"]),
                }
            )
        return {
            "schema": SCHEMA,
            "pymupdf": pymupdf.__version__,
            "page_count": doc.page_count,
            "ocr_jobs": jobs,
            "pages": pages,
        }


def extract(path: Path, output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    with pymupdf.open(path) as doc:
        chunks = doc.to_markdown(page_chunks=True, show_progress=False, use_ocr=False)
        pages = []
        for index, chunk in enumerate(chunks):
            page = doc[index] if index < doc.page_count else None
            native = chunk.get("text", "")
            entry = {
                "number": index + 1,
                "markdown": native,
                "foreground": [],
                "background": [],
            }
            if page is not None:
                plan = page_plan(page)
                for kind in ("foreground", "background"):
                    for region_index, box in enumerate(plan[kind]):
                        name = f"p{index + 1:04d}_{kind[0]}{region_index}.png"
                        entry[kind].append(
                            render_region(page, box, output / name)
                        )
            pages.append(entry)
        return {
            "schema": SCHEMA,
            "pymupdf": pymupdf.__version__,
            "page_count": doc.page_count,
            "pages": pages,
        }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cp4ai-pdf")
    parser.add_argument("--version", action="version", version=f"%(prog)s {SCHEMA}")
    sub = parser.add_subparsers(dest="command", required=True)

    probe_parser = sub.add_parser("probe")
    probe_parser.add_argument("--input", type=Path, required=True)

    extract_parser = sub.add_parser("extract")
    extract_parser.add_argument("--input", type=Path, required=True)
    extract_parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if not args.input.is_file():
            raise FileNotFoundError(f"not found: {args.input}")
        if args.command == "probe":
            result = probe(args.input)
        else:
            result = extract(args.input, args.output)
    except Exception as exc:  # noqa: BLE001 - reported to the Swift caller
        print(f"cp4ai-pdf: {exc}", file=sys.stderr)
        return 2
    json.dump(result, sys.stdout, ensure_ascii=False, separators=(",", ":"))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
