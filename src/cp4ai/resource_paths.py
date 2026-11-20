"""Locate bundled resources in source trees and PyInstaller app bundles."""

from __future__ import annotations

import sys
from pathlib import Path


def resource_dir() -> Path:
    if not getattr(sys, "frozen", False):
        return Path(__file__).resolve().parent / "resources"

    candidates: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass))
    candidates.append(Path(sys.executable).resolve().parent.parent / "Resources")

    for candidate in candidates:
        if (candidate / "bin" / "pandoc").exists() or (candidate / "quickaction").is_dir():
            return candidate
    return candidates[0]
