#!/bin/bash
# Build Copy 4 AI.app and the DMG.
#
# Requirements: Xcode, XcodeGen, create-dmg, uv, Python 3.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

VERSION="$(tr -d '[:space:]' < VERSION)"
SWIFT_VERSION="$(sed -n 's/.*current = "\(.*\)"/\1/p' Packages/CP4AICore/Sources/CP4AICore/Version.swift)"
if [ "$VERSION" != "$SWIFT_VERSION" ]; then
    echo "version mismatch: VERSION=$VERSION Version.swift=$SWIFT_VERSION" >&2
    exit 1
fi

for command in xcodegen xcodebuild create-dmg python3 uv; do
    if ! command -v "$command" >/dev/null 2>&1; then
        echo "missing required tool: $command" >&2
        exit 1
    fi
done

echo "==> Fetching Pandoc, librsvg, libemf2svg and tokenizer data"
python3 packaging/fetch_native.py

echo "==> Building the PyMuPDF helper"
./packaging/build_pdf_helper.sh

echo "==> Generating the Xcode project"
xcodegen generate

echo "==> Building the app (Release)"
xcodebuild \
    -project Copy4AI.xcodeproj \
    -scheme Copy4AI \
    -configuration Release \
    -derivedDataPath build/DerivedData \
    CODE_SIGN_IDENTITY=- \
    CODE_SIGNING_ALLOWED=YES \
    MARKETING_VERSION="$VERSION" \
    CURRENT_PROJECT_VERSION="$VERSION" \
    build

APP="$ROOT/build/DerivedData/Build/Products/Release/Copy 4 AI.app"
if [ ! -d "$APP" ]; then
    echo "missing app bundle: $APP" >&2
    exit 1
fi

echo "==> Signing nested code"
codesign --force --sign - --timestamp=none "$APP/Contents/MacOS/cp4ai" 2>/dev/null || true
codesign --force --deep --sign - --timestamp=none "$APP"
codesign --verify --deep --strict --verbose=2 "$APP"

echo "==> Auditing bundled binaries"
while IFS= read -r -d '' binary; do
    if file "$binary" | grep -q 'Mach-O'; then
        if otool -L "$binary" 2>/dev/null | grep -Eq '@@HOMEBREW_PREFIX@@|/opt/homebrew|/usr/local/opt'; then
            echo "Homebrew reference remains in $binary" >&2
            otool -L "$binary" | grep -E '@@HOMEBREW_PREFIX@@|/opt/homebrew|/usr/local/opt' >&2
            exit 1
        fi
    fi
done < <(find "$APP/Contents/Resources/bin" "$APP/Contents/Resources/pdf-helper" -type f -print0 2>/dev/null)

echo "==> Building DMG"
DMG="$ROOT/dist/Copy4AI-${VERSION}-arm64.dmg"
STAGE="$ROOT/build/dmg"
rm -rf "$STAGE"
mkdir -p "$STAGE"
ditto "$APP" "$STAGE/Copy 4 AI.app"
rm -f "$DMG"
create-dmg \
    --volname "Copy 4 AI" \
    --background "$ROOT/packaging/dmg-background.png" \
    --window-pos 200 120 \
    --window-size 660 480 \
    --icon-size 120 \
    --icon "Copy 4 AI.app" 170 250 \
    --hide-extension "Copy 4 AI.app" \
    --app-drop-link 490 250 \
    "$DMG" "$STAGE"

echo "==> Done"
echo "$APP"
echo "$DMG"
shasum -a 256 "$DMG"
