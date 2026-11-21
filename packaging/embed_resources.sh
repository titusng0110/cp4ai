#!/bin/bash
# Copy bundled tools into Copy 4 AI.app/Contents and ad-hoc sign the Mach-O
# files.  Called from the Xcode post-build phase and from build_app.sh.
set -euo pipefail

CONTENTS="${1:-}"
if [ -z "$CONTENTS" ] || [ ! -d "$CONTENTS" ]; then
    echo "usage: embed_resources.sh <Contents-directory>" >&2
    exit 2
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RESOURCES="$CONTENTS/Resources"
mkdir -p "$RESOURCES"

copy_if_present() {
    local source="$1"
    local destination="$2"
    if [ -e "$source" ]; then
        rm -rf "$destination"
        mkdir -p "$(dirname "$destination")"
        if [ -d "$source" ]; then
            ditto "$source" "$destination"
        else
            cp "$source" "$destination"
        fi
    fi
}

copy_if_present "$ROOT/packaging/native/bin" "$RESOURCES/bin"
copy_if_present "$ROOT/build/pdf-helper" "$RESOURCES/pdf-helper"
copy_if_present "$ROOT/packaging/native/tiktoken" "$RESOURCES/tiktoken"
copy_if_present "$ROOT/Resources/fonts.conf" "$RESOURCES/fonts.conf"
copy_if_present "$ROOT/branding/CP4AI.icns" "$RESOURCES/CP4AI.icns"
copy_if_present "$ROOT/THIRD_PARTY_NOTICES.md" "$RESOURCES/THIRD_PARTY_NOTICES.md"
copy_if_present "$ROOT/LICENSE" "$RESOURCES/LICENSE"

sign_file() {
    local file="$1"
    if [ -L "$file" ]; then
        return
    fi
    if file "$file" 2>/dev/null | grep -q 'Mach-O'; then
        codesign --force --sign - --timestamp=none "$file" >/dev/null 2>&1 || true
    fi
}

if command -v codesign >/dev/null 2>&1; then
    while IFS= read -r -d '' file; do
        sign_file "$file"
    done < <(find "$RESOURCES" -type f -print0)
fi

echo "embedded resources in $RESOURCES"
