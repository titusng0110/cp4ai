# Copy 4 AI 3.1.0

This release replaces the Python app with a Swift-native shell and an Apple
Vision OCR pipeline.

## Highlights

- **Swift app** — the Quick Action handler and floating progress panel are now
  AppKit/Swift, with a shared Swift core for DOCX, PPTX and PDF conversion.
- **No main window** — the Finder Quick Actions are the only GUI. The app
  registers itself as a native Finder service and exits when idle.
- **Two Quick Actions** — **Copy 4 AI** uses Apple Vision OCR; **Copy 4 AI
  (no OCR)** skips OCR entirely and marks images as omitted.
- **Apple Vision OCR** — uses the current Swift `RecognizeTextRequest`
  API. Tesseract and the `--tesseract`/`--livetext` flags are gone.
- **Python only for PDF parsing** — a small PyInstaller helper built around
  PyMuPDF returns page Markdown and OCR region PNGs. Swift performs all OCR.
- **Bundled tools** — Pandoc 3.14, librsvg, libemf2svg and the PyMuPDF helper
  ship inside the DMG. Users need no Python, uv, Homebrew or Tesseract.
- **Exact token counts** — `cl100k_base` BPE is implemented in Swift with the
  bundled vocabulary, so `cp4ai` reports the same counts as tiktoken.
- **Swift EMF+ parser** — EMF+ bitmaps are decoded with CoreGraphics; numpy is
  no longer part of the app.
- **CLI included** — `cp4ai` and `md4ai` are embedded in the app. The app
  installs both symlinks and adds `~/.local/bin` to `PATH` on first launch;
  there is no separate installer step.
- **One install** — dragging the app to Applications followed by one launch
  installs the Quick Action and the command-line tools.

## CLI changes

- `cp4ai` with no arguments prints help; it no longer launches a GUI.
- `cp4ai` copies to the clipboard, `md4ai` writes Markdown files.
- `--jobs` defaults to all active CPU cores for both commands.
- `--languages` selects Vision recognition languages (default `en-US`).
- The Quick Action processes at most `min(cpu cores, 6)` files concurrently.

## Removed

- Tesseract integration, `ocrmac`, Pillow, numpy and ftfy.
- The Python GUI, uv/Homebrew runtime dependencies and the Automator workflow.
- `--tesseract` and `--livetext` flags.

## Compatibility

- macOS 15 or later, Apple Silicon.
- The app is ad-hoc signed; first launch may require right-click → Open.
- PyMuPDF is AGPL-3.0; see `THIRD_PARTY_NOTICES.md`.
