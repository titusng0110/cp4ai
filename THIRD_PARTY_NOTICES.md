# Third-party notices

Copy 4 AI itself is released under the MIT License.

The app bundles separate executables and libraries. They are unmodified apart
from relocating dynamic-library paths and stripping build metadata where
needed.

## Bundled executables

- **Pandoc 3.14** — GPL-2.0-or-later
  https://github.com/jgm/pandoc
- **librsvg / rsvg-convert 2.63.4** — LGPL-2.1-or-later
  https://gitlab.gnome.org/GNOME/librsvg
- **libemf2svg / emf2svg-conv 1.8.1** — GPL-2.0-only
  https://github.com/kakwa/libemf2svg

## Bundled librsvg/libemf2svg dependencies

Cairo, GLib, Pango, HarfBuzz, Fontconfig, FreeType, gettext, libpng, Pixman,
FriBidi, Graphite2, X11/XCB libraries and their transitive dependencies are
included with the two converters. Upstream source and licenses:

- https://gitlab.freedesktop.org/cairo/cairo
- https://gitlab.gnome.org/GNOME/glib
- https://gitlab.gnome.org/GNOME/pango
- https://github.com/harfbuzz/harfbuzz
- https://gitlab.freedesktop.org/fontconfig/fontconfig
- https://gitlab.freedesktop.org/freetype/freetype
- https://www.gnu.org/software/gettext/
- https://www.libpng.org/pub/png/libpng.html
- https://gitlab.freedesktop.org/pixman/pixman
- https://github.com/fribidi/fribidi
- https://github.com/silnrsi/graphite
- https://www.x.org/

Homebrew bottle metadata, including exact versions and source URLs, is
available from https://formulae.brew.sh/.

## PDF helper (PyInstaller)

- **PyMuPDF / pymupdf4llm / pymupdf-layout** — AGPL-3.0
  https://github.com/pymupdf/PyMuPDF
- **ONNX Runtime** — MIT
  https://github.com/microsoft/onnxruntime
- **NumPy** — BSD-3-Clause
  https://numpy.org/
- **NetworkX** — BSD-3-Clause
  https://networkx.org/
- **PyYAML** — MIT
  https://pyyaml.org/
- **tabulate** — MIT
  https://github.com/astanin/python-tabulate
- **psutil** — BSD-3-Clause
  https://github.com/giampaolo/psutil
- **Python** — PSF-2.0
  https://www.python.org/

## Tokenizer data

- **`cl100k_base.tiktoken`** — MIT
  https://github.com/openai/tiktoken

## Apple frameworks

Apple Vision (`RecognizeTextRequest`), AppKit, Foundation and ImageIO are
provided by macOS and are not distributed with the app.

## Removed in 3.1.0

Tesseract, ocrmac, Pillow and ftfy are no longer bundled or used.
