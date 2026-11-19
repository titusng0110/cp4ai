# Document-to-Markdown Workflow

This directory contains a reproducible pipeline that converts every `.docx` and
`.pdf` under `src/` into AI-friendly Markdown under `md/`, without summarizing
or truncating the source. It is designed for another AI agent (or a human) to
pick up and run again.

## Quick start

```bash
cd ~/notes4ai

# 1. Install the Homebrew dependencies
brew bundle                 # Tesseract 5.5.4, libemf2svg, librsvg

# 2. Make sure the Tesseract language files are present
./tools/setup_tessdata.sh

# 3. Install the exact Python environment (Python 3.13)
uv sync

# 4. Convert everything
uv run python convert_to_md.py --force
```

Output:

```text
md/
├── README.md             # generated index of all documents
├── Notes/...
├── Reading/...
└── ...
```

Every Markdown file mirrors its source path and is self-contained: no image
files are copied into `md/`.

## Exact environment

Python: **3.13** (see `.python-version`)

Python packages (`pyproject.toml`, locked in `uv.lock`):

| Package | Version | Purpose |
|---|---|---|
| `pymupdf` | 1.28.2 | PDF page access, image-region rendering |
| `pymupdf4llm` | 0.3.4 | PDF text layer → Markdown, page chunks |
| `pypandoc-binary` | 1.17 | Bundled Pandoc 3.9 for DOCX → GFM |
| `opencv-python-headless` | 5.1.0.95 | Table-line removal before OCR |
| `numpy` | 2.5.5 | Array handling for OpenCV |
| `tabulate` | 0.10.0 | `pymupdf4llm` dependency |

System packages:

| Package | Version | Install |
|---|---|---|
| Tesseract OCR | 5.5.4 | `brew install tesseract` |
| libemf2svg | 1.8.1 | `brew install libemf2svg` (classic EMF → SVG) |
| librsvg | 2.63.4 | `brew install librsvg` (SVG → PNG) |
| Python 3.13 | 3.13.x | managed by `uv` |

Tesseract language data in `tools/tessdata/`:

- `eng.traineddata` — copied from the Homebrew Tesseract installation
- `chi_tra.traineddata` — Traditional Chinese, downloaded from
  [tessdata_fast](https://github.com/tesseract-ocr/tessdata_fast)
- `configs/tsv` — required because the script uses Tesseract's TSV confidence
  output when running with `--tessdata-dir`

`tools/setup_tessdata.sh` recreates all three. The files are small (~6 MB) and
are already present in this repository folder.

## What the converter does

### DOCX files

1. Runs Pandoc through `pypandoc` with:

   ```text
   --from=docx --to=gfm --wrap=none --markdown-headings=atx
   --track-changes=all --extract-media=media
   ```

   This preserves headings, lists, tables, footnotes, text boxes, and tracked
   changes (deletions appear as `<del>...</del>`).

2. OCRs every **raster** image extracted by Pandoc. Text is inserted at the
   image's position as a blockquote labelled `Image text (OCR)`. If Pandoc
   extracted a floating/anchored drawing but did not emit an image link (common
   in these notes), the image is OCR'd and put in a
   `## Figures from the original document (OCR text)` section at the end.

3. Appends DOCX comments verbatim in
   `## Appendix: Comments in the original DOCX`, with author, date, and the
   passage each comment was attached to. Pandoc drops comments, so this step is
   necessary to avoid losing exam hints.

4. Converts EMF/EMF+/SVG images to PNG and OCRs them:
   - **EMF+** files (the common case in these DOCX files) store a screenshot
     as a bitmap inside the EMF record. The script extracts the raw
     BGRA/BGR pixels directly, flattens transparency onto white, and OCRs the
     result. `libemf2svg` ignores EMF+ records, so this direct path is
     essential.
   - **Classic EMF** is converted with `emf2svg-conv` (libemf2svg) and then
     `rsvg-convert` (librsvg).
   - **SVG** is rasterised directly with `rsvg-convert`.
   - Only images that still fail are listed in
     `## Vector images (not OCR'd)`; the original DOCX remains the authority
     for those.

5. Image files are extracted into a temporary directory and deleted afterwards.
   Nothing in `md/` points at an image file.

### PDF files

1. `pymupdf4llm.to_markdown(page_chunks=True)` extracts the digital text layer
   page by page.
2. Every page is prefixed with `<!-- page N of M -->` so page references remain
   stable.
3. Embedded images are OCR'd:
   - **Foreground images** (screenshots, table fragments, diagrams) are OCR'd
     individually.
   - **Full-page background images** are skipped when the page already has a
     substantial text layer. They are used only when the native text layer is
     sparse, which catches scanned pages.
   - Adjacent image fragments are merged first, so a table split across several
     images is OCR'd once.
4. OCR text is appended after the native page text under
   `<!-- OCR text from image(s) on this page ... -->`. It may contain recognition
   errors; the original text layer is always kept above it.
5. The diagonal `pcll2026pass` watermark is removed when the text layer exposes
   it.

### OCR quality strategy

The script does not trust a single Tesseract mode:

- It runs Tesseract with `eng+chi_tra`.
- For each image it compares:
  - the **original image** with `--psm 3` (layout-aware), and
  - a **line-removed / watermark-suppressed** copy with `--psm 6` (table mode).
- It picks the result with the highest **Tesseract TSV confidence**, breaking
  ties by word count. This matters because preprocessing helps tables but
  destroys some screenshots.
- For DOCX figures it also tries `--psm 11` (sparse text), which reads labels
  scattered around boxes and arrows. Sparse mode is preferred when it is within
  five confidence points of the best result.

This is why `configs/tsv` must exist in `tools/tessdata/`.

## Commands and options

```bash
# Reconvert everything, overwriting existing Markdown
uv run python convert_to_md.py --force

# Convert only files whose path contains a string
uv run python convert_to_md.py --only "Lecture 4" --force
uv run python convert_to_md.py --only "Exam/" --force

# Skip OCR (fast, but loses text that exists only inside images)
uv run python convert_to_md.py --no-ocr --force

# Use different source/output directories
uv run python convert_to_md.py --src /path/to/src --out /path/to/md --force
```

The script is idempotent: without `--force` it skips Markdown files that
already exist. It continues after a failed file and prints a summary of
failures at the end.

## Rebuilding from a clean slate

```bash
# Remove generated output and the managed environment
rm -rf .venv md tmp __pycache__

# Reinstall exact packages
uv sync

# Reconvert
uv run python convert_to_md.py --force
```

## Verification checklist

```bash
# Every source has a Markdown counterpart
find src -type f \( -iname '*.docx' -o -iname '*.pdf' \) | wc -l
find md -name '*.md' ! -name 'README.md' | wc -l

# No image links or extracted assets leaked into the output
grep -R "!\[" md --include='*.md' || echo "no image links"
find md -type d -name '*.assets' -o -type f \( -iname '*.png' -o -iname '*.jpg' \)

# Spot-check any pages with dense tables or diagrams
#   (OCR text appears under the page's native text layer)
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `ERROR: tesseract is not installed` | `brew install tesseract` |
| `read_params_file: Can't open tsv` | `./tools/setup_tessdata.sh` (copies `configs/tsv`) |
| OCR output is gibberish on a screenshot | The confidence selector usually picks the original-image pass; check the source PDF page and, if needed, add a targeted `--psm` preference in `ocr_image`. |
| A PDF page has no OCR text | It may genuinely be blank, or its image is below the 0.8% area threshold. Check `<!-- page N -->` and the source. |
| EMF image content is missing | Check `## Vector images (not OCR'd)`. EMF+ should work via direct bitmap extraction; classic EMF needs `libemf2svg` + `librsvg`. |
| `emf2svg-conv` outputs a 245-byte empty SVG | The file is EMF+, not classic EMF. The direct EMF+ bitmap extractor should handle it; no action needed. |
| `pymupdf4llm` prints “Consider using the pymupdf_layout package” | Harmless stderr advice; the pinned 0.3.4 API is intentional. |

## Design notes / gotchas

- `pymupdf4llm` 0.3.4 is pinned. Newer 2.x versions depend on PyMuPDF 2.x and
  ONNX Runtime, which currently lack Python 3.15 wheels and change output
  formatting. 0.3.4 is stable on Python 3.13 and preserves the native PDF text
  layer cleanly.
- `pypandoc-binary` bundles Pandoc, so no separate Pandoc install is needed.
- Some DOCX files store images as floating drawings. Pandoc extracts the image
  files but emits no `![](...)` link. The `figures_section()` fallback exists
  specifically for that case; do not remove it.
- The PDF exam templates contain a full-page background image on every page.
  Without the foreground/background split, OCR would run on all 68 pages and
  duplicate the entire document. The split is intentional.
- Page markers are HTML comments so they do not render as visible headings but
  remain searchable and machine-readable.
- No text is summarized. OCR text is additive; the native text layer always
  comes first.
