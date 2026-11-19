# notes4ai

Turn a folder of `.docx` and `.pdf` notes into AI-friendly Markdown.

The converter preserves the full source text: DOCX headings, lists, tables,
footnotes, text boxes and tracked changes survive, and text that exists only
inside images is extracted with OCR. Nothing is summarized or truncated.

## First-time setup

Requires macOS with [Homebrew](https://brew.sh) and [uv](https://docs.astral.sh/uv/).

```bash
git clone <your-remote-url> notes4ai
cd notes4ai

brew bundle                 # Tesseract, libemf2svg, librsvg
./tools/setup_tessdata.sh   # verify Tesseract language data
uv sync                     # Python 3.13 environment
```

The Tesseract language files (`eng`, `chi_tra`) are committed under
`tools/tessdata/`, so the setup script normally has nothing to download.

## Convert a new folder of notes

1. Drop the files into `src/`, keeping any subfolders you want mirrored:

   ```bash
   cp -R ~/Downloads/my-notes/. src/
   ```

2. Run the converter:

   ```bash
   uv run python convert_to_md.py
   ```

3. Read the result in `md/`. Start with `md/README.md`, which indexes every
   converted document.

Existing output is skipped by default. Useful options:

```bash
uv run python convert_to_md.py --force          # reconvert everything
uv run python convert_to_md.py --only "Lecture 4"  # only matching paths
uv run python convert_to_md.py --no-ocr         # faster, skips image text
```

## What is committed

- `src/` is **gitignored** (except `.gitkeep`), so your notes are never
  committed by accident.
- `md/` is **gitignored** too; it is generated output.
- Only the pipeline, its locked dependencies and the Tesseract data are
  versioned.

See [`WORKFLOW.md`](WORKFLOW.md) for the exact environment, design decisions
and troubleshooting.
