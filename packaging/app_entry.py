"""Entry point for the PyInstaller macOS app bundle."""

from __future__ import annotations

import multiprocessing
import os
import sys
import tempfile
import traceback
from pathlib import Path

from cp4ai.resource_paths import resource_dir


def setup_environment() -> None:
    resources = resource_dir()
    bin_dir = resources / "bin"
    # The app always uses its own bundled tools.  A CLI user may have set
    # these variables globally for the uv CLI; the app must not inherit them.
    os.environ["CP4AI_PANDOC"] = str(bin_dir / "pandoc")
    os.environ["TIKTOKEN_CACHE_DIR"] = str(resources / "tiktoken")
    os.environ["FONTCONFIG_PATH"] = str(resources / "etc" / "fonts")
    pieces = [str(bin_dir), "/opt/homebrew/bin", "/usr/local/bin"]
    existing = os.environ.get("PATH", "/usr/bin:/bin:/usr/sbin:/sbin")
    os.environ["PATH"] = ":".join(pieces + [existing])


def _debug_log(message: str) -> None:
    log = Path.home() / "Library" / "Logs" / "Copy 4 AI-debug.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as handle:
        handle.write(message.rstrip() + "\n")


def _debug_ocr(path: Path) -> int:
    from cp4ai.core import ocr_image_livetext

    _debug_log(f"=== debug OCR {path}")
    try:
        _debug_log(repr(ocr_image_livetext(path)))
    except Exception:
        _debug_log(traceback.format_exc())
    return 0


def _debug_convert(path: Path) -> int:
    from cp4ai.md4ai import convert_one

    _debug_log(f"=== debug convert {path}")
    try:
        with tempfile.TemporaryDirectory(prefix="cp4ai_debug_") as tmp:
            output = Path(tmp) / "out.md"
            details = convert_one(path, output, True, "livetext")
            _debug_log(f"details: {details}")
            _debug_log(output.read_text(encoding="utf-8")[:4000])
    except Exception:
        _debug_log(traceback.format_exc())
    return 0


def main() -> int:
    setup_environment()
    argv = sys.argv[1:]
    if argv and argv[0] == "--debug-ocr" and len(argv) > 1:
        return _debug_ocr(Path(argv[1]))
    if argv and argv[0] == "--debug-convert" and len(argv) > 1:
        return _debug_convert(Path(argv[1]))

    from cp4ai.gui import run_gui

    return run_gui([])


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
