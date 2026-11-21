# Copy 4 AI (cp4ai)

Copy 4 AI turns `.docx`, `.pdf` and `.pptx` files into recall-first Markdown
for LLM ingestion, either on the clipboard or as `.md` files.

This repository is the **macOS app and CLI**, version 3.1.0. The Linux port
lives in [cp4ai-linux](https://github.com/titusng0110/cp4ai-linux).

The pipeline is recall-first: every source word matters. OCR errors, duplicate
text and imperfect formatting are acceptable because the downstream LLM can
interpret them; silently dropping a point is not recoverable.

## What is included

- **Finder Quick Actions** — select DOCX/PDF/PPTX files, right-click →
  Quick Actions → **Copy 4 AI** (OCR) or **Copy 4 AI (no OCR)**. A small
  progress panel shows the work and the concatenated Markdown lands on the
  clipboard.
- **`cp4ai`** — the same conversion from a terminal, copying to the clipboard.
- **`md4ai`** — writes `<source>.pdf.md`, `<source>.docx.md` or
  `<source>.pptx.md` next to the input.
- Headings, lists, tables, footnotes, comments, speaker notes, page and slide
  boundaries, and OCR text from images are preserved.
- OCR runs through Apple's Vision framework using the current Swift
  `RecognizeTextRequest` API. Tesseract is not used or supported.
- The DMG bundles Pandoc, librsvg, libemf2svg and a PyInstaller build of
  PyMuPDF. Users do **not** need Python, uv, Homebrew or Tesseract.

Released under the MIT License. Bundled third-party components and their
licenses are listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Install

Requirements: **Apple Silicon** and **macOS 15 or later**.

1. Download `Copy4AI-3.1.0-arm64.dmg` from GitHub Releases.
2. Open the DMG and drag **Copy 4 AI.app** to Applications.
3. Open the app once from Applications. It registers the Finder Quick Action,
   installs the `cp4ai`/`md4ai` command-line tools, adds `~/.local/bin` to
   `PATH` in `~/.zprofile`, and exits; there is no main window.
4. Restart the terminal, then use `cp4ai` or `md4ai`.

The app is ad-hoc signed. On first launch macOS may require
**right-click → Open** (or System Settings → Privacy & Security → Open Anyway).

On first launch the app installs:

```
~/.local/bin/cp4ai
~/.local/bin/md4ai
```

both pointing at the app's embedded CLI, and appends a marked block to
`~/.zprofile` so `~/.local/bin` is on `PATH`. Open a new terminal after the
first launch. To use the Quick Actions, select DOCX/PDF/PPTX files in Finder,
then right-click → **Quick Actions** → **Copy 4 AI** or
**Copy 4 AI (no OCR)**.

To remove everything:

```bash
rm -rf "/Applications/Copy 4 AI.app"
rm -f "$HOME/.local/bin/cp4ai" "$HOME/.local/bin/md4ai"
# Then remove the "Copy 4 AI command-line tools" block from ~/.zprofile.
```

The Quick Actions disappear with the app after Finder refreshes its Services.

## CLI

```bash
cp4ai                          # prints help
cp4ai a.docx b.pdf             # convert and copy to clipboard
cp4ai --no-ocr --jobs 4 ...
cp4ai --languages en-US,zh-Hans ...

md4ai                          # prints help
md4ai a.pdf                    # writes a.pdf.md next to it
md4ai -rf notes/               # recursive, overwrite
md4ai -o out/ -r notes/        # preserve the directory tree under out/
```

Options common to both commands:

| Option | Meaning |
| --- | --- |
| `--no-ocr` | Skip OCR (no Vision requests) |
| `--jobs N` | Parallel workers (default: CPU cores) |
| `--languages LIST` | OCR languages, comma separated (default: `en-US`) |
| `--version` | Print the version |

`md4ai` also accepts `-r/--recursive`, `-f/--force`, and `-o/--out`.

## OCR

OCR uses Apple Vision's `RecognizeTextRequest` (revision 3) with language
correction. Images are flattened onto white before recognition. The default
language is `en-US`; pass additional languages with `--languages`, for example:

```bash
md4ai --languages en-US,zh-Hans slides.pptx
```

PDF pages keep their digital text layer. Text that exists only inside images
(screenshots, scans, diagrams) is appended under a marked OCR comment. EMF+
bitmaps are parsed directly in Swift; EMF and SVG are rendered with the bundled
`emf2svg-conv` and `rsvg-convert`.

## Output

- YAML front matter with source path, format, date, page/slide counts and tool
  versions.
- PDF pages marked `<!-- page N of M -->`, slides marked
  `<!-- slide N of M -->`.
- DOCX comments next to their anchored passage, with author and date; comments
  without an anchor go into an appendix.
- PPTX speaker notes and comments after each slide.
- Image OCR under a clear `Image text (OCR)` blockquote, plus picture
  coordinates for PPTX.
- DOCX floating images that Pandoc cannot place in the body in a
  `## Figures from the original document (OCR text)` section.

Image files are never copied into the output.

## Architecture

```
Copy 4 AI.app
├── Copy 4 AI          AppKit Quick Action handler + progress panel
├── cp4ai              CLI binary (also invoked as md4ai)
└── Contents/Resources
    ├── bin/           Pandoc, rsvg-convert, emf2svg-conv + dylibs
    ├── pdf-helper/    PyInstaller bundle: PyMuPDF + layout model
    ├── tiktoken/      cl100k_base vocabulary
    └── fonts.conf
```

- The Swift core (`Packages/CP4AICore`) owns DOCX/PPTX parsing, Markdown
  assembly, Vision OCR, EMF+ extraction and token counting.
- Python is used only by the PDF helper, which returns page Markdown and
  pre-merged OCR region PNGs. Swift performs the OCR.
- Exact `cl100k_base` token counts are computed in Swift; no tiktoken Python
  package ships in the app.
- `ftfy`-style double-encoded UTF-8 repair was removed in this rewrite.

## Build from source

Requirements: Xcode, [XcodeGen](https://github.com/yonaskolb/XcodeGen),
`create-dmg`, `uv`, Python 3 and Docker-free macOS tooling.

```bash
brew install xcodegen create-dmg
./packaging/build_app.sh
```

The script fetches Pandoc/librsvg/libemf2svg, builds the PyMuPDF helper with
PyInstaller, generates the Xcode project, builds the Release app, signs the
nested binaries ad-hoc, and writes:

```
dist/Copy4AI-3.1.0-arm64.dmg
```

For development:

```bash
swift test --package-path Packages/CP4AICore
xcodebuild -project Copy4AI.xcodeproj -scheme Copy4AI -configuration Debug \
    -derivedDataPath build/DerivedData build
```

## Known limitations

- Apple Silicon only; PyMuPDF 2.1 publishes an arm64 macOS wheel.
- Ad-hoc signing means the first launch needs right-click → Open. Notarization
  can be added with a Developer ID certificate.
- The app is not sandboxed because it spawns Pandoc and the PDF helper.
- PyMuPDF is AGPL-3.0; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
