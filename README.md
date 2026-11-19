# Copy 4 AI (cp4ai)

Copy 4 AI (package `cp4ai`) copies text from lecture notes into Markdown for
downstream LLM ingestion. It accepts `.docx`, `.pdf` and `.pptx` files. The
`md4ai` command writes files; `cp4ai` copies the converted chain to the
clipboard.

The pipeline is **recall-first**: every source word matters. OCR errors,
duplicate text and imperfect formatting are acceptable because the downstream
LLM can interpret them; silently dropping a point is not recoverable.

- DOCX headings, lists, tables, footnotes, text boxes and tracked changes are
  preserved.
- DOCX comments are inserted next to the passage they annotate, with author
  and date; unanchored comments go into an appendix.
- PDF page order and page boundaries are preserved.
- PPTX slides are delimited with `<!-- slide N of M -->`; speaker notes and
  comments are appended at the end of each slide.
- PDF, DOCX and PPTX images are OCR'd; image files are not copied into the
  output. PPTX images also get their shape coordinates.
- OCR defaults to Apple's Live Text via `ocrmac`; `--tesseract` switches to
  Tesseract. Transparent images are flattened onto white before OCR.
- Output is `<source>.pdf.md`, `<source>.docx.md` or `<source>.pptx.md`, so it
  never collides with the input file.

Released under the MIT License.

## Install

Requirements: **macOS**, [Homebrew](https://brew.sh) and
[uv](https://docs.astral.sh/uv/). Python itself is installed by `uv`.

```bash
git clone https://github.com/titusng0110/cp4ai.git
cd cp4ai
uv tool install .
```

This installs the `md4ai` and `cp4ai` commands. If a command is not found,
run `uv tool update-shell` and restart the terminal (or add `~/.local/bin` to
`PATH`).

On first use the tools install `libemf2svg` and `librsvg` with Homebrew if they
are missing. Tesseract is installed only when you use `--tesseract`.
Homebrew installs into a user-writable prefix on Apple Silicon, so no `sudo`
is normally needed.

To skip that automatic check:

```bash
CP4AI_SKIP_SETUP=1 md4ai ...
```

For development, `uv sync` installs the package in editable mode and
`uv run md4ai` runs it without installing globally.

### Updating and uninstalling

Because the tool is installed from a local clone, reinstall it after pulling
changes:

```bash
cd cp4ai
git pull
uv tool install --force .
```

If you changed the code locally without committing, the same command rebuilds
from your working tree. Check the installed version with:

```bash
md4ai --version
uv tool list
```

Uninstall with:

```bash
uv tool uninstall cp4ai
```

This removes the `md4ai` and `cp4ai` commands and their isolated environment.
Your Markdown files and the Homebrew packages remain installed.

### Installed packages

- Python 3.13
- Python packages: `numpy 2.5.5`, `pymupdf 1.28.2`, `pymupdf4llm 0.3.4`,
  `pypandoc-binary 1.17`, `tabulate 0.10.0`, `ocrmac 1.0.1`, `pillow 13.0.0`,
  `tiktoken 0.14.0`
- Homebrew packages: `libemf2svg`, `librsvg`; optional `tesseract` for
  `--tesseract`

## Usage

```bash
md4ai a.pdf                  # writes a.pdf.md next to a.pdf
md4ai a.docx                 # writes a.docx.md next to a.docx
md4ai a.pptx                 # writes a.pptx.md next to a.pptx

md4ai -r notes/              # every .pdf/.docx/.pptx under notes/, in place
md4ai -rf notes/             # same, overwriting existing .md files
md4ai -r -f notes/           # equivalent long form

md4ai -o b.md a.pdf          # write exactly b.md
md4ai -o out/ a.pdf          # write out/a.pdf.md (creates out/)
md4ai -o out/ -r notes/      # preserve notes/'s structure under out/
```

If an output file already exists, the command **refuses to run** unless
`-f/--force` is given. For a recursive run it checks all destinations first,
so it will not partially convert a directory and then stop.

`--out` is treated as a file when it ends in `.md`; otherwise it is treated as
a directory. A directory is created if needed.

### Options

| Option | Meaning |
|---|---|
| `-r`, `--recursive` | Convert every `.docx`/`.pdf`/`.pptx` under a directory |
| `-f`, `--force` | Overwrite existing output |
| `-o`, `--out` | Output file, or output directory preserving structure |
| `--jobs N` | Parallel worker processes (default: CPU cores) |
| `--livetext` | Apple Live Text via `ocrmac` (default) |
| `--tesseract` | Use Tesseract instead of Live Text (installs it if missing) |
| `--no-ocr` | Do not OCR images |
| `--version` | Show version |

`-rf` and `-r -f` are equivalent. Directory inputs require `-r`.

### Clipboard mode

The `cp4ai` clipboard command uses the same conversion pipeline but writes the
result to the macOS clipboard instead of files. It accepts one or more files
and does not support directories:

```bash
cp4ai a.pdf b.docx c.pptx
```

Each document is wrapped with its filename (without directories):

```text
[a.pdf BEGIN]
...
[a.pdf END]

[b.docx BEGIN]
...
[b.docx END]

[c.pptx BEGIN]
...
[c.pptx END]
```

`cp4ai` accepts only `--tesseract`, `--no-ocr` and `--jobs N`. If any file
fails, the clipboard is left unchanged. On success it reports the clipboard
size and the GPT-4 token count:

```text
=========================
Copied to clipboard! (12345 characters / 3000 tokens)
```

## Design / Algorithm

### Pipeline

```text
a.pdf  -> a.pdf.md
notes/ -> notes/**/*.pdf.md, notes/**/*.docx.md
```

Documents are independent. Each file is converted in its own temporary
directory, and `--jobs` controls how many run in parallel.

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

### PPTX

1. Pandoc converts each slide to GitHub-flavored Markdown; slide titles become
   level-2 headings.
2. Slides are delimited with `<!-- slide N of M -->`, matching the PDF page
   marker style.
3. Images are replaced by OCR text with no minimum-length filter. When the
   PPTX stores a picture's position, its coordinates (`x`, `y`, `w`, `h` in
   EMU) are appended next to the OCR text.
4. Speaker notes are read from `notesSlide*.xml` and appended at the end of
   their slide under `### Speaker notes`.
5. PPTX comments are read from the slide relationships and appended at the end
   of their slide under `### Comments`, with author and date.

### PDF

1. `pymupdf4llm` extracts the native text layer page by page.
2. Every page is marked with `<!-- page N of M -->`.
3. Image regions are classified:
   - foreground images (screenshots, table fragments, diagrams) are OCR'd
     individually;
   - full-page background images are used only when the native text layer is
     sparse, which catches scanned pages.
4. Adjacent image fragments are merged, so a table split across several images
   is OCR'd once.
5. OCR text is appended after the native text under a marked OCR comment. OCR
   is discarded only when it adds no new words beyond the native text.
6. OCR results are cached by a SHA-256 hash of the rendered pixels, so text is
   reused only when the image region is bit-identical. Image xrefs and box size
   are not sufficient: the rendered clip can differ when vector text overlays
   an image or when a shared background appears on several pages.

### OCR

DOCX images and PDF image regions share `ocr_image()`, which selects the
configured engine.

**Apple Live Text (default).** Uses Apple's Live Text framework through
`ocrmac`, with English (`en-US`) preferred. It is usually more accurate than
Tesseract on printed English and keeps clause numbers with their text, but
column order in forms and tables can be less faithful. It performs one
recognition pass per image rather than four Tesseract passes. Transparent
images are flattened onto white first, because Live Text otherwise returns
nothing for RGBA images with an alpha background.

**Tesseract (`--tesseract`).** English-only Tesseract (`eng`) with no image
preprocessing, once for each of four page-segmentation modes:

| PSM | Assumption | Good for |
|---|---|---|
| 3 | automatic layout | normal pages and mixed layouts |
| 4 | single column | tables, receipts, row-wise data |
| 6 | single uniform block | cropped paragraphs and text blocks |
| 11 | sparse text | diagrams, labels, screenshots |

Each OCR'd image region is run through all four modes; results are ranked by
coverage-adjusted confidence:

```text
confidence × (words / max_words)
```

Raw confidence alone favours short, easy reads and can drop table rows. The
coverage factor penalises a result that missed much of the text, without
rewarding noisy output that simply produced more words.

Both engines discard OCR from images with fewer than 10 non-space characters
*after* OCR. OCR is skipped only when bit-identical input has already been
processed in the same document: DOCX images are keyed by a SHA-256 of the image
bytes (or the rasterised PNG for EMF/WMF/SVG), while PDF regions are keyed by a
SHA-256 of the rendered pixels.

### Parallelism

The default worker count is the number of CPU cores; use `--jobs N` to change
it. Tesseract is limited to one thread per worker.

### Design choices

- Recall comes before cleanliness: watermark text, short native-text fragments
  and imperfect OCR wording are kept. Beyond de-duplication against the native
  text, OCR is dropped only when an image yields fewer than 10 non-space
  characters.
- OCR text is additive; the native text layer always comes first.
- Page markers are HTML comments, so they remain searchable without rendering.
- DOCX floating drawings need a separate figures section because Pandoc
  extracts them without emitting an image link.
- PDF foreground/background splitting prevents full-page template images from
  duplicating the native text layer; content-hash OCR caching reuses text only
  for bit-identical rendered regions.
- DOCX comments sit next to the passage they annotate so their context survives
  conversion; only unanchored comments fall back to an appendix.
- No image files are copied into the Markdown.
