#!/bin/bash
# Build the Copy 4 AI .app and DMG.  Run from the repository root.
# Native tools are fetched here, at build time, and bundled in the DMG.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

VERSION="$(python3 - <<'PY'
import re, pathlib
text = pathlib.Path("src/cp4ai/__init__.py").read_text()
print(re.search(r'__version__ = "([^"]+)"', text).group(1))
PY
)"

export CP4AI_VERSION="$VERSION"

echo "==> Syncing Python environment"
uv sync --frozen

echo "==> Fetching native tools (Pandoc, librsvg, libemf2svg, tiktoken cache)"
uv run python packaging/fetch_native.py

echo "==> Building app with PyInstaller"
uv run --with 'pyinstaller==6.22.3' \
    pyinstaller --noconfirm --clean packaging/cp4ai.spec

APP="$ROOT/dist/Copy 4 AI.app"
if [[ ! -d "$APP" ]]; then
    echo "missing app bundle: $APP" >&2
    exit 1
fi

PANDOC="$(find "$APP/Contents" -type f -name pandoc | head -1)"
if [[ -z "$PANDOC" ]]; then
    echo "pandoc was not bundled" >&2
    exit 1
fi
BIN_DIR="$(dirname "$PANDOC")"

chmod +x "$BIN_DIR/pandoc" "$BIN_DIR/rsvg-convert" "$BIN_DIR/emf2svg-conv"

echo "==> Auditing bundled binaries"
for binary in "$BIN_DIR"/*; do
    if otool -L "$binary" 2>/dev/null | grep -Eq '@@HOMEBREW_PREFIX@@|/opt/homebrew'; then
        echo "Homebrew reference remains in $binary" >&2
        otool -L "$binary" | grep -E '@@HOMEBREW_PREFIX@@|/opt/homebrew' >&2
        exit 1
    fi
done

echo "==> Ad-hoc signing"
for binary in "$BIN_DIR"/*; do
    if [[ -L "$binary" ]]; then
        continue
    fi
    if file "$binary" | grep -q 'Mach-O'; then
        codesign --force --sign - "$binary"
    fi
done
codesign --force --deep --sign - "$APP"
codesign --verify --deep --strict --verbose=2 "$APP"

echo "==> Building DMG"
if ! command -v create-dmg >/dev/null 2>&1; then
    echo "create-dmg is required for the installer window: brew install create-dmg" >&2
    exit 1
fi
DMG="$ROOT/dist/Copy4AI-${VERSION}-arm64.dmg"
rm -rf "$ROOT/dist/dmg"
mkdir -p "$ROOT/dist/dmg"
ditto "$APP" "$ROOT/dist/dmg/Copy 4 AI.app"
rm -f "$DMG"
create-dmg \
    --volname "Copy 4 AI" \
    --background "$ROOT/packaging/dmg-background.png" \
    --window-pos 200 120 \
    --window-size 660 420 \
    --icon-size 120 \
    --icon "Copy 4 AI.app" 180 220 \
    --hide-extension "Copy 4 AI.app" \
    --app-drop-link 480 220 \
    "$DMG" "$ROOT/dist/dmg"

echo "==> Done"
echo "$APP"
echo "$DMG"
shasum -a 256 "$DMG"
