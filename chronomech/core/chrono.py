"""Chronograph (stopwatch) model shared by the side panel and the clock's chrono hands."""
from __future__ import annotations

import time
from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal


@dataclass(frozen=True)
class Lap:
    index: int
    split: float      # total elapsed when the lap was taken
    duration: float   # length of this lap


class Stopwatch(QObject):
    changed = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._running = False
        self._t0 = 0.0
        self._accumulated = 0.0
        self.laps: list[Lap] = []

    @property
    def running(self) -> bool:
        return self._running

    @property
    def is_reset(self) -> bool:
        return not self._running and self._accumulated == 0.0 and not self.laps

    def elapsed(self) -> float:
        if self._running:
            return self._accumulated + (time.perf_counter() - self._t0)
        return self._accumulated

    def start(self) -> None:
        if not self._running:
            self._t0 = time.perf_counter()
            self._running = True
            self.changed.emit()

    def stop(self) -> None:
        if self._running:
            self._accumulated += time.perf_counter() - self._t0
            self._running = False
            self.changed.emit()

    def toggle(self) -> None:
        self.stop() if self._running else self.start()

    def lap(self) -> None:
        if not self._running:
            return
        total = self.elapsed()
        previous = self.laps[-1].split if self.laps else 0.0
        self.laps.append(Lap(len(self.laps) + 1, total, total - previous))
        self.changed.emit()

    def reset(self) -> None:
        self._running = False
        self._accumulated = 0.0
        self.laps.clear()
        self.changed.emit()

    def lap_or_reset(self) -> None:
        """Lower pusher of a real chronograph: lap while running, reset when stopped."""
        self.lap() if self._running else self.reset()
