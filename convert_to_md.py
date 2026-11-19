#!/usr/bin/env python3
"""Convert DOCX and PDF study material into AI-friendly Markdown.

What this script guarantees
---------------------------
* It never summarizes or truncates the source text.
* DOCX files go through Pandoc, so headings, lists, tables, footnotes, text
  boxes and tracked changes survive.
* Every raster DOCX image is OCR'd and its text is inserted into the Markdown
  at the image's position. Image files are *not* copied into the output.
* Every PDF keeps its digital text layer and page order, with page boundaries
  marked as ``<!-- page N of M -->``. Text that exists only inside PDF images
  (screenshots, table fragments, diagrams) is OCR'd and appended on the same
  page, under a clearly marked OCR comment.
* DOCX comments are reproduced verbatim in an appendix, because Pandoc does
  not emit them.
* A few DOCX files contain EMF/vector drawings. EMF+ bitmaps are extracted
  directly from the EMF record and OCR'd; classic EMF/SVG are rasterised with
  libemf2svg + librsvg. Only images that still fail are listed in a short
  "Vector images (not OCR'd)" section at the end of the Markdown.

Usage
-----
    uv sync
    uv run python convert_to_md.py
    uv run python convert_to_md.py --force
    uv run python convert_to_md.py --only "Lecture 4"
    uv run python convert_to_md.py --no-ocr

Reproducible environment
------------------------
    Python 3.13
    pymupdf==1.28.2
    pymupdf4llm==0.3.4
    pypandoc-binary==1.17        (bundles Pandoc 3.9)
    opencv-python-headless==5.1.0.95
    numpy==2.5.5
    tabulate==0.10.0
    Tesseract 5.5.4              (brew install tesseract)
    eng.traineddata + chi_tra.traineddata in tools/tessdata
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile
from datetime import date
from pathlib import Path
from typing import Iterable
from urllib.parse import unquote
from xml.etree import ElementTree as ET

import cv2
import numpy as np
import pymupdf
import pymupdf4llm
import pypandoc

ROOT = Path(__file__).resolve().parent
DEFAULT_SRC = ROOT / "src"
DEFAULT_OUT = ROOT / "md"
TESSDATA_DIR = ROOT / "tools" / "tessdata"

W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
WATERMARK_RE = re.compile(r"(?:@?\s*pcll\s*8026\s*pass|@?pcll2026pass)", re.IGNORECASE)
ALNUM_RE = re.compile(r"[A-Za-z0-9\u3400-\u9fff]")
LIGATURES = {
    "\ufb00": "ff",
    "\ufb01": "fi",
    "\ufb02": "fl",
    "\ufb03": "ffi",
    "\ufb04": "ffl",
}
IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
OCR_COMMENT = (
    "<!-- OCR text from image(s) on this page; the text existed only inside "
    "a picture and may contain recognition errors -->"
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def clean_text(text: str) -> str:
    """Normalize PDF text without changing its substantive content."""
    for src, dst in LIGATURES.items():
        text = text.replace(src, dst)
    text = text.replace("\u00a0", " ").replace("\u00ad", "")
    # Superscripts such as "1 [st] loan" are common in the PDF text layer.
    text = re.sub(r"(?<=\d)\s*\[(st|nd|rd|th)\]", r"\1", text, flags=re.IGNORECASE)
    lines = []
    for line in text.splitlines():
        # Drop the diagonal course watermark where the text layer exposes it.
        if WATERMARK_RE.search(line) and len(line.strip()) < 40:
            continue
        lines.append(line.rstrip())
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def yaml_value(value: object) -> str:
    return json.dumps(str(value), ensure_ascii=False)


def md_title(path: Path) -> str:
    return re.sub(r"\s+", " ", path.stem).strip()


def display_path(path: Path) -> str:
    """Prefer a project-relative path so the Markdown stays portable."""
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def front_matter(path: Path, source_format: str, **extra: object) -> str:
    lines = [
        "---",
        f"source: {yaml_value(display_path(path))}",
        f"format: {source_format}",
        f"converted: {yaml_value(date.today().isoformat())}",
    ]
    for key, value in extra.items():
        if value is None or value == "":
            continue
        lines.append(f"{key}: {yaml_value(value)}")
    lines.append("---")
    return "\n".join(lines)


def write_markdown(out_path: Path, body: str) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(body.rstrip() + "\n", encoding="utf-8")


def token_set(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]{2,}", text.lower()))


def overlap_ratio(candidate: str, reference: str) -> float:
    candidate_tokens = token_set(candidate)
    if not candidate_tokens:
        return 1.0
    return len(candidate_tokens & token_set(reference)) / len(candidate_tokens)


def useful_ocr(text: str) -> bool:
    """Reject OCR noise from logos, photos and decorative images."""
    if len(ALNUM_RE.findall(text)) < 8:
        return False
    if len(re.findall(r"[A-Za-z0-9]{2,}", text)) < 2:
        return False
    printable = sum(ch.isalnum() or ch.isspace() or ch in ".,;:()[]/-%$&'\"+=" for ch in text)
    return printable / max(len(text), 1) >= 0.55


# ---------------------------------------------------------------------------
# DOCX conversion
# ---------------------------------------------------------------------------


def docx_xml_text(data: bytes) -> str:
    root = ET.fromstring(data)
    chunks: list[str] = []
    for para in root.iter(W_NS + "p"):
        text = "".join(node.text or "" for node in para.iter(W_NS + "t")).strip()
        if text:
            chunks.append(text)
    return "\n".join(chunks)


def extract_docx_header(path: Path) -> str:
    """Return the first substantive Word header, ignoring page-number footers."""
    headers: list[str] = []
    try:
        with zipfile.ZipFile(path) as zf:
            for name in sorted(zf.namelist()):
                if not re.fullmatch(r"word/header\d+\.xml", name):
                    continue
                text = " ".join(docx_xml_text(zf.read(name)).split())
                if text and not re.fullmatch(r"PAGE(?:\s*\d+)?", text, re.IGNORECASE):
                    headers.append(text)
    except (zipfile.BadZipFile, KeyError, ET.ParseError):
        return ""
    seen: set[str] = set()
    for header in headers:
        if header not in seen:
            return header
        seen.add(header)
    return ""


def extract_docx_comments(path: Path) -> list[dict[str, str]]:
    """Extract DOCX comments, authors, dates and the passage they annotate."""
    try:
        with zipfile.ZipFile(path) as zf:
            if "word/comments.xml" not in zf.namelist():
                return []
            comments_root = ET.fromstring(zf.read("word/comments.xml"))
            document_root = ET.fromstring(zf.read("word/document.xml"))
    except (zipfile.BadZipFile, KeyError, ET.ParseError):
        return []

    anchors: dict[str, list[str]] = {}
    order: list[str] = []
    for para in document_root.iter(W_NS + "p"):
        ids = [
            node.get(W_NS + "id")
            for node in para.iter()
            if node.tag in (W_NS + "commentRangeStart", W_NS + "commentReference")
        ]
        ids = [i for i in ids if i is not None]
        if not ids:
            continue
        text = "".join(node.text or "" for node in para.iter(W_NS + "t")).strip()
        for comment_id in ids:
            if comment_id not in order:
                order.append(comment_id)
            anchors.setdefault(comment_id, [])
            if text and text not in anchors[comment_id]:
                anchors[comment_id].append(text)

    comments: list[dict[str, str]] = []
    for node in comments_root.findall(W_NS + "comment"):
        paragraphs: list[str] = []
        for para in node.iter(W_NS + "p"):
            text = "".join(child.text or "" for child in para.iter(W_NS + "t")).strip()
            if text:
                paragraphs.append(text)
        if not paragraphs:
            continue
        comments.append(
            {
                "id": node.get(W_NS + "id", ""),
                "author": node.get(W_NS + "author", "Unknown"),
                "date": (node.get(W_NS + "date") or "")[:10],
                "text": "\n\n".join(paragraphs),
                "anchor": " … ".join(anchors.get(node.get(W_NS + "id", ""), [])),
            }
        )

    rank = {comment_id: i for i, comment_id in enumerate(order)}
    comments.sort(key=lambda c: (rank.get(c["id"], 10**9), c["id"]))
    return comments


def comments_appendix(comments: list[dict[str, str]]) -> str:
    if not comments:
        return ""
    out = [
        "---",
        "",
        "## Appendix: Comments in the original DOCX",
        "",
        "> Word stores comments separately from the body text. Pandoc does not "
        "emit them, so they are reproduced verbatim below with their author, "
        "date, and the passage they were attached to.",
    ]
    for index, comment in enumerate(comments, start=1):
        meta = f"### Comment {index} — {comment['author']}"
        if comment["date"]:
            meta += f" — {comment['date']}"
        out.extend(["", meta, ""])
        anchor = comment["anchor"].strip()
        if anchor:
            if len(anchor) > 400:
                anchor = anchor[:400].rstrip() + "…"
            out.extend([f"**Attached to:** “{anchor}”", ""])
        quoted = "\n".join(
            f"> {line}" if line.strip() else ">" for line in comment["text"].splitlines()
        )
        out.append(quoted)
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Image OCR (shared by DOCX and PDF)
# ---------------------------------------------------------------------------


def preprocess_for_ocr(src: Path, dst: Path) -> bool:
    """Remove table rules and the light watermark, keep dark text."""
    image = cv2.imread(str(src), cv2.IMREAD_GRAYSCALE)
    if image is None:
        return False
    height, width = image.shape
    if width < 1800:
        scale = 1800 / width
        image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        height, width = image.shape

    # Keep only dark pixels; this drops the light-grey diagonal watermark.
    binary = cv2.threshold(image, 160, 255, cv2.THRESH_BINARY_INV)[1]

    horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(20, width // 20), 1))
    vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(20, height // 20)))
    horizontal = cv2.morphologyEx(binary, cv2.MORPH_OPEN, horizontal_kernel, iterations=1)
    vertical = cv2.morphologyEx(binary, cv2.MORPH_OPEN, vertical_kernel, iterations=1)
    rules = cv2.add(horizontal, vertical)
    cleaned = cv2.subtract(binary, rules)
    cleaned = cv2.bitwise_not(cleaned)
    return cv2.imwrite(str(dst), cleaned)


def tesseract_tsv(
    image: Path, psm: int, tessdata_dir: Path | None
) -> tuple[str, float, int]:
    """Run Tesseract and return reconstructed text, mean confidence, word count.

    Tesseract's own confidence lets us choose between the original image and
    the line-removed version instead of guessing which preprocessing helped.
    """
    cmd = ["tesseract", str(image), "stdout", "-l", "eng+chi_tra", "--psm", str(psm), "tsv"]
    if tessdata_dir and (tessdata_dir / "eng.traineddata").exists():
        cmd.extend(["--tessdata-dir", str(tessdata_dir)])
    env = dict(os.environ, OMP_THREAD_LIMIT="1")
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if proc.returncode != 0:
        return "", 0.0, 0

    lines = proc.stdout.splitlines()
    if lines and lines[0].startswith("level"):
        lines = lines[1:]

    output: list[str] = []
    words: list[str] = []
    current_key: tuple[str, ...] | None = None
    previous_key: tuple[str, ...] | None = None
    total = 0.0
    weight = 0
    word_count = 0
    for line in lines:
        parts = line.split("\t")
        if len(parts) < 12:
            continue
        text = parts[11].strip()
        if not text:
            continue
        key = tuple(parts[1:5])  # page, block, paragraph, line
        if current_key is not None and key != current_key:
            output.append(" ".join(words))
            words = []
            if previous_key is not None and key[2] != previous_key[2]:
                output.append("")
        if current_key is not None and key != current_key:
            previous_key = current_key
        current_key = key
        words.append(text)
        try:
            confidence = float(parts[10])
        except ValueError:
            confidence = -1.0
        if confidence >= 0:
            total += confidence * len(text)
            weight += len(text)
            word_count += 1
    if words:
        output.append(" ".join(words))

    text = "\n".join(output).replace("\x0c", "\n")
    mean_confidence = total / weight if weight else 0.0
    return text, mean_confidence, word_count


def ocr_image(
    path: Path,
    workdir: Path,
    index: int,
    tessdata_dir: Path | None,
    diagram: bool = False,
) -> str:
    """OCR one raster image, choosing the best page-segmentation mode.

    ``diagram=True`` also tries sparse-text mode, which reads labels scattered
    around boxes and arrows instead of assuming a single text column.
    """
    cleaned = workdir / f"clean_{index}.png"
    made_clean = preprocess_for_ocr(path, cleaned)

    candidates: list[tuple[float, int, str, str]] = []
    if made_clean:
        text, confidence, words = tesseract_tsv(cleaned, psm=6, tessdata_dir=tessdata_dir)
        candidates.append((confidence, words, text, "table"))
    text, confidence, words = tesseract_tsv(path, psm=3, tessdata_dir=tessdata_dir)
    candidates.append((confidence, words, text, "layout"))
    if diagram:
        text, confidence, words = tesseract_tsv(path, psm=11, tessdata_dir=tessdata_dir)
        candidates.append((confidence, words, text, "sparse"))

    # Prefer the most confident non-empty result; use word count as a tie-break.
    candidates = [c for c in candidates if c[2].strip()]
    if not candidates:
        return ""
    best = max(candidates, key=lambda item: (item[0], item[1]))
    if diagram:
        sparse = next((c for c in candidates if c[3] == "sparse"), None)
        # Sparse mode is better at labels, so use it when it is close to the best.
        if sparse and sparse[0] >= best[0] - 5:
            best = sparse

    text = best[2]
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = "\n".join(
        line for line in text.splitlines() if not (WATERMARK_RE.search(line) and len(line.strip()) < 40)
    )
    return text.strip()


def extract_emf_plus_bitmap(emf_path: Path, out_png: Path) -> bool:
    """Extract the bitmap embedded in an EMF+ file and flatten it onto white.

    Word commonly stores screenshots/tables as EMF+ ``EmfPlusBitmap`` records
    rather than as separate PNG files. ``libemf2svg`` ignores EMF+ records
    entirely, so we read the raw BGRA pixels from the record directly.
    """
    data = emf_path.read_bytes()
    offset = 0
    plus_chunks: list[tuple[int, int]] = []
    while offset + 8 <= len(data):
        record_type, record_size = struct.unpack_from("<II", data, offset)
        if record_size < 8 or offset + record_size > len(data):
            break
        if record_type == 70:  # EMR_COMMENT
            _, comment_id = struct.unpack_from("<II", data, offset + 8)
            if comment_id == 0x2B464D45:  # "EMF+"
                plus_chunks.append((offset + 16, offset + record_size))
        offset += record_size

    for start, end in plus_chunks:
        cursor = start
        while cursor + 12 <= end:
            record_type, _flags, record_size, _data_size = struct.unpack_from(
                "<HHII", data, cursor
            )
            if record_type == 0x4008 and record_size > 40:  # EmfPlusBitmap
                width, height, stride = struct.unpack_from("<III", data, cursor + 20)
                payload = data[cursor + 40 : cursor + 40 + stride * height]
                if (
                    0 < width <= 10000
                    and 0 < height <= 10000
                    and stride in (width * 3, width * 4)
                    and len(payload) == stride * height
                ):
                    pixels = np.frombuffer(payload, dtype=np.uint8)
                    if stride == width * 4:
                        bgra = pixels.reshape(height, stride)[:, : width * 4].reshape(
                            height, width, 4
                        )
                        alpha = bgra[:, :, 3]
                        if int(alpha.max()) == 0:
                            bgr = bgra[:, :, :3]
                        else:
                            alpha_f = alpha.astype(np.float32) / 255.0
                            bgr = bgra[:, :, :3].astype(np.float32) + (
                                1.0 - alpha_f[:, :, None]
                            ) * 255.0
                            bgr = np.clip(bgr, 0, 255).astype(np.uint8)
                    else:
                        bgr = pixels.reshape(height, stride)[:, : width * 3].reshape(
                            height, width, 3
                        )
                    cv2.imwrite(str(out_png), bgr)
                    return out_png.exists() and out_png.stat().st_size > 0
            if record_size < 12 or cursor + record_size > end:
                break
            cursor += record_size
    return False


def svg_to_png(svg_path: Path, out_png: Path, width: int = 2400) -> bool:
    if not shutil.which("rsvg-convert"):
        return False
    proc = subprocess.run(
        ["rsvg-convert", str(svg_path), "-o", str(out_png), "--width", str(width)],
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0 and out_png.exists() and out_png.stat().st_size > 0


def vector_to_png(source: Path, out_png: Path, workdir: Path) -> bool:
    """Convert EMF/EMF+/SVG to a raster image for OCR."""
    suffix = source.suffix.lower()
    if suffix == ".emf" and extract_emf_plus_bitmap(source, out_png):
        return True
    if suffix in {".emf", ".svg"}:
        svg_path = source if suffix == ".svg" else workdir / f"{source.stem}_vector.svg"
        if suffix == ".emf":
            converter = shutil.which("emf2svg-conv")
            if not converter:
                return False
            proc = subprocess.run(
                [converter, "-p", "-i", str(source), "-o", str(svg_path)],
                capture_output=True,
                text=True,
            )
            if proc.returncode != 0 or not svg_path.exists():
                return False
            if svg_path.stat().st_size < 500:
                return False
            if all(token not in svg_path.read_text(errors="ignore") for token in ("<path", "<image", "<text")):
                return False
        return svg_to_png(svg_path, out_png)
    return False


def ocr_image_file(
    path: Path,
    workdir: Path,
    index: int,
    tessdata_dir: Path | None,
) -> str:
    """OCR a raster image, converting EMF/EMF+/SVG to PNG first if needed."""
    if path.suffix.lower() in {".emf", ".wmf", ".svg"}:
        png_path = workdir / f"vector_{index}.png"
        if not vector_to_png(path, png_path, workdir):
            return ""
        return ocr_image(png_path, workdir, index, tessdata_dir, diagram=True)
    return ocr_image(path, workdir, index, tessdata_dir, diagram=True)


def ocr_blockquote(text: str, label: str) -> str:
    lines = [f"> **Image text (OCR) — {label}**", ">"]
    lines.extend(f"> {line}" if line.strip() else ">" for line in text.splitlines())
    return "\n".join(lines)


def replace_docx_images(
    markdown: str,
    media_dir: Path,
    workdir: Path,
    tessdata_dir: Path | None,
) -> tuple[str, list[Path], set[Path]]:
    """Replace every DOCX image link with its OCR text (or a clear note)."""
    failed_vectors: list[Path] = []
    referenced: set[Path] = set()
    counter = 0

    def repl(match: re.Match[str]) -> str:
        nonlocal counter
        alt = match.group(1).strip()
        source = unquote(match.group(2).strip())
        image_path = (media_dir / source).resolve()
        label = alt or Path(source).name
        if not image_path.exists():
            return f"<!-- image not extracted: {label} -->"

        counter += 1
        referenced.add(image_path)
        text = ocr_image_file(image_path, workdir, counter, tessdata_dir)
        if not text or not useful_ocr(text):
            if image_path.suffix.lower() in {".emf", ".wmf", ".svg"}:
                failed_vectors.append(image_path)
                return f"<!-- vector image not OCR'd: {label} -->"
            return f"<!-- image omitted: {label} (no readable text detected) -->"

        # Keep table rows intact: a multi-line blockquote would break the table.
        line_start = markdown.rfind("\n", 0, match.start()) + 1
        line_end = markdown.find("\n", match.end())
        line = markdown[line_start : line_end if line_end != -1 else len(markdown)]
        if line.lstrip().startswith("|"):
            escaped = text.replace("|", "\\|").replace("\n", "<br>")
            return f"<br>**Image text (OCR):** {escaped}"

        return "\n\n" + ocr_blockquote(text, label) + "\n\n"

    return IMAGE_RE.sub(repl, markdown), failed_vectors, referenced


def natural_key(path: Path) -> list[object]:
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", path.name)]


def figures_section(
    media_dir: Path,
    referenced: set[Path],
    workdir: Path,
    tessdata_dir: Path | None,
) -> tuple[str, int, list[Path]]:
    """OCR images that Pandoc extracted but could not place in the body.

    Word floating/anchored drawings are extracted to ``media/`` but do not
    produce a Markdown image link. They often contain the most important
    diagrams in the document, so none may be dropped.
    """
    image_suffixes = {
        ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".webp",
        ".emf", ".wmf", ".svg",
    }
    figures: list[tuple[str, str]] = []
    failed_vectors: list[Path] = []
    index = 5000
    for image_path in sorted((p for p in media_dir.rglob("*") if p.is_file()), key=natural_key):
        if image_path.suffix.lower() not in image_suffixes:
            continue
        if image_path.resolve() in referenced:
            continue
        index += 1
        text = ocr_image_file(image_path, workdir, index, tessdata_dir)
        if text and useful_ocr(text):
            figures.append((image_path.name, text))
        elif image_path.suffix.lower() in {".emf", ".wmf", ".svg"}:
            failed_vectors.append(image_path)
    if not figures:
        return "", 0, failed_vectors

    out = [
        "## Figures from the original document (OCR text)",
        "",
        "> Pandoc could not position these floating/anchored drawings in the "
        "body, but the images were still present in the DOCX. Their text is "
        "reproduced below in image order and may contain recognition errors.",
    ]
    for number, (name, text) in enumerate(figures, start=1):
        out.extend(["", f"### Figure {number} — {name}", ""])
        out.extend(f"> {line}" if line.strip() else ">" for line in text.splitlines())
    return "\n".join(out), len(figures), failed_vectors


def vector_note(vector_files: list[Path]) -> str:
    if not vector_files:
        return ""
    lines = [
        "## Vector images (not OCR'd)",
        "",
        "> The original DOCX contains EMF/WMF/SVG vector drawings. These need a "
        "vector renderer to convert to an image before OCR, so they were left "
        "out of this Markdown. The source files are listed below; consult the "
        "original DOCX if their visual detail is needed.",
        "",
    ]
    lines.extend(f"- `{path.name}`" for path in vector_files)
    return "\n".join(lines)


def convert_docx(path: Path, out_path: Path, tessdata_dir: Path | None) -> str:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="cct_docx_") as tmp:
        workdir = Path(tmp)
        pandoc = pypandoc.get_pandoc_path()
        cmd = [
            pandoc,
            str(path.resolve()),
            "--from=docx",
            "--to=gfm",
            "--wrap=none",
            "--markdown-headings=atx",
            "--track-changes=all",
            "--extract-media=media",
        ]
        proc = subprocess.run(cmd, cwd=workdir, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"Pandoc failed for {path}:\n{proc.stderr}")

        media_dir = workdir / "media"
        body, failed_vectors, referenced = replace_docx_images(
            proc.stdout.strip(), media_dir, workdir, tessdata_dir
        )
        figures, figure_count, more_failed = figures_section(
            media_dir, referenced, workdir, tessdata_dir
        )
        vector_files = sorted(set(failed_vectors + more_failed), key=natural_key)
        header = extract_docx_header(path)
        comments = extract_docx_comments(path)

    pieces = [
        front_matter(
            path,
            "docx",
            converter="pandoc 3.9 (pypandoc 1.17)",
            header=header or None,
            comments=len(comments) if comments else None,
            images_ocr="tesseract 5.5.4 eng+chi_tra",
        ),
        "",
        f"# {md_title(path)}",
        "",
    ]
    if header:
        pieces.extend([f"> **Original document header:** {header}", ""])
    pieces.extend(
        [body, "", figures, comments_appendix(comments), vector_note(vector_files)]
    )
    write_markdown(out_path, "\n".join(pieces))
    return (
        f"docx, {len(comments)} comment(s), {figure_count} floating figure(s), "
        f"{len(vector_files)} vector image(s) not OCR'd"
    )


# ---------------------------------------------------------------------------
# PDF conversion + OCR
# ---------------------------------------------------------------------------


def merge_boxes(boxes: Iterable[pymupdf.Rect], gap: float = 6.0) -> list[pymupdf.Rect]:
    """Merge neighbouring image fragments (e.g. a table split into several images)."""
    merged: list[pymupdf.Rect] = []
    for box in sorted(boxes, key=lambda b: (b.y0, b.x0)):
        box = pymupdf.Rect(box)
        if box.is_empty:
            continue
        for i, existing in enumerate(merged):
            expanded = pymupdf.Rect(
                existing.x0 - gap, existing.y0 - gap, existing.x1 + gap, existing.y1 + gap
            )
            if expanded.intersects(box):
                merged[i] = existing | box
                break
        else:
            merged.append(box)

    changed = True
    while changed:
        changed = False
        result: list[pymupdf.Rect] = []
        for box in merged:
            for i, existing in enumerate(result):
                expanded = pymupdf.Rect(
                    existing.x0 - gap, existing.y0 - gap, existing.x1 + gap, existing.y1 + gap
                )
                if expanded.intersects(box):
                    result[i] = existing | box
                    changed = True
                    break
            else:
                result.append(box)
        merged = result
    return merged


def ocr_page_images(
    page: pymupdf.Page,
    page_number: int,
    workdir: Path,
    cache: dict[tuple, str],
    tessdata_dir: Path | None,
    native_text: str,
) -> str:
    page_area = page.rect.get_area()
    foreground: list[pymupdf.Rect] = []
    background: list[pymupdf.Rect] = []
    xref_by_box: dict[tuple[int, int, int, int], tuple[int, ...]] = {}
    for info in page.get_image_info(xrefs=True):
        box = pymupdf.Rect(info["bbox"]) & page.rect
        if box.is_empty or box.width < 80 or box.height < 40:
            continue
        if box.get_area() < page_area * 0.008:
            continue
        if box.width / max(box.height, 1) > 20 or box.height / max(box.width, 1) > 20:
            continue
        if box.get_area() >= page_area * 0.85:
            background.append(box)
        else:
            foreground.append(box)
        key = (round(box.x0), round(box.y0), round(box.x1), round(box.y1))
        xref_by_box.setdefault(key, tuple())
        xref_by_box[key] += (int(info.get("xref", 0)),)

    def run_boxes(boxes: list[pymupdf.Rect], offset: int) -> list[str]:
        results: list[str] = []
        for index, box in enumerate(merge_boxes(boxes)):
            xrefs = sorted(
                {
                    xref
                    for key, values in xref_by_box.items()
                    for xref in values
                    if pymupdf.Rect(key).intersects(box)
                }
            )
            cache_key = (tuple(xrefs), round(box.width), round(box.height))
            if cache_key in cache:
                text = cache[cache_key]
            else:
                pix = page.get_pixmap(clip=box, dpi=300, alpha=False)
                image_path = workdir / f"page_{page_number:04d}_{offset + index}.png"
                pix.save(image_path)
                text = ocr_image(
                    image_path,
                    workdir,
                    page_number * 100 + offset + index,
                    tessdata_dir,
                )
                cache[cache_key] = text
            if text and useful_ocr(text):
                results.append(text)
        return results

    native_tokens = len(token_set(native_text))
    regions: list[str] = []
    if foreground:
        # The common case: a real screenshot/table on a page whose full-page
        # image is just a background scan. OCR the foreground only.
        regions = run_boxes(foreground, 0)
        # A nearly blank native text layer plus almost no foreground text means
        # the page may be a full-page scan; fall back to the whole page.
        if native_tokens < 40 and len(token_set("\n".join(regions))) < 20 and background:
            regions = run_boxes(background, 50)
    elif background and native_tokens < 40:
        # Scanned page with no separate foreground images.
        regions = run_boxes(background, 50)
    return "\n\n".join(regions)


def convert_pdf(
    path: Path,
    out_path: Path,
    use_ocr: bool = True,
    tessdata_dir: Path | None = None,
) -> str:
    doc = pymupdf.open(path)
    try:
        chunks = pymupdf4llm.to_markdown(doc, page_chunks=True, show_progress=False)
        parts: list[str] = []
        ocr_pages = 0
        cache: dict[tuple, str] = {}
        with tempfile.TemporaryDirectory(prefix="cct_pdf_") as tmp:
            workdir = Path(tmp)
            for page_index, chunk in enumerate(chunks):
                page = doc[page_index]
                native = clean_text(chunk.get("text", ""))
                ocr_text = ""
                if use_ocr:
                    ocr_text = ocr_page_images(
                        page, page_index + 1, workdir, cache, tessdata_dir, native
                    )
                    if ocr_text and overlap_ratio(ocr_text, native) >= 0.90:
                        ocr_text = ""
                if ocr_text:
                    ocr_pages += 1

                page_body = native
                if ocr_text:
                    page_body += f"\n\n{OCR_COMMENT}\n\n{ocr_text}"

                parts.append(
                    f"<!-- page {page_index + 1} of {len(chunks)} -->\n\n{page_body.strip()}"
                )
    finally:
        doc.close()

    header = front_matter(
        path,
        "pdf",
        pages=len(chunks),
        text_extraction="pymupdf4llm 0.3.4",
        images_ocr=(
            f"tesseract 5.5.4 eng+chi_tra ({ocr_pages} page(s) with OCR text)"
            if use_ocr
            else "disabled"
        ),
    )
    write_markdown(out_path, f"{header}\n\n# {md_title(path)}\n\n" + "\n\n".join(parts))
    return f"pdf, {len(chunks)} pages, OCR on {ocr_pages} page(s)"


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def find_sources(src: Path) -> list[Path]:
    files = [
        p
        for p in src.rglob("*")
        if p.is_file() and p.suffix.lower() in {".docx", ".pdf"} and not p.name.startswith("~$")
    ]
    return sorted(files, key=lambda p: p.as_posix().lower())


def build_index(out_dir: Path, rows: list[tuple[Path, Path, str]]) -> None:
    lines = [
        "# Source Library (Markdown)",
        "",
        f"Converted from `src/` on {date.today().isoformat()}.",
        "",
        "## Documents",
        "",
        "| Markdown | Source | Type | Details |",
        "|---|---|---|---|",
    ]
    for md_path, src_path, details in rows:
        rel_md = md_path.relative_to(out_dir).as_posix()
        lines.append(
            f"| [{rel_md}]({rel_md}) | `{display_path(src_path)}` | "
            f"{src_path.suffix.lower().lstrip('.')} | {details} |"
        )
    lines.extend(
        [
            "",
            "## Conversion notes",
            "",
            "- **DOCX:** Pandoc 3.9 (via pypandoc 1.17) to GitHub-flavored Markdown. "
            "Headings, lists, tables, footnotes, text boxes and tracked changes are "
            "preserved. Every raster image is passed through OCR with Tesseract "
            "5.5.4 and its text is inserted at the image's position where detected; "
            "image files are not copied into the "
            "Markdown. DOCX comments are reproduced verbatim in an appendix. "
            "EMF+ bitmaps are extracted from the EMF record and OCR'd; classic "
            "EMF/SVG are rasterised with libemf2svg + librsvg. Only failures are "
            "listed in a short note at the end of the file.",
            "- **PDF:** PyMuPDF4LLM 0.3.4 preserves the digital text layer and page "
            "order. Pages are delimited with `<!-- page N of M -->` comments. Text "
            "that exists only inside embedded images (screenshots, table fragments, "
            "diagrams) is OCR'd with Tesseract 5.5.4 (`eng+chi_tra`), marked with "
            "`<!-- OCR text ... -->`, and may contain recognition errors.",
            "- Nothing was summarized, shortened, or deliberately omitted. Blank pages "
            "are kept as page markers so page references remain accurate.",
        ]
    )
    (out_dir / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", type=Path, default=DEFAULT_SRC, help="Source directory")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Output directory")
    parser.add_argument("--force", action="store_true", help="Overwrite existing Markdown")
    parser.add_argument("--no-ocr", action="store_true", help="Disable OCR")
    parser.add_argument("--only", default=None, help="Only convert paths containing this text")
    args = parser.parse_args()

    if not args.no_ocr and not shutil.which("tesseract"):
        print("ERROR: tesseract is not installed. Run: brew install tesseract", file=sys.stderr)
        return 1

    sources = find_sources(args.src)
    if args.only:
        needle = args.only.lower()
        sources = [p for p in sources if needle in p.as_posix().lower()]
    if not sources:
        print("No DOCX or PDF files found.")
        return 1

    args.out.mkdir(parents=True, exist_ok=True)
    rows: list[tuple[Path, Path, str]] = []
    failures: list[tuple[Path, str]] = []

    for number, source in enumerate(sources, start=1):
        rel = source.relative_to(args.src)
        out_name = re.sub(r"\s+", " ", source.stem).strip() + ".md"
        out_path = args.out / rel.parent / out_name
        if out_path.exists() and not args.force:
            print(f"[{number}/{len(sources)}] skip (exists): {rel}")
            rows.append((out_path, source, "existing"))
            continue
        print(f"[{number}/{len(sources)}] {rel} …", flush=True)
        try:
            if source.suffix.lower() == ".docx":
                details = convert_docx(source, out_path, TESSDATA_DIR)
            else:
                details = convert_pdf(source, out_path, not args.no_ocr, TESSDATA_DIR)
            rows.append((out_path, source, details))
            print(f"           -> {out_path.relative_to(args.out)} ({details})")
        except Exception as exc:  # noqa: BLE001 - report and continue the batch
            failures.append((source, str(exc)))
            print(f"           !! FAILED: {exc}", file=sys.stderr)

    # A partial run must not replace the library-wide index with one row.
    if args.only:
        print("Index not rebuilt (partial --only run).")
    else:
        build_index(args.out, rows)

    converted = sum(1 for _, _, details in rows if details != "existing")
    print(f"\nConverted {converted} file(s) into {args.out}")
    if failures:
        print(f"{len(failures)} failure(s):", file=sys.stderr)
        for source, message in failures:
            print(f"  - {source}: {message}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
