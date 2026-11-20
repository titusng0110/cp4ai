#!/usr/bin/env python3
"""Build the Copy 4 AI logo assets from the preliminary 2000x2000 PNG.

The source is a black ring with "CP4AI" inside on a white square. The ring is
inscribed in the canvas, so the outside white is removed and a small margin is
added. The interior disc stays opaque white; the ring and text stay black.

Outputs:
    CP4AI-logo.png       2400x2400 transparent PNG
    CP4AI-logo-1024.png  1024x1024 transparent PNG
    CP4AI-logo.svg       vector logo
    CP4AI-logo.pdf       vector PDF
    CP4AI.icns           macOS app icon
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "CP4AI-source.png"

SRC_SIZE = 2000
SRC_CX = SRC_CY = 1000.0
R_OUT = 1000.0
R_IN = 900.0
TEXT_RADIUS = 870.0
PADDING = 200
SIZE = SRC_SIZE + PADDING * 2
CX = CY = SIZE / 2


def clamp(values: np.ndarray) -> np.ndarray:
    return np.clip(values, 0.0, 1.0)


def build_pngs() -> Image.Image:
    source = np.asarray(Image.open(SOURCE).convert("L"), dtype=np.uint8)

    yy, xx = np.ogrid[:SIZE, :SIZE]
    distance = np.hypot(xx - CX, yy - CY)

    disc_alpha = clamp(R_IN + 0.5 - distance)
    ring_alpha = clamp(R_OUT + 0.5 - distance) * clamp(
        distance - (R_IN - 0.5)
    )

    disc = np.zeros((SIZE, SIZE, 4), dtype=np.uint8)
    disc[..., 0:3] = 255
    disc[..., 3] = np.round(disc_alpha * 255).astype(np.uint8)

    sy, sx = np.ogrid[:SRC_SIZE, :SRC_SIZE]
    source_radius = np.hypot(sx - SRC_CX, sy - SRC_CY)
    text_alpha = np.where(
        source_radius < TEXT_RADIUS,
        255 - source,
        0,
    ).astype(np.uint8)
    text = np.zeros((SIZE, SIZE, 4), dtype=np.uint8)
    text[
        PADDING : PADDING + SRC_SIZE,
        PADDING : PADDING + SRC_SIZE,
        3,
    ] = text_alpha

    ring = np.zeros((SIZE, SIZE, 4), dtype=np.uint8)
    ring[..., 3] = np.round(ring_alpha * 255).astype(np.uint8)

    canvas = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    canvas = Image.alpha_composite(canvas, Image.fromarray(disc, "RGBA"))
    canvas = Image.alpha_composite(canvas, Image.fromarray(text, "RGBA"))
    canvas = Image.alpha_composite(canvas, Image.fromarray(ring, "RGBA"))

    canvas.save(ROOT / "CP4AI-logo.png")
    canvas.resize((1024, 1024), Image.Resampling.LANCZOS).save(
        ROOT / "CP4AI-logo-1024.png"
    )
    return canvas


def build_svg(canvas: Image.Image) -> None:
    """Trace the text and draw the ring as exact vector geometry."""
    text_full = np.full((SIZE, SIZE), 255, dtype=np.uint8)
    # Recover the text mask from the source at the output offset. Potrace
    # treats black as foreground, so keep the original black letters and a
    # white background.
    source = np.asarray(Image.open(SOURCE).convert("L"), dtype=np.uint8)
    sy, sx = np.ogrid[:SRC_SIZE, :SRC_SIZE]
    source_radius = np.hypot(sx - SRC_CX, sy - SRC_CY)
    text_full[
        PADDING : PADDING + SRC_SIZE,
        PADDING : PADDING + SRC_SIZE,
    ] = np.where(source_radius < TEXT_RADIUS, source, 255).astype(np.uint8)

    with tempfile.TemporaryDirectory(prefix="cp4ai_logo_") as tmp:
        tmp_path = Path(tmp)
        pgm = tmp_path / "text.pgm"
        svg = tmp_path / "text.svg"
        Image.fromarray(text_full, "L").save(pgm)
        subprocess.run(
            ["potrace", "-s", "-o", str(svg), str(pgm)],
            check=True,
            capture_output=True,
            text=True,
        )
        raw = svg.read_text(encoding="utf-8")

    match = re.search(r"<svg[^>]*>(.*)</svg>", raw, re.DOTALL)
    if not match:
        raise RuntimeError("potrace produced no SVG paths")
    paths = match.group(1).strip()

    centerline = (R_OUT + R_IN) / 2
    stroke = R_OUT - R_IN
    composed = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{SIZE}" height="{SIZE}" viewBox="0 0 {SIZE} {SIZE}">
  <title>Copy 4 AI</title>
  <circle cx="{CX}" cy="{CY}" r="{R_IN}" fill="#ffffff"/>
  <circle cx="{CX}" cy="{CY}" r="{centerline}" fill="none" stroke="#000000" stroke-width="{stroke}"/>
  {paths}
</svg>
'''
    (ROOT / "CP4AI-logo.svg").write_text(composed, encoding="utf-8")


def build_pdf() -> None:
    rsvg = shutil.which("rsvg-convert")
    if not rsvg:
        bundled = ROOT.parent / "packaging" / "native" / "bin" / "rsvg-convert"
        rsvg = str(bundled) if bundled.exists() else None
    if not rsvg:
        raise RuntimeError("rsvg-convert is required for the PDF export")
    subprocess.run(
        [
            rsvg,
            "-f",
            "pdf",
            "-o",
            str(ROOT / "CP4AI-logo.pdf"),
            str(ROOT / "CP4AI-logo.svg"),
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def build_icns(canvas: Image.Image) -> None:
    iconset = ROOT / "CP4AI.iconset"
    if iconset.exists():
        shutil.rmtree(iconset)
    iconset.mkdir()
    sizes = [
        (16, "icon_16x16.png"),
        (32, "icon_16x16@2x.png"),
        (32, "icon_32x32.png"),
        (64, "icon_32x32@2x.png"),
        (128, "icon_128x128.png"),
        (256, "icon_128x128@2x.png"),
        (256, "icon_256x256.png"),
        (512, "icon_256x256@2x.png"),
        (512, "icon_512x512.png"),
        (1024, "icon_512x512@2x.png"),
    ]
    for size, name in sizes:
        canvas.resize((size, size), Image.Resampling.LANCZOS).save(
            iconset / name
        )
    subprocess.run(
        [
            "iconutil",
            "-c",
            "icns",
            str(iconset),
            "-o",
            str(ROOT / "CP4AI.icns"),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    shutil.rmtree(iconset)


def main() -> int:
    canvas = build_pngs()
    build_svg(canvas)
    build_pdf()
    build_icns(canvas)

    print(f"logo: {ROOT / 'CP4AI-logo.png'}")
    print(f"1024: {ROOT / 'CP4AI-logo-1024.png'}")
    print(f"svg:  {ROOT / 'CP4AI-logo.svg'}")
    print(f"pdf:  {ROOT / 'CP4AI-logo.pdf'}")
    print(f"icns: {ROOT / 'CP4AI.icns'}")
    for point in [(0, 0), (int(CX), 400), (int(CX), int(CY))]:
        print(point, canvas.getpixel(point))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
