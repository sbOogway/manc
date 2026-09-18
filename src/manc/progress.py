"""A stderr spinner for the long steps of a run, silent unless stderr is a terminal.

`spinner("tagging 331 headlines")` animates a line while the block runs; the logging
`Handler` clears that line before every record so log output stays readable on a terminal
and untouched in a cron mail.
"""

import itertools
import logging
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import IO

FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
CLEAR = "\r\033[K"

_current: "Spinner | None" = None


class Spinner:
    def __init__(self, label: str, stream: IO[str], interval: float) -> None:
        self.label = label
        self.stream = stream
        self.interval = interval
        self.active = stream.isatty()
        self.frames = itertools.cycle(FRAMES)
        self.lock = threading.Lock()
        self.stopping = threading.Event()
        self.thread = threading.Thread(target=self._spin, daemon=True)

    def tick(self) -> None:
        if self.active:
            with self.lock:
                self.stream.write(f"\r{next(self.frames)} {self.label}")
                self.stream.flush()

    def clear(self) -> None:
        if self.active:
            with self.lock:
                self.stream.write(CLEAR)
                self.stream.flush()

    def _spin(self) -> None:
        while not self.stopping.wait(self.interval):
            self.tick()

    def start(self) -> None:
        if self.active:
            self.thread.start()

    def stop(self) -> None:
        self.stopping.set()
        if self.thread.is_alive():
            self.thread.join()
        self.clear()


@contextmanager
def spinner(label: str, stream: IO[str] = sys.stderr, interval: float = 0.1) -> Iterator[Spinner]:
    global _current
    current = Spinner(label, stream, interval)
    _current = current
    current.start()
    try:
        yield current
    finally:
        current.stop()
        _current = None


class Handler(logging.StreamHandler):
    """A StreamHandler that wipes the spinner line before each record."""

    def emit(self, record: logging.LogRecord) -> None:
        if _current is not None:
            _current.clear()
        super().emit(record)
