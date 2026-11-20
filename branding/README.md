# Copy 4 AI branding

The logo is a black ring and black `CP4AI` text on a white disc. Everything
outside the ring is transparent; the disc inside the ring stays opaque white.

| File | Use |
|---|---|
| `CP4AI-logo.png` | 2400×2400 master, transparent outside |
| `CP4AI-logo-1024.png` | 1024×1024 general use |
| `CP4AI-logo.svg` | vector logo (ring + traced text) |
| `CP4AI-logo.pdf` | vector PDF export |
| `CP4AI.icns` | macOS app icon |
| `CP4AI-source.png` | original 2000×2000 PNG |

Regenerate with:

```bash
.venv/bin/python branding/make_logo.py
```

`make_logo.py` needs Pillow, NumPy and `potrace` for the SVG text trace;
`rsvg-convert` is used for the PDF export.
