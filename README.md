# notes4ai

## Intro

`notes4ai` converts law notes — cases, statutes, lecture outlines, problem sets
and exam frameworks — from `.docx` and `.pdf` into Markdown for downstream LLM
ingestion.

The pipeline is **recall-first**: every source word matters. OCR errors,
duplicate text and imperfect formatting are acceptable because the downstream
LLM can interpret them; silently dropping a point is not recoverable.

- DOCX headings, lists, tables, footnotes, text boxes and tracked changes are
  preserved.
- DOCX comments are inserted next to the passage they annotate, with author
  and date; unanchored comments go into an appendix.
- PDF page order and page boundaries are preserved.
- PDF and DOCX images are OCR'd; image files are not copied into the output.
- OCR uses Tesseract by default; `--livetext` uses Apple's Live Text via
  `ocrmac` for printed English text.
- `md/` mirrors `src/` and includes a generated index.
- Watermark text and short fragments from the native text layer are kept; OCR
  from images that yields fewer than 10 non-space characters is dropped as
  decorative.

Released under the MIT License.

## Setup

Requires macOS, [Homebrew](https://brew.sh) and
[uv](https://docs.astral.sh/uv/).

```bash
git clone <your-remote-url> notes4ai
cd notes4ai

brew bundle
./tools/setup_tessdata.sh
uv sync
```

`tools/tessdata/` already contains `eng.traineddata` and the TSV config, so
setup normally needs no downloads.

### Installed packages

- Python 3.13
- Python packages: `numpy 2.5.5`, `pymupdf 1.28.2`, `pymupdf4llm 0.3.4`,
  `pypandoc-binary 1.17`, `tabulate 0.10.0`, `ocrmac 1.0.1`
- Homebrew packages: `libemf2svg 1.8.1`, `librsvg 2.63.4_1`, `tesseract 5.5.4`
- Tesseract data: `eng.traineddata`, `configs/tsv`

## Usage

```bash
# Put notes in src/, then convert them
cp -R ~/Downloads/my-notes/. src/
uv run python convert_to_md.py
```

Output:

```text
md/
├── README.md             # generated index
├── Notes/...
├── Exam/...
└── ...
```

Common options:

```bash
uv run python convert_to_md.py --force          # reconvert everything
uv run python convert_to_md.py --only "Lecture 4"
uv run python convert_to_md.py --tesseract      # default OCR engine
uv run python convert_to_md.py --livetext       # Apple Live Text (macOS Sonoma+)
uv run python convert_to_md.py --no-ocr         # skip image text
uv run python convert_to_md.py --jobs 4         # worker processes
uv run python convert_to_md.py --src path/to/src --out path/to/md
```

Without `--force`, existing Markdown is skipped. Failed documents do not stop
the batch; failures are summarised at the end. A partial `--only` run does not
rebuild the library index.

Tesseract is the default and requires the Homebrew binary. `--livetext` uses
Apple's Live Text through `ocrmac`; it requires macOS Sonoma or later and is
usually more accurate on printed English, but its line ordering can be less
faithful in multi-column forms. If Live Text returns no usable text for an
image, the converter falls back to Tesseract for that image so content is not
dropped.

## Design / Algorithm

### Pipeline

```text
src/ (.docx/.pdf)
  -> one worker per document
  -> md/ (mirrored paths + index)
```

Documents are independent. Each worker writes only its own Markdown file and
uses its own temporary directory. The index is written once by the parent
process after all workers finish.

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

**Tesseract (default).** English-only Tesseract (`eng`) with no image
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

**Apple Live Text (`--livetext`).** Uses Apple's Live Text framework through
`ocrmac`, with English (`en-US`) preferred. It is usually more accurate than
Tesseract on printed English and keeps clause numbers with their text, but
column order in forms and tables can be less faithful. It performs one
recognition pass per image rather than the four Tesseract passes. If Live Text
returns no usable text, the image is retried with Tesseract.

Both engines discard OCR from images with fewer than 10 non-space characters
*after* OCR. OCR is skipped only when bit-identical input has already been
processed in the same document: DOCX images are keyed by a SHA-256 of the image
bytes (or the rasterised PNG for EMF/WMF/SVG), while PDF regions are keyed by a
SHA-256 of the rendered pixels.

### Parallelism

The default worker count is the number of CPU cores; use `--jobs N` to change
it. Tesseract is limited to one thread per worker, so the workload stays within
the requested process count.

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
- No image files are copied into `md/`.
