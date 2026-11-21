# Copy 4 AI (cp4ai)

## 1. Intro

Copy 4 AI turns `.docx`, `.pdf` and `.pptx` files into Markdown that is ready
to paste into ChatGPT, Claude or any other AI chat.

It is **recall-first**: every word in the source matters. OCR mistakes,
duplicate text and imperfect formatting are acceptable because the AI can
interpret them; silently dropping a sentence or a table row is not.

Copy 4 AI gives you four ways to work:

- **Copy 4 AI** — a Finder Quick Action that converts files and copies the
  result to the clipboard.
- **Copy 4 AI (no OCR)** — the same action without reading text from images,
  useful when the files already have a good text layer.
- **`cp4ai`** — the clipboard workflow from a terminal.
- **`md4ai`** — the same conversion, written to `.md` files instead.

It keeps headings, lists, tables, footnotes, comments, speaker notes, page and
slide boundaries, and text found inside images. Everything runs locally:
files are never uploaded, and there is no account or network requirement.
You do not need Python, Homebrew, Tesseract or any other extra software.

Released under the MIT License. Bundled third-party components are listed in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## 2. Setup

### Requirements

- Apple Silicon Mac
- macOS 15 or later

### Install

1. Download `Copy4AI-3.1.0-arm64.dmg`.
2. Open the DMG and drag **Copy 4 AI.app** to Applications.
3. Open **Copy 4 AI** once from Applications.
4. Click **OK** on the welcome dialog.

That first launch does the rest:

- registers **Copy 4 AI** and **Copy 4 AI (no OCR)** in Finder → Quick
  Actions;
- installs `~/.local/bin/cp4ai` and `~/.local/bin/md4ai`;
- adds `~/.local/bin` to your `PATH` in `~/.zprofile`.

Open a new terminal after this if you want to use the command-line tools.

The app is ad-hoc signed. If macOS refuses to open it, right-click the app and
choose **Open** once (or use System Settings → Privacy & Security → Open
Anyway). Running it directly from the mounted DMG shows a warning; install it
in Applications first.

The welcome dialog is shown whenever you double-click the app. It is only a
reminder; the app has no main window.

### If Finder does not show the Quick Actions

Launch the app once, then relaunch Finder. You can also refresh the Services
database manually:

```bash
/System/Library/CoreServices/pbs -flush
```

### Update

Quit the app, replace it in Applications with the new version, and open it
once. The Quick Actions, command-line links and PATH entry are refreshed
automatically.

### Uninstall

```bash
rm -rf "/Applications/Copy 4 AI.app"
rm -f "$HOME/.local/bin/cp4ai" "$HOME/.local/bin/md4ai"
```

Then remove the block marked `Copy 4 AI command-line tools` from
`~/.zprofile`. The Finder Quick Actions disappear after Finder refreshes its
Services list.

### Build from source

Requirements: Xcode, [XcodeGen](https://github.com/yonaskolb/XcodeGen),
`create-dmg`, `uv` and Python 3.

```bash
brew install xcodegen create-dmg
./packaging/build_app.sh
```

The script fetches Pandoc, librsvg and libemf2svg, builds the PyMuPDF helper
with PyInstaller, generates the Xcode project, builds the Release app, signs it
ad-hoc and writes:

```text
dist/Copy4AI-3.1.0-arm64.dmg
```

For core tests:

```bash
swift test --package-path Packages/CP4AICore
```

Logs are written to `~/Library/Logs/Copy 4 AI.log`.

## 3. Usage

### Finder Quick Actions

1. Select one or more `.docx`, `.pdf` or `.pptx` files in Finder.
2. Right-click → **Quick Actions**.
3. Choose **Copy 4 AI** (read text from images too) or **Copy 4 AI (no OCR)**
   (faster; images are skipped).
4. When the progress panel finishes, paste into your AI chat.

Each file is wrapped in markers so the AI can tell documents apart:

```text
[a.pdf BEGIN]
...
[a.pdf END]

[b.docx BEGIN]
...
[b.docx END]
```

The clipboard is only changed when every file succeeds. Errors stay in the
progress panel, and details go to the log. Directories are not accepted; select
files instead.

### `cp4ai` — clipboard

```bash
cp4ai                          # print help; no GUI is opened
cp4ai a.docx b.pdf             # convert and copy the combined result
cp4ai --no-ocr a.pdf           # skip OCR
cp4ai --jobs 4 notes/*.pptx    # four workers
cp4ai --languages en-US,zh-Hans slides.pptx
```

On success it prints:

```text
=========================
Copied to clipboard! (26524 characters / 5980 tokens)
```

If any file fails, the clipboard is left untouched and the command exits with
a non-zero status.

| Option | Meaning |
| --- | --- |
| `--no-ocr` | Do not read text from images |
| `--jobs N` | Parallel workers (default: all active CPU cores) |
| `--languages LIST` | OCR languages, comma separated (default: `en-US`) |
| `-h`, `--help` | Show help |
| `--version` | Show the version |

### `md4ai` — Markdown files

```bash
md4ai a.pdf                    # writes a.pdf.md next to a.pdf
md4ai a.docx                   # writes a.docx.md
md4ai -r notes/                # every supported file under notes/
md4ai -rf notes/               # recursive, overwrite existing .md
md4ai -o b.md a.pdf            # write exactly b.md
md4ai -o out/ -r notes/        # preserve the tree under out/
md4ai --no-ocr scanned.pdf
```

Output names never collide with the source: `name.pdf` becomes
`name.pdf.md`, and the same pattern applies to DOCX and PPTX.

| Option | Meaning |
| --- | --- |
| `-r`, `--recursive` | Convert every supported file under a directory |
| `-f`, `--force` | Overwrite existing Markdown |
| `-o`, `--out` | Output file, or directory preserving the input tree |
| `--no-ocr` | Do not read text from images |
| `--jobs N` | Parallel workers (default: all active CPU cores) |
| `--languages LIST` | OCR languages, comma separated (default: `en-US`) |
| `-h`, `--help` | Show help |
| `--version` | Show the version |

`-rf` and `-r -f` are equivalent. Directory input requires `-r`. A path ending
in `.md` is treated as a file; anything else is treated as a directory.

### What the Markdown contains

- YAML front matter with source path, format, date, page/slide counts, Pandoc
  version and OCR mode.
- PDF pages marked `<!-- page N of M -->`; PPTX slides marked
  `<!-- slide N of M -->`.
- Image text under a clearly marked `Image text (OCR)` blockquote.
- DOCX comments next to the passage they annotate, with author and date.
  Comments without an anchor go into an appendix.
- PPTX speaker notes and comments after their slide.
- DOCX floating/anchored images that Pandoc cannot place in the body in a
  `## Figures from the original document (OCR text)` section.
- A `## Vector images (not OCR'd)` list if an EMF/SVG drawing could not be
  rendered.

Image files themselves are never copied into the Markdown.

## 4. Design / Algorithm

### Architecture

```text
Copy 4 AI.app
├── Copy 4 AI          AppKit Quick Action handler + progress panel
├── cp4ai              CLI (also invoked as md4ai)
└── Contents/Resources
    ├── bin/           pandoc, rsvg-convert, emf2svg-conv + dylibs
    ├── pdf-helper/    PyInstaller bundle: PyMuPDF + layout model
    ├── tiktoken/      cl100k_base vocabulary
    └── fonts.conf
```

The Swift app and CLI share `CP4AICore`. The app is a native Finder service:
it declares two `NSServices` entries and shows only the floating progress
panel. There is no document window and no sandbox, because the app launches
Pandoc, the PDF helper and the vector converters.

Python is used for one job only: a small PyInstaller helper reads PDFs with
PyMuPDF and returns page Markdown plus pre-merged OCR-region PNGs. Swift does
all OCR, text merging and Markdown assembly.

### DOCX

1. Pandoc converts the document to GitHub-flavored Markdown with headings,
   lists, tables, footnotes, text boxes and tracked changes preserved.
2. Every Markdown image link and raw `<img>` tag is replaced by the OCR text.
   Table cells get inline OCR so the table stays valid; other images become
   blockquotes. Images with identical bytes are OCR'd once.
3. Floating drawings that Pandoc extracts but cannot place in the body are
   OCR'd in a figures section at the end.
4. `word/comments.xml` and `word/document.xml` are parsed in Swift. Comments
   are placed after the passage they annotate; unanchored comments go into an
   appendix.
5. Unusual images are rasterised before OCR:
   - EMF+ bitmaps are read directly from the EMF record in Swift;
   - classic EMF goes through `emf2svg-conv`, then `rsvg-convert`;
   - SVG goes through `rsvg-convert`.
6. The media directory is temporary and deleted afterwards.

### PDF

1. The PyMuPDF helper extracts the native text layer page by page with layout
   enabled and its own OCR disabled.
2. It also finds image regions, merges fragments, renders them at 300 dpi and
   returns them as PNGs with their SHA-256.
3. Swift OCRs foreground regions first. If a page has little native text and
   the foreground result is thin, the full-page background image is OCR'd as a
   fallback.
4. OCR that only repeats the native text layer is removed.
5. Pages are marked `<!-- page N of M -->`; OCR text is appended on the same
   page under a marked comment.

### PPTX

1. Pandoc converts slides to GitHub-flavored Markdown; slide titles become
   level-2 headings.
2. Swift parses the PPTX XML for slide order, speaker notes, comments and
   picture coordinates.
3. Slides are marked `<!-- slide N of M -->`.
4. Images are replaced by OCR text. When a picture position is available it is
   appended as percentages rounded to the nearest 10%:
   `**Position:** [top: 45%, left: 60%, width: 40%, height: 20%]`.
5. Speaker notes and comments are appended at the end of their slide.

### OCR

OCR uses Apple's current Swift Vision API, `RecognizeTextRequest` (revision 3),
at accurate recognition level with language correction enabled.

- Transparent images are flattened onto white first.
- Observations are sorted top-to-bottom and left-to-right, then joined by
  line.
- The default language is `en-US`; `--languages` adds others, for example
  `en-US,zh-Hans`.
- Each page/region result is cached by a SHA-256 of its pixels, so identical
  regions are never OCR'd twice.
- OCR is dropped only when an image yields fewer than 10 non-space characters,
  or when its words are already present in the native text layer.

### Vector images

- **EMF+** records are parsed in Swift: the embedded BGRA/BGR bitmap is
  extracted, alpha-flattened onto white and written as PNG with CoreGraphics.
- **EMF** is converted to SVG with `emf2svg-conv`, then to PNG with
  `rsvg-convert`.
- **SVG** is rendered with `rsvg-convert`.
- If none of these produce an image, the file is listed under
  `## Vector images (not OCR'd)` rather than silently dropped.

### Markdown and token counts

The Markdown is assembled in Swift: front matter, title, body, figures,
comments and page/slide markers. `cp4ai` reports exact `cl100k_base` token
counts using a BPE implementation and the bundled vocabulary, so its numbers
match tiktoken without shipping the Python package.

### Parallelism and progress

The CLI defaults to one worker per active CPU core. The Quick Actions use
`min(cpu cores, 6)` so Vision does not exhaust memory. `--jobs N` overrides
the CLI default.

Before conversion, Copy 4 AI estimates pages and OCR jobs. The progress panel
combines both counters:

```text
3/10 pages + 2/5 OCR
```

### Design choices

- **Recall before cleanliness.** OCR errors and formatting noise are kept
  because the downstream AI can interpret them; losing a point is not
  recoverable.
- **Native text first.** OCR is additive and is removed only when it duplicates
  the text layer.
- **Images never enter the output.** Only their recognized text does.
- **Comments stay in context.** DOCX comments follow their anchored passage;
  PPTX notes and comments follow their slide.
- **Page and slide markers are HTML comments**, so they remain searchable
  without rendering.
- **Everything is local.** No uploads, no accounts and no network calls during
  conversion.
- **Bundled, not installed.** Pandoc, librsvg, libemf2svg, PyMuPDF and the
  tokenizer vocabulary live inside the app; users do not need Homebrew, Python
  or Tesseract.
