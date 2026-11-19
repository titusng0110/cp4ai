#!/usr/bin/env bash
# Populate tools/tessdata with the language data and TSV config used by
# convert_to_md.py. Safe to re-run.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
DEST="$HERE/tessdata"
mkdir -p "$DEST/configs"

if ! command -v tesseract >/dev/null 2>&1; then
    echo "ERROR: tesseract is not installed. Run: brew install tesseract" >&2
    exit 1
fi

# Locate the Homebrew Tesseract data directory.
BREW_TESSDATA="$(brew --prefix tesseract 2>/dev/null || true)/share/tessdata"
if [ ! -f "$BREW_TESSDATA/eng.traineddata" ]; then
    BREW_TESSDATA="/opt/homebrew/share/tessdata"
fi

if [ ! -f "$DEST/eng.traineddata" ]; then
    cp "$BREW_TESSDATA/eng.traineddata" "$DEST/eng.traineddata"
    echo "copied eng.traineddata"
fi

if [ ! -f "$DEST/configs/tsv" ]; then
    cp "$BREW_TESSDATA/configs/tsv" "$DEST/configs/tsv"
    echo "copied configs/tsv"
fi

echo "Tesseract data ready in $DEST"
