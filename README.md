# Copy 4 AI (cp4ai)

## Intro

Copy 4 AI copies text from lecture notes into Markdown for downstream LLM
ingestion. It accepts `.docx`, `.pdf` and `.pptx` files.

The pipeline is **recall-first**: every source word matters. OCR errors,
duplicate text and imperfect formatting are acceptable because the downstream
LLM can interpret them; silently dropping a point is not recoverable.

- **macOS app** — GUI-only, with a **Copy 4 AI** Finder Quick Action and a
  small progress window.
- **CLI** — `md4ai` writes Markdown files; `cp4ai` copies the converted chain
  to the clipboard.
- Headings, lists, tables, footnotes, comments, speaker notes, page and slide
  boundaries, and OCR text from images are preserved.
- OCR defaults to Apple Live Text; Tesseract is optional in the CLI.
- CLI file output is `<source>.pdf.md`, `<source>.docx.md` or
  `<source>.pptx.md`, so it never collides with the input file.

Released under the MIT License. Bundled third-party components and their
licenses are listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Setup

### GUI (macOS app)

Requirements: **Apple Silicon**, **macOS 15 or later**.

1. Download `Copy4AI-3.0.0-arm64.dmg` from
   [GitHub Releases](https://github.com/titusng0110/cp4ai/releases).
2. Open the DMG. The installer window says **Drag Copy 4 AI to Applications**
   and **Then go to Applications and double click on Copy 4 AI.app**. Drag
   the app onto the Applications shortcut.
3. In Applications, double-click **Copy 4 AI** once. It installs the
   **Copy 4 AI** Finder action. Dragging the app alone does not install the
   action.

The app does not need to stay running after that; the Quick Action launches it
on demand. If Finder does not show the action immediately, open the app again
and choose **Reinstall Finder Action**, or relaunch Finder.

Running the app directly from the mounted disk shows a warning and does not
install the Finder action.

The app is self-contained: it bundles Pandoc 3.14, librsvg, libemf2svg and the
Tiktoken cache. It needs no Python, uv, Homebrew or network access.
It is **GUI-only** and does not install `cp4ai` or `md4ai` commands.

The app is ad-hoc signed. On first launch, macOS may require **right-click →
Open** (or System Settings → Privacy & Security → Open Anyway).

To remove it, drag **Copy 4 AI** to the Trash, then remove the Finder action:

```bash
rm -rf "$HOME/Library/Services/Copy 4 AI.workflow"
```

Logs are written to `~/Library/Logs/Copy 4 AI.log`.

To build the app from source (Apple Silicon, Xcode command line tools, uv,
and `create-dmg`):

```bash
brew install create-dmg
./packaging/build_app.sh
```

The script downloads the native tools at build time, bundles them into the app,
ad-hoc signs it, and writes `dist/Copy4AI-3.0.0-arm64.dmg`. The downloaded
binaries live under `packaging/native/` and are gitignored. The installer
background is `packaging/dmg-background.png`; regenerate it with
`python packaging/make_dmg_background.py`. There is no CI.

### CLI

Requirements: **macOS**, [Homebrew](https://brew.sh),
[uv](https://docs.astral.sh/uv/), and **Pandoc**:

```bash
brew install pandoc
git clone https://github.com/titusng0110/cp4ai.git
cd cp4ai
uv tool install .
```

This installs `md4ai` and `cp4ai` in `~/.local/bin`. If a command is not found,
run `uv tool update-shell` and restart the terminal (or add `~/.local/bin` to
`PATH`).

The CLI uses your own Pandoc. It auto-installs the niche `libemf2svg` and
`librsvg` helpers with Homebrew when OCR needs them. It never installs Pandoc
or Tesseract automatically.

Tesseract is opt-in:

```bash
brew install tesseract
```

Advanced controls:

```bash
CP4AI_PANDOC=/path/to/pandoc md4ai a.docx   # use a specific Pandoc
CP4AI_SKIP_SETUP=1 md4ai a.pdf              # skip the vector-image check
```

To update the CLI after pulling changes:

```bash
cd cp4ai
git pull
uv tool install --force .
```

To uninstall it:

```bash
uv tool uninstall cp4ai
```

#### App and CLI together

The DMG app and the uv CLI can coexist and do not clash:

- The app is GUI-only and never writes to `~/.local/bin`.
- The app forces its bundled Pandoc, librsvg, libemf2svg, Tiktoken cache and
  Fontconfig path. It ignores `CP4AI_PANDOC` and cache variables set for the
  CLI.
- The CLI uses `pandoc` from `PATH`, auto-installs the vector helpers with
  Homebrew, and uses Homebrew Tesseract only when requested.
- If an older app build left `cp4ai`/`md4ai` wrappers in `~/.local/bin`, the
  app removes those regular files on launch. uv symlinks are left untouched.
- Both can run at the same time; the only shared resource is the clipboard.

## Usage

### GUI

1. Select one or more `.docx`, `.pdf` or `.pptx` files in Finder.
2. Right-click → **Quick Actions** → **Copy 4 AI**.
3. The progress window shows work as it happens:

   ```text
   3/10 pages + 2/5 OCR
   ```

   The bar advances as pages and OCR jobs complete. A DOCX counts as one page,
   PDF pages count individually, and PPTX slides count individually.
4. When done, the Markdown chain is on the clipboard and the window closes.

The GUI accepts files, not directories. If an unsupported item is included, it
is skipped; if nothing valid remains, the window explains why. Each file is
wrapped with its filename:

```text
[a.pdf BEGIN]
...
[a.pdf END]

[b.docx BEGIN]
...
[b.docx END]
```

There are no notifications. Errors stay in the progress window and full details
are written to `~/Library/Logs/Copy 4 AI.log`. The app auto-closes 1.5 seconds
after the clipboard write; a helper process may linger briefly while it shuts
down.

### CLI

#### File output: `md4ai`

```bash
md4ai a.pdf                  # writes a.pdf.md next to a.pdf
md4ai a.docx                 # writes a.docx.md next to a.docx
md4ai a.pptx                 # writes a.pptx.md next to a.pptx

md4ai -r notes/              # every .docx/.pdf/.pptx under notes/, in place
md4ai -rf notes/             # same, overwriting existing .md files
md4ai -r -f notes/           # equivalent long form

md4ai -o b.md a.pdf          # write exactly b.md
md4ai -o out/ a.pdf          # write out/a.pdf.md (creates out/)
md4ai -o out/ -r notes/      # preserve notes/'s structure under out/
```

If an output file already exists, the command refuses to run unless
`-f/--force` is given. For a recursive run it checks all destinations first,
so it will not partially convert a directory and then stop.

`--out` is treated as a file when it ends in `.md`; otherwise it is treated as
a directory. A directory is created if needed.

| Option | Meaning |
|---|---|
| `-r`, `--recursive` | Convert every `.docx`/`.pdf`/`.pptx` under a directory |
| `-f`, `--force` | Overwrite existing output |
| `-o`, `--out` | Output file, or output directory preserving structure |
| `--jobs N` | Parallel worker processes (default: CPU cores) |
| `--livetext` | Apple Live Text via `ocrmac` (default) |
| `--tesseract` | Use Tesseract instead of Live Text (requires `brew install tesseract`) |
| `--no-ocr` | Do not OCR images |
| `--version` | Show version |

`-rf` and `-r -f` are equivalent. Directory inputs require `-r`.

#### Clipboard output: `cp4ai`

```bash
cp4ai a.pdf b.docx c.pptx
```

`cp4ai` uses the same conversion pipeline but writes the result to the macOS
clipboard instead of files. It accepts one or more files and does not support
directories. Each document is wrapped with `[filename BEGIN]` and
`[filename END]`.

It accepts `--tesseract`, `--no-ocr`, `--jobs N` and `--version`. If any file
fails, the clipboard is left unchanged. On success it reports the clipboard
size and the GPT-4 token count:

```text
=========================
Copied to clipboard! (12345 characters / 3000 tokens)
```

## Design / Algorithm

### Pipeline

Documents are independent. Each file is converted in its own temporary
directory, and `--jobs` controls how many run in parallel. Images stay in the
temporary directory and are never copied into the output.

### Progress

Before conversion starts, the app counts work units:

- **Pages:** PDF pages, PPTX slides, and one page per DOCX.
- **OCR jobs:** PDF image regions, DOCX media images, and PPTX pictures.

The progress text and bar combine both counters:

```text
3/10 pages + 2/5 OCR
```

The bar uses `(pages done + OCR done) / (pages total + OCR total)`. Counts are
estimates before conversion; after a successful batch the totals are
reconciled with the actual events so the display ends at 100%.

The GUI runs conversion in a worker process. This is required for Apple Live
Text, whose `VKCImageAnalyzer` path relies on a CFRunLoop and returns no
annotations when called from an ordinary background thread.

### DOCX

1. Pandoc converts the document to GitHub-flavored Markdown with headings,
   lists, tables, footnotes, text boxes and tracked changes preserved.
2. Each image is replaced by its OCR text. Markdown image links and raw
   `<img>` tags are both handled. Images inside tables become inline text so
   the table stays intact; other images become blockquotes. Identical image
   bytes are OCR'd once per document.
3. Floating drawings that Pandoc extracts but cannot place in the body are
   OCR'd in a figures section at the end.
4. DOCX comments are read from `word/comments.xml` and inserted after the
   passage they annotate, with author and date. Pandoc's comment-span anchors
   locate the passage; comments without one are listed in an appendix.
5. EMF/EMF+/SVG images are rasterised before OCR:
   - EMF+ bitmaps are extracted directly from the EMF record;
   - classic EMF is converted with `emf2svg-conv`, then `rsvg-convert`;
   - SVG uses `rsvg-convert`.
6. Images are kept in a temporary directory and deleted afterwards.

### PDF

1. PyMuPDF extracts the native text layer page by page with its layout engine
   and its own OCR disabled.
2. Every page is marked `<!-- page N of M -->`.
3. Text that exists only inside images is OCR'd and appended on the same page,
   under a clearly marked OCR comment.
4. Foreground images are OCR'd first. If a page has little native text and the
   foreground result is thin, a full-page background image is also OCR'd.
5. Rendered image regions are cached by a SHA-256 of their pixels, so
   bit-identical regions are not OCR'd twice.

### PPTX

1. Pandoc converts each slide to GitHub-flavored Markdown; slide titles become
   level-2 headings.
2. Slides are delimited with `<!-- slide N of M -->`.
3. Images are replaced by OCR text with no minimum-length filter. When the
   PPTX stores a picture's position, its coordinates (`x`, `y`, `w`, `h` in
   EMU) are appended next to the OCR text.
4. Speaker notes are read from `notesSlide*.xml` and appended at the end of
   their slide under `### Speaker notes`.
5. PPTX comments are read from the slide relationships and appended at the end
   of their slide under `### Comments`, with author and date.

### OCR

OCR defaults to **Apple Live Text** through `ocrmac`, English (`en-US`)
preferred. Transparent images are flattened onto white first, because Live Text
returns nothing for RGBA images with an alpha background.

The optional **Tesseract** engine runs English-only OCR with four
page-segmentation modes:

| PSM | Assumption | Good for |
|---|---|---|
| 3 | automatic layout | normal pages and mixed layouts |
| 4 | single column | tables, receipts, row-wise data |
| 6 | single uniform block | cropped paragraphs and text blocks |
| 11 | sparse text | diagrams, labels, screenshots |

Each image is run through all four modes and ranked by:

```text
confidence × (words / max_words)
```

Coverage-adjusted confidence avoids preferring a short, easy read that missed
table rows. OCR is dropped only when an image yields fewer than 10 non-space
characters. Cache keys are exact SHA-256 hashes; there is no fuzzy reuse.

The app uses Apple Live Text.

### Parallelism

The CLI defaults to one worker process per CPU core; `--jobs N` changes it.
The GUI caps itself at four workers. PDF page rendering and OCR run inside the
worker processes, while the parent process only aggregates results and updates
the window.

### Design choices

- Recall comes before cleanliness: watermark text, short native-text fragments
  and imperfect OCR wording are kept. Beyond de-duplication against the native
  text, OCR is dropped only when an image yields fewer than 10 non-space
  characters.
- OCR text is additive; the native text layer always comes first.
- Page and slide markers are HTML comments, so they remain searchable without
  rendering.
- DOCX floating drawings need a separate figures section because Pandoc
  extracts them without emitting an image link.
- PDF foreground/background splitting prevents full-page template images from
  duplicating the native text layer.
- DOCX comments sit next to the passage they annotate so their context survives
  conversion; only unanchored comments fall back to an appendix.
- PPTX notes and comments stay with their slide.
- No image files are copied into the Markdown.
