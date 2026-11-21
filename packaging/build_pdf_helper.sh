#!/bin/bash
# Build the PyInstaller PDF helper and copy it into build/pdf-helper.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/helper"

uv sync --group build
uv run pyinstaller --noconfirm --clean pdf_helper.spec

DEST="$ROOT/build/pdf-helper"
rm -rf "$DEST"
mkdir -p "$ROOT/build"
cp -R "$ROOT/helper/dist/cp4ai-pdf" "$DEST"

echo "==> Smoke test"
"$DEST/cp4ai-pdf" --version
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
cat > "$TMP/probe.pdf" <<'EOF'
EOF
uv run python - "$TMP" <<'PY'
import sys, pymupdf, pathlib
out = pathlib.Path(sys.argv[1]) / "probe.pdf"
doc = pymupdf.open()
page = doc.new_page()
page.insert_text((72, 100), "Copy 4 AI helper smoke test", fontsize=16)
doc.save(out)
PY
"$DEST/cp4ai-pdf" probe --input "$TMP/probe.pdf"

echo "==> Wrote $DEST"
du -sh "$DEST"
