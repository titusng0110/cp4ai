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
- DOCX comments are reproduced verbatim in an appendix.
- PDF page order and page boundaries are preserved.
- PDF and DOCX images are OCR'd; image files are not copied into the output.
- `md/` mirrors `src/` and includes a generated index.
- Watermarks and short OCR fragments are kept rather than filtered out.

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
  `pypandoc-binary 1.17`, `tabulate 0.10.0`
- Homebrew packages: `libemf2svg 1.8.1`, `librsvg 2.63.4`, `tesseract 5.5.4`
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
uv run python convert_to_md.py --no-ocr         # skip image text
uv run python convert_to_md.py --jobs 4         # worker processes
uv run python convert_to_md.py --src path/to/src --out path/to/md
```

Without `--force`, existing Markdown is skipped. Failed documents do not stop
the batch; failures are summarised at the end. A partial `--only` run does not
rebuild the library index.

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
2. Each image link is replaced by its OCR text. Images inside tables become
   inline text so the table stays intact; other images become blockquotes.
3. Floating drawings that Pandoc extracts but cannot place in the body are
   OCR'd in a figures section at the end.
4. DOCX comments are read from `word/comments.xml` and appended with author,
   date and the attached passage.
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

### OCR

DOCX images and PDF image regions use the same `ocr_image()` function. It runs
English-only Tesseract (`eng`) with no image preprocessing, once for each of
four page-segmentation modes:

| PSM | Assumption | Good for |
|---|---|---|
| 3 | automatic layout | normal pages and mixed layouts |
| 4 | single column | tables, receipts, row-wise data |
| 6 | single uniform block | cropped paragraphs and text blocks |
| 11 | sparse text | diagrams, labels, screenshots |

Each image costs exactly four Tesseract runs. Results are ranked by
coverage-adjusted confidence:

```text
confidence × (words / max_words)
```

Raw confidence alone favours short, easy reads and can drop table rows. The
coverage factor penalises a result that missed much of the text, without
rewarding noisy output that simply produced more words.

### Parallelism

The default worker count is the number of CPU cores; use `--jobs N` to change
it. Tesseract is limited to one thread per worker, so the workload stays within
the requested process count.

### Design choices

- Recall comes before cleanliness: watermark text, short OCR fragments and
  imperfect wording are kept.
- OCR text is additive; the native text layer always comes first.
- Page markers are HTML comments, so they remain searchable without rendering.
- DOCX floating drawings need a separate figures section because Pandoc
  extracts them without emitting an image link.
- PDF foreground/background splitting prevents full-page template images from
  duplicating the native text layer.
- No image files are copied into `md/`.
