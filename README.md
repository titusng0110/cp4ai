# notes4ai

## Intro

`notes4ai` converts a folder of `.docx` and `.pdf` notes into AI-friendly
Markdown. It is built for study notes, lecture outlines, problem sets and exam
frameworks: documents that mix prose, tables, screenshots, diagrams and
comments.

The guiding rule is **no lossy rewriting**. The converter never summarizes,
shortens or paraphrases. It preserves the source text layer and adds OCR text
for content that exists only inside images.

### What it does

```text
src/ (.docx, .pdf)  ->  convert_to_md.py  ->  md/ (mirrored paths + index)
```

- DOCX files go through Pandoc to GitHub-flavored Markdown.
- PDF files keep their digital text layer, page order and page boundaries.
- Images are OCR'd with Tesseract; image files are not copied into `md/`.
- DOCX comments are reproduced verbatim in an appendix.
- Every generated document is self-contained Markdown.

### What it preserves

- DOCX headings, lists, tables, footnotes, text boxes and tracked changes.
- DOCX comments, including author, date and the attached passage.
- PDF page boundaries, as `<!-- page N of M -->` comments.
- Native PDF text before any OCR text on the same page.
- Tables and diagrams as OCR text when they exist only as pictures.
- The original filenames and folder structure under `md/`.

### What it does not do

- It does not summarize, translate or rewrite.
- It does not reconstruct pixel-perfect table layouts.
- It does not guarantee perfect OCR; screenshots and handwriting can contain
  recognition errors.
- It does not copy images into the output.

## Setup

### Requirements

- macOS with [Homebrew](https://brew.sh)
- [uv](https://docs.astral.sh/uv/)
- Python 3.13 (managed by `uv`)
- Tesseract 5.5.4, libemf2svg and librsvg (installed by `brew bundle`)

### Install

```bash
git clone <your-remote-url> notes4ai
cd notes4ai

brew bundle                 # Tesseract, libemf2svg, librsvg
./tools/setup_tessdata.sh   # verify the committed language data
uv sync                     # Python 3.13 environment
```

### Tesseract language data

The English language file is committed under `tools/tessdata/`, so a fresh
clone normally needs no downloads:

| File | Purpose |
|---|---|
| `eng.traineddata` | English text |
| `configs/tsv` | required for TSV confidence output with `--tessdata-dir` |

`tools/setup_tessdata.sh` recreates both from the Homebrew installation if they
are missing.

### Python and system dependencies

Python packages (`pyproject.toml`, locked in `uv.lock`):

| Package | Version | Purpose |
|---|---|---|
| `pymupdf` | 1.28.2 | PDF page access, image rendering, PNG writing |
| `pymupdf4llm` | 0.3.4 | PDF text layer → Markdown, page chunks |
| `pypandoc-binary` | 1.17 | Bundled Pandoc 3.9 for DOCX → GFM |
| `numpy` | 2.5.5 | Pixel arrays for EMF+ bitmap extraction |
| `tabulate` | 0.10.0 | `pymupdf4llm` dependency |

System packages:

| Package | Version | Install |
|---|---|---|
| Tesseract OCR | 5.5.4 | `brew install tesseract` |
| libemf2svg | 1.8.1 | `brew install libemf2svg` (classic EMF → SVG) |
| librsvg | 2.63.4 | `brew install librsvg` (SVG → PNG) |

### Repository layout

```text
convert_to_md.py     converter
pyproject.toml       Python dependencies
uv.lock              locked dependency versions
Brewfile             Homebrew dependencies
tools/
  setup_tessdata.sh
  tessdata/          eng, configs/tsv
src/                 input notes (gitignored)
md/                  generated Markdown (gitignored)
```

### What git tracks

- `src/` is gitignored except `.gitkeep`, so private notes are never committed.
- `md/` and `convert.log` are generated and gitignored.
- The converter, locked dependencies and Tesseract data are versioned.

### Clean rebuild

```bash
rm -rf .venv md tmp __pycache__
uv sync
uv run python convert_to_md.py --force
```

## Usage

### Convert a folder of notes

1. Copy the files into `src/`, keeping any subfolders you want mirrored:

   ```bash
   cp -R ~/Downloads/my-notes/. src/
   ```

2. Run the converter:

   ```bash
   uv run python convert_to_md.py
   ```

3. Read the result in `md/`. Start with `md/README.md`, which indexes every
   document.

```text
md/
├── README.md             # generated index
├── Notes/...
├── Exam/...
└── ...
```

### Commands and options

```bash
# Convert new files only (existing Markdown is skipped)
uv run python convert_to_md.py

# Reconvert everything, overwriting existing Markdown
uv run python convert_to_md.py --force

# Convert only paths containing a string
uv run python convert_to_md.py --only "Lecture 4" --force

# Skip OCR (fast, but loses text that exists only inside images)
uv run python convert_to_md.py --no-ocr --force

# Choose the number of parallel workers (default: CPU cores)
uv run python convert_to_md.py --jobs 4 --force

# Use different source/output directories
uv run python convert_to_md.py --src /path/to/src --out /path/to/md --force
```

### Parallelism

Documents are independent, so the converter processes one **document per
worker** using a process pool:

- Default worker count is `os.cpu_count()`; use `--jobs N` to override.
- Each worker writes only its own Markdown file, and every DOCX/PDF conversion
  gets a unique temporary directory. There is no shared mutable output state.
- The library index (`md/README.md`) is built in the parent process after all
  workers finish, so it is never written concurrently.
- Tesseract calls set `OMP_THREAD_LIMIT=1`, so each worker runs one
  single-threaded OCR process at a time instead of oversubscribing the CPU.

### Output format

Each Markdown file starts with YAML front matter:

```yaml
source: src/Notes/Lecture 4.docx
format: docx
converted: 2026-11-20
converter: pandoc 3.9 (pypandoc 1.17)
```

The body then contains:

- a top-level heading derived from the filename;
- the converted native text;
- OCR text inserted at image positions, or in a figures section for floating
  DOCX drawings;
- DOCX comments in an appendix;
- PDF page markers such as `<!-- page 12 of 68 -->`;
- PDF OCR blocks marked with `<!-- OCR text from image(s) on this page ... -->`.

### Idempotency and partial runs

- Without `--force`, existing Markdown files are skipped.
- A failed document does not stop the batch; failures are listed at the end.
- A partial `--only` run does not rebuild `md/README.md`, so the library-wide
  index is not replaced with a single row.
- Temporary files are deleted after each document.

### Verification

```bash
# Every source has a Markdown counterpart
find src -type f \( -iname '*.docx' -o -iname '*.pdf' \) | wc -l
find md -name '*.md' ! -name 'README.md' | wc -l

# No image links or extracted assets leaked into the output
grep -R "!\[" md --include='*.md' || echo "no image links"
find md -type d -name '*.assets' -o -type f \( -iname '*.png' -o -iname '*.jpg' \)

# Spot-check pages with dense tables or diagrams
# (OCR text appears below the page's native text layer)
```

### Troubleshooting

| Symptom | Fix |
|---|---|
| `ERROR: tesseract is not installed` | `brew install tesseract` |
| `read_params_file: Can't open tsv` | `./tools/setup_tessdata.sh` (copies `configs/tsv`) |
| OCR output is weak on a screenshot | Check the source image. The four modes and coverage score are fixed in `OCR_PSMS` and `ocr_image()`; tune there only with a measured reason. |
| A PDF page has no OCR text | It may genuinely be blank, or its image is below the 0.8% area threshold. Check `<!-- page N -->` and the source. |
| EMF image content is missing | Check `## Vector images (not OCR'd)`. EMF+ works via direct bitmap extraction; classic EMF needs `libemf2svg` + `librsvg`. |
| `emf2svg-conv` outputs a 245-byte empty SVG | The file is EMF+, not classic EMF. The direct EMF+ bitmap extractor should handle it; no action needed. |
| `pymupdf4llm` prints “Consider using the pymupdf_layout package” | Harmless stderr advice; the pinned 0.3.4 API is intentional. |

## Design / Algorithm

### Pipeline overview

```text
for each source document (in parallel):
    DOCX -> Pandoc -> Markdown + extracted media -> OCR images -> comments
    PDF  -> PyMuPDF4LLM -> native pages -> OCR foreground images -> merge
after all workers:
    write md/README.md index
```

Each document is a self-contained job. The only cross-document work is the
final index build, which happens in the parent process.

### DOCX conversion

1. Pandoc runs with:

   ```text
   --from=docx --to=gfm --wrap=none --markdown-headings=atx
   --track-changes=all --extract-media=media
   ```

   This preserves headings, lists, tables, footnotes, text boxes and tracked
   changes. Deletions appear as `<del>...</del>`.

2. Every image link is replaced by its OCR text:
   - ordinary images become a blockquote labelled `Image text (OCR)`;
   - images inside a Markdown table become an inline `<br>**Image text...**`
     block so the table is not broken.

3. Images that Pandoc extracted but could not place in the body (floating or
   anchored drawings) are OCR'd and appended in
   `## Figures from the original document (OCR text)`.

4. DOCX comments are extracted from `word/comments.xml`, paired with their
   anchored passage, and appended in `## Appendix: Comments in the original DOCX`.
   Pandoc drops comments, so this step is necessary to keep review notes.

5. EMF/EMF+/SVG images are rasterised before OCR:
   - **EMF+** stores a bitmap inside the EMF record. The raw BGRA/BGR pixels are
     extracted, transparency is flattened onto white, and the image is written
     with PyMuPDF.
   - **Classic EMF** goes through `emf2svg-conv`, then `rsvg-convert`.
   - **SVG** goes directly through `rsvg-convert`.
   - Files that cannot be rendered are listed in
     `## Vector images (not OCR'd)`.

6. Images are extracted into a per-document temporary directory and deleted
   afterwards.

### PDF conversion

1. `pymupdf4llm.to_markdown(page_chunks=True)` extracts the native text layer
   page by page.
2. Every page gets a `<!-- page N of M -->` marker so references stay stable.
3. Image regions are classified:
   - **Foreground images** (screenshots, table fragments, diagrams) are OCR'd
     individually.
   - **Background images** covering at least 85% of the page are skipped when
     the native text layer is substantial. They are used only when the page
     looks scanned (fewer than 40 native tokens).
   - Regions smaller than 0.8% of the page, or with an extreme aspect ratio
     (over 20:1), are ignored as rules or decoration.
4. Adjacent image fragments are merged first, so a table split into several
   pictures is OCR'd once. A per-document cache avoids re-OCRing identical
   regions.
5. OCR text is appended after the native page text under the marked OCR
   comment. If the OCR output overlaps the native text by 90% or more, it is
   discarded as duplicate.
6. The diagonal `pcll2026pass` watermark is removed when the native text layer
   exposes it.

### Shared OCR algorithm

DOCX images and PDF page images call the same `ocr_image()` function. Tesseract
runs with `eng` and no image preprocessing, once for each of four
page-segmentation modes:

| PSM | Assumption | Good for |
|---|---|---|
| 3 | fully automatic layout | normal pages and mixed layouts |
| 4 | single column of variable-size text | tables, receipts, row-wise data |
| 6 | single uniform block | cropped paragraphs and text blocks |
| 11 | sparse text, no reading order | diagrams, labels, screenshots |

Each image therefore costs exactly **four Tesseract runs**. The modes are
deliberately fixed so DOCX and PDF cannot drift into different OCR behaviour.

### OCR scoring

The four results are ranked by **coverage-adjusted confidence**:

```text
confidence × (words / max_words)
```

This is not raw confidence. Measured on the source notes, raw confidence
correlates negatively with coverage within an image (−0.41): sparse mode often
scores high by reading a few easy words while dropping table rows. The coverage
factor discounts a result that missed much of the text without rewarding a mode
merely for producing more, possibly noisy, words.

### Noise and duplicate filtering

- `useful_ocr()` rejects text from logos, photos and decoration: fewer than 8
  alphanumeric characters, fewer than 2 words, or a printable-character ratio
  below 55%.
- PDF OCR that is 90% or more overlapping with the native text layer is dropped.
- Lines that are only the course watermark are removed.
- Empty pages remain as page markers so page numbers stay accurate.

### Important design decisions

- `pymupdf4llm` 0.3.4 is pinned. Newer 2.x versions depend on PyMuPDF 2.x and
  ONNX Runtime and change output formatting.
- `pypandoc-binary` bundles Pandoc, so no separate Pandoc install is needed.
- Floating DOCX drawings need the `figures_section()` fallback because Pandoc
  extracts the image files but emits no link for them.
- The PDF foreground/background split prevents full-page template images from
  duplicating the entire native text layer.
- No OpenCV dependency: EMF+ pixels are handled with NumPy and written with
  PyMuPDF.
- Page markers are HTML comments so they stay searchable without appearing as
  visible headings.
- OCR text is additive; the native text layer always comes first.

### Known limitations

- OCR can misread small text, screenshots, handwriting and low-contrast tables.
- Vector formats without a working renderer (notably WMF) are listed but not
  OCR'd.
- DOCX table layout is preserved by Pandoc, but OCR text inside a table is
  flattened to an inline block.
- PDF tables are reproduced as text, not reconstructed as Markdown grid tables.
