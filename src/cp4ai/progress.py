"""Cross-process progress events for pages and OCR jobs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class Sink(Protocol):
    def page(self) -> None: ...

    def ocr(self) -> None: ...


_sink: Sink | None = None


def set_sink(sink: Sink | None) -> None:
    global _sink
    _sink = sink


def page_done() -> None:
    if _sink is not None:
        _sink.page()


def ocr_done() -> None:
    if _sink is not None:
        _sink.ocr()


@dataclass
class WorkTotals:
    pages: int
    ocr: int


@dataclass
class WorkState:
    pages_total: int
    ocr_total: int
    pages_done: int = 0
    ocr_done: int = 0

    @property
    def fraction(self) -> float:
        total = self.pages_total + self.ocr_total
        if total <= 0:
            return 0.0
        return min(1.0, (self.pages_done + self.ocr_done) / total)

    def apply(self, event: tuple[str]) -> None:
        kind = event[0]
        if kind == "page":
            self.pages_done += 1
        elif kind == "ocr":
            self.ocr_done += 1


class QueueSink:
    """Sink used inside a ProcessPool worker."""

    def __init__(self, queue):
        self.queue = queue

    def page(self) -> None:
        self.queue.put(("page",))

    def ocr(self) -> None:
        self.queue.put(("ocr",))


class CallbackSink:
    """Sink used for in-process conversions."""

    def __init__(self, state: WorkState, callback):
        self.state = state
        self.callback = callback

    def page(self) -> None:
        self.state.apply(("page",))
        self.callback(self.state)

    def ocr(self) -> None:
        self.state.apply(("ocr",))
        self.callback(self.state)
