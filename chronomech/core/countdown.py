"""Countdown timer model (also projected onto the clock bezel like a dive watch)."""
from __future__ import annotations

import time

from PySide6.QtCore import QObject, Signal

MAX_SECONDS = 99 * 3600 + 59 * 60 + 59


class Countdown(QObject):
    IDLE, RUNNING, PAUSED, DONE = "idle", "running", "paused", "done"

    changed = Signal()
    finished = Signal()

    def __init__(self, seconds: float = 300, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.state = self.IDLE
        self._duration = float(max(1, min(MAX_SECONDS, seconds)))
        self._total = self._duration        # grows when time is added mid-run
        self._remaining = self._duration    # valid while idle/paused
        self._end = 0.0                     # perf_counter deadline while running

    @property
    def duration(self) -> float:
        return self._duration

    @property
    def total(self) -> float:
        return self._total

    def remaining(self) -> float:
        if self.state == self.RUNNING:
            return max(0.0, self._end - time.perf_counter())
        if self.state == self.DONE:
            return 0.0
        return self._remaining

    def progress(self) -> float:
        """Fraction of time left: 1.0 = full, 0.0 = elapsed."""
        return 0.0 if self._total <= 0 else max(0.0, min(1.0, self.remaining() / self._total))

    def end_epoch(self) -> float | None:
        """Wall-clock moment the timer will fire (None when not armed)."""
        if self.state in (self.RUNNING, self.PAUSED):
            return time.time() + self.remaining()
        return None

    def set_duration(self, seconds: float) -> None:
        self._duration = float(max(1, min(MAX_SECONDS, round(seconds))))
        self.state = self.IDLE
        self._total = self._remaining = self._duration
        self.changed.emit()

    def add(self, seconds: float) -> None:
        if self.state in (self.IDLE, self.DONE):
            self.set_duration(max(1.0, (self._duration if self.state == self.IDLE else 0) + seconds))
            return
        if self.state == self.RUNNING:
            left = self.remaining()
            seconds = max(seconds, 1.0 - left)          # never go below one second
            self._end += seconds
        else:
            seconds = max(seconds, 1.0 - self._remaining)
            self._remaining += seconds
        self._total = max(1.0, self._total + seconds)
        self.changed.emit()

    def start(self) -> None:
        if self.state == self.RUNNING:
            return
        if self.state == self.DONE:
            self._remaining = self._total = self._duration
        self._end = time.perf_counter() + self._remaining
        self.state = self.RUNNING
        self.changed.emit()

    def pause(self) -> None:
        if self.state == self.RUNNING:
            self._remaining = self.remaining()
            self.state = self.PAUSED
            self.changed.emit()

    def toggle(self) -> None:
        self.pause() if self.state == self.RUNNING else self.start()

    def reset(self) -> None:
        self.state = self.IDLE
        self._total = self._remaining = self._duration
        self.changed.emit()

    def poll(self) -> None:
        if self.state == self.RUNNING and self.remaining() <= 0.0:
            self.state = self.DONE
            self.changed.emit()
            self.finished.emit()
