"""Locate the Pandoc executable used by the converters.

The macOS app bundles Pandoc 3.14 and points ``CP4AI_PANDOC`` at it.  CLI
users install Pandoc themselves (for example with ``brew install pandoc``) and
the CLI resolves it from ``PATH``.
"""

from __future__ import annotations

import functools
import os
import shutil
import subprocess
from pathlib import Path

HOMEBREW_PANDOC_PATHS = (
    Path("/opt/homebrew/bin/pandoc"),
    Path("/usr/local/bin/pandoc"),
)


def find_pandoc() -> str | None:
    """Return the first usable Pandoc path, or ``None``."""
    override = os.environ.get("CP4AI_PANDOC")
    if override:
        candidate = Path(override).expanduser()
        if candidate.is_file():
            return str(candidate)

    found = shutil.which("pandoc")
    if found:
        return found

    for candidate in HOMEBREW_PANDOC_PATHS:
        if candidate.is_file():
            return str(candidate)
    return None


def pandoc_binary() -> str:
    """Return the Pandoc path or raise a helpful error."""
    path = find_pandoc()
    if path:
        return path
    raise RuntimeError(
        "pandoc not found. Install it with: brew install pandoc "
        "(or install the Copy 4 AI app, which bundles it)"
    )


@functools.lru_cache(maxsize=1)
def pandoc_version() -> str:
    """Return the Pandoc version string, for front-matter metadata."""
    try:
        proc = subprocess.run(
            [pandoc_binary(), "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    first = proc.stdout.splitlines()[0].strip() if proc.stdout else ""
    if first.lower().startswith("pandoc"):
        return first[6:].strip() or "unknown"
    return first or "unknown"
