#!/usr/bin/env python3
"""Generate the Copy 4 AI DMG background with install instructions."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
WIDTH, HEIGHT = 1320, 840
BACKGROUND = "#f7f7f9"
INK = "#1d1d1f"
MUTED = "#6e6e73"
ARROW = "#86868b"


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    name = "Arial Bold.ttf" if bold else "Arial.ttf"
    return ImageFont.truetype(f"/System/Library/Fonts/Supplemental/{name}", size)


def main() -> int:
    image = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(image)

    title = "Drag Copy 4 AI to Applications"
    title_font = font(44, bold=True)
    title_width = draw.textlength(title, font=title_font)
    draw.text(
        ((WIDTH - title_width) / 2, 84),
        title,
        font=title_font,
        fill=INK,
    )

    subtitle = "Then go to Applications and double click on Copy 4 AI.app"
    subtitle_font = font(44, bold=True)
    subtitle_width = draw.textlength(subtitle, font=subtitle_font)
    draw.text(
        ((WIDTH - subtitle_width) / 2, 164),
        subtitle,
        font=subtitle_font,
        fill=INK,
    )

    arrow_y = 460
    draw.line((524, arrow_y, 784, arrow_y), fill=ARROW, width=6)
    draw.polygon(
        [(784, arrow_y - 16), (784, arrow_y + 16), (816, arrow_y)],
        fill=ARROW,
    )

    image.save(ROOT / "dmg-background.png", dpi=(144, 144))
    print(ROOT / "dmg-background.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
