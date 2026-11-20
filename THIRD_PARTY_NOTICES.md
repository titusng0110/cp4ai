# Third-party notices

Copy 4 AI itself is released under the MIT License. The macOS app bundle
includes the following separate programs and libraries. They are unmodified
apart from relocating dynamic-library paths so they load from inside the app.

## Bundled executables

- **Pandoc 3.14** — GPL-2.0-or-later
  https://github.com/jgm/pandoc
- **librsvg / rsvg-convert 2.63.4** — LGPL-2.1-or-later
  https://gitlab.gnome.org/GNOME/librsvg
- **libemf2svg / emf2svg-conv 1.8.1** — GPL-2.0-only
  https://github.com/kakwa/libemf2svg

## Bundled librsvg/libemf2svg dependencies

The app bundles the dynamic libraries required by the two converters,
including Cairo, GLib, Pango, HarfBuzz, Fontconfig, FreeType, gettext,
libpng, Pixman, FriBidi, Graphite2, X11/XCB libraries, and their transitive
dependencies. Their upstream licenses and source are available from:

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

## Python packages

- **PyMuPDF / pymupdf4llm / pymupdf-layout** — AGPL-3.0
  https://github.com/pymupdf/PyMuPDF
- **ONNX Runtime** — MIT
  https://github.com/microsoft/onnxruntime
- **Tiktoken** — MIT
  https://github.com/openai/tiktoken
- **ocrmac** — MIT
  https://github.com/straussmaximilian/ocrmac
- **PyObjC** — MIT
  https://github.com/ronaldoussoren/pyobjc
- **NumPy** — BSD-3-Clause
  https://numpy.org/
- **Pillow** — HPND
  https://python-pillow.org/
- **tabulate** — MIT
  https://github.com/astanin/python-tabulate
- **ftfy** — Apache-2.0
  https://github.com/rspeer/python-ftfy
- **wcwidth** — MIT
  https://github.com/jquast/wcwidth
- **psutil** — BSD-3-Clause
  https://github.com/giampaolo/psutil
- **PyYAML** — MIT
  https://pyyaml.org/
- **Python** — PSF-2.0
  https://www.python.org/

## Optional

Tesseract is **not** bundled. If a CLI user installs it with Homebrew, it is
covered by the Apache-2.0 license: https://github.com/tesseract-ocr/tesseract
