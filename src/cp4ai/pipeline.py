"""Shared conversion pipeline used by the CLIs and the macOS app."""

from __future__ import annotations

import multiprocessing
import shutil
import subprocess
import tempfile
import threading
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from .progress import (
    CallbackSink,
    QueueSink,
    WorkState,
    WorkTotals,
    set_sink,
)

SOURCE_SUFFIXES = {".docx", ".pdf", ".pptx"}


@dataclass(frozen=True)
class Rejected:
    path: Path
    reason: str


@dataclass(frozen=True)
class BatchResult:
    markdown: str
    chars: int
    tokens: int
    files: list[Path]


class BatchFailure(Exception):
    """Raised when one or more files failed; the clipboard is untouched."""

    def __init__(self, errors: Sequence[tuple[Path, str]]):
        self.errors = list(errors)
        super().__init__(f"{len(self.errors)} file(s) failed")


ProgressCallback = Callable[
    [int, int, Path, str | None, str | None],
    None,
]
WorkProgressCallback = Callable[[WorkState], None]


def _init_worker_progress(queue) -> None:
    set_sink(QueueSink(queue))


def filter_sources(paths: Iterable[Path | str]) -> tuple[list[Path], list[Rejected]]:
    """Split selections into supported files and rejected entries.

    Directories are never accepted.  Duplicate paths are collapsed while
    preserving the caller's order.
    """
    valid: list[Path] = []
    rejected: list[Rejected] = []
    seen: set[Path] = set()

    for raw in paths:
        path = Path(raw).expanduser()
        try:
            key = path.resolve()
        except OSError:
            key = path
        if key in seen:
            continue
        seen.add(key)

        if path.is_dir():
            rejected.append(Rejected(path, "directories are not supported"))
        elif not path.exists():
            rejected.append(Rejected(path, "not found"))
        elif not path.is_file():
            rejected.append(Rejected(path, "not a regular file"))
        elif path.suffix.lower() not in SOURCE_SUFFIXES:
            rejected.append(
                Rejected(path, "unsupported file type (expected .docx, .pdf or .pptx)")
            )
        else:
            valid.append(path)
    return valid, rejected


def sort_sources(paths: Iterable[Path]) -> list[Path]:
    """Stable, Finder-friendly ordering by file name."""
    return sorted(paths, key=lambda path: path.name.casefold())


def check_pandoc(sources: Sequence[Path]) -> str | None:
    """Return an error message when Pandoc is needed but unavailable."""
    if not any(path.suffix.lower() in {".docx", ".pptx"} for path in sources):
        return None
    from .pandoc import find_pandoc

    if find_pandoc():
        return None
    return "pandoc not found. Install it with: brew install pandoc"


def check_tesseract(engine: str) -> str | None:
    """Tesseract is opt-in and must be supplied by the user."""
    if engine != "tesseract":
        return None
    if shutil.which("tesseract"):
        return None
    return "--tesseract requires Tesseract. Install it with: brew install tesseract"


def count_work(sources: Sequence[Path]) -> WorkTotals:
    """Estimate pages and OCR jobs before conversion starts."""
    from .core import count_ocr_jobs, count_pages

    pages = 0
    ocr = 0
    for source in sources:
        try:
            pages += count_pages(source)
            ocr += count_ocr_jobs(source)
        except Exception:  # noqa: BLE001 - conversion will report the real error
            continue
    return WorkTotals(pages=pages, ocr=ocr)


def convert_batch(
    sources: Sequence[Path],
    *,
    engine: str,
    use_ocr: bool,
    jobs: int,
    progress: ProgressCallback | None = None,
    work_progress: WorkProgressCallback | None = None,
    force_process: bool = False,
) -> BatchResult:
    """Convert files, concatenate them, and return clipboard-ready Markdown.

    Individual failures are reported through ``progress`` and collected into
    :class:`BatchFailure`; successful files are never copied when any file
    fails.  ``work_progress`` receives page/OCR counters aggregated across all
    files.
    """
    # Imported lazily so the GUI can show its window before pymupdf, ocrmac
    # and tiktoken are loaded.
    from .md4ai import convert_one

    sources = list(sources)
    total = len(sources)
    errors: list[tuple[Path, str]] = []
    state: WorkState | None = None
    if work_progress is not None:
        totals = count_work(sources)
        state = WorkState(pages_total=totals.pages, ocr_total=totals.ocr)
        work_progress(state)

    with tempfile.TemporaryDirectory(prefix="cp4ai_clipboard_") as tmp:
        workdir = Path(tmp)
        planned = [
            (source, workdir / f"{index:04d}.md")
            for index, source in enumerate(sources)
        ]

        use_processes = force_process or (jobs > 1 and total > 1)
        if not use_processes:
            sink = (
                CallbackSink(state, work_progress)
                if state is not None and work_progress is not None
                else None
            )
            if sink:
                set_sink(sink)
            try:
                for index, (source, output) in enumerate(planned, start=1):
                    try:
                        details = convert_one(source, output, use_ocr, engine)
                    except Exception as exc:  # noqa: BLE001 - report and continue
                        errors.append((source, str(exc)))
                        if progress:
                            progress(index, total, source, None, str(exc))
                    else:
                        if progress:
                            progress(index, total, source, details, None)
            finally:
                if sink:
                    set_sink(None)
        else:
            workers = min(max(1, jobs), total)
            completed = 0
            queue = None
            drain = None
            if state is not None and work_progress is not None:
                ctx = multiprocessing.get_context("spawn")
                queue = ctx.Queue()

                def drain_events() -> None:
                    while True:
                        event = queue.get()
                        if event is None:
                            break
                        state.apply(event)
                        work_progress(state)

                drain = threading.Thread(target=drain_events, daemon=True)
                drain.start()

            initializer = _init_worker_progress if queue is not None else None
            initargs = (queue,) if queue is not None else ()
            try:
                with ProcessPoolExecutor(
                    max_workers=workers,
                    initializer=initializer,
                    initargs=initargs,
                ) as pool:
                    futures = {
                        pool.submit(
                            convert_one, source, output, use_ocr, engine
                        ): source
                        for source, output in planned
                    }
                    for future in as_completed(futures):
                        source = futures[future]
                        completed += 1
                        try:
                            details = future.result()
                        except Exception as exc:  # noqa: BLE001 - report and continue
                            errors.append((source, str(exc)))
                            if progress:
                                progress(
                                    completed, total, source, None, str(exc)
                                )
                        else:
                            if progress:
                                progress(
                                    completed, total, source, details, None
                                )
            finally:
                if queue is not None:
                    queue.put(None)
                    drain.join(timeout=10)
                    queue.close()
                    queue.join_thread()

        if errors:
            raise BatchFailure(errors)

        if state is not None and work_progress is not None:
            state.pages_total = state.pages_done
            state.ocr_total = state.ocr_done
            work_progress(state)

        sections = []
        for source, output in planned:
            body = output.read_text(encoding="utf-8").rstrip()
            sections.append(f"[{source.name} BEGIN]\n{body}\n[{source.name} END]")
        markdown = "\n\n".join(sections) + "\n"

    return BatchResult(
        markdown=markdown,
        chars=len(markdown),
        tokens=count_tokens(markdown),
        files=sources,
    )


def count_tokens(text: str) -> int:
    import tiktoken

    return len(tiktoken.get_encoding("cl100k_base").encode(text))


def copy_to_clipboard(text: str) -> None:
    subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True)
