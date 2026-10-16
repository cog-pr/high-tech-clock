"""A single heartbeat that drives every animated and time-dependent widget."""
from __future__ import annotations

import time
from datetime import datetime

from PySide6.QtCore import QObject, Qt, QTimer, Signal


class TimeEngine(QObject):
    frame = Signal(float)        # epoch seconds, emitted every animation frame
    second = Signal(object)      # naive local datetime, once per wall-clock second
    minute = Signal(object)
    day = Signal(object)

    IDLE_INTERVAL_MS = 250       # while the window is hidden: keep alarms alive, skip drawing

    def __init__(self, fps: int = 60, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._fps = fps
        self._active = True
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.timeout.connect(self._tick)
        self._last_sec: int | None = None
        self._last_min: int | None = None
        self._last_day = None
        self._apply_interval()

    @property
    def fps(self) -> int:
        return self._fps

    def set_fps(self, fps: int) -> None:
        self._fps = max(10, min(144, int(fps)))
        self._apply_interval()

    def set_active(self, active: bool) -> None:
        """Hidden/minimised windows only need the 1 Hz bookkeeping, not 60 fps."""
        self._active = active
        self._apply_interval()

    def _apply_interval(self) -> None:
        interval = round(1000 / self._fps) if self._active else self.IDLE_INTERVAL_MS
        self._timer.setInterval(max(1, interval))

    def start(self) -> None:
        self._timer.start()
        self._tick()

    @staticmethod
    def now() -> datetime:
        return datetime.now()

    def _tick(self) -> None:
        t = time.time()
        sec = int(t)
        if sec != self._last_sec:
            self._last_sec = sec
            now = datetime.fromtimestamp(sec)
            self.second.emit(now)
            minute_key = sec // 60
            if minute_key != self._last_min:
                self._last_min = minute_key
                self.minute.emit(now)
            if now.date() != self._last_day:
                self._last_day = now.date()
                self.day.emit(now)
        if self._active:
            self.frame.emit(t)
