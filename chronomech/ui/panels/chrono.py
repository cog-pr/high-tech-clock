"""04 · CHRONOGRAPH — stopwatch with laps; drives the clock's chrono hands too."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QWidget

from ... import theme as T
from ...core.chrono import Stopwatch
from ...core.engine import TimeEngine
from ..widgets import HudPanel, MechButton, SegmentDisplay, fmt_duration


def short(seconds: float) -> str:
    m, s = divmod(seconds, 60)
    h, m = divmod(int(m), 60)
    return f"{h}:{m:02d}:{s:05.2f}" if h else f"{m:02d}:{s:05.2f}"


class LapView(QWidget):
    def __init__(self, stopwatch: Stopwatch, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._sw = stopwatch
        self._scroll = 0.0
        self.setMinimumHeight(40)
        self._f_head = T.font(9, "semibold", spacing=1.2)
        self._f_row = T.font(12, "regular")
        self._f_tag = T.font(9, "semibold", spacing=0.8)
        self._row_h = 21.0

    def wheelEvent(self, event) -> None:
        rows = len(self._sw.laps) + (1 if self._sw.running else 0)
        limit = max(0.0, rows * self._row_h - (self.height() - 18))
        self._scroll = max(0.0, min(limit, self._scroll - event.angleDelta().y() / 4))
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        laps = self._sw.laps
        p.setFont(self._f_head)
        p.setPen(T.qc(T.TEXT_FAINT))
        p.drawText(QPointF(2, 10), "LAP")
        p.drawText(QRectF(0, 0, W * 0.66, 13), Qt.AlignmentFlag.AlignRight, "LAP TIME")
        p.drawText(QRectF(0, 0, W - 2, 13), Qt.AlignmentFlag.AlignRight, "TOTAL")
        p.setPen(QPen(T.qc(T.LINE), 1))
        p.drawLine(QPointF(0, 15.5), QPointF(W, 15.5))
        if not laps and not self._sw.running:
            p.setFont(self._f_head)
            p.setPen(T.qc(T.TEXT_FAINT))
            p.drawText(QRectF(0, 16, W, H - 16), Qt.AlignmentFlag.AlignCenter, "SPACE: START / STOP    L: LAP")
            return
        rows: list[tuple[str, float, float, str]] = []
        if self._sw.running:
            total = self._sw.elapsed()
            prev = laps[-1].split if laps else 0.0
            rows.append((f"{len(laps) + 1:02d}", total - prev, total, "live"))
        best = min(laps, key=lambda l: l.duration) if len(laps) > 1 else None
        worst = max(laps, key=lambda l: l.duration) if len(laps) > 1 else None
        for lap in reversed(laps):
            tag = "best" if lap is best else ("worst" if lap is worst else "")
            rows.append((f"{lap.index:02d}", lap.duration, lap.split, tag))
        p.save()
        p.setClipRect(QRectF(0, 17, W, H - 17))
        for i, (idx, dur, total, tag) in enumerate(rows):
            y = 18 + i * self._row_h - self._scroll
            if y > H or y + self._row_h < 17:
                continue
            base = y + self._row_h * 0.7
            color = {"live": T.VIOLET_HI, "best": "#ffffff", "worst": T.ALERT}.get(tag, T.TEXT_DIM)
            if tag == "live":
                p.fillRect(QRectF(0, y, W, self._row_h - 2), T.qc(T.VIOLET_DEEP, 80))
            p.setFont(self._f_row)
            p.setPen(T.qc(T.TEXT_DIM))
            p.drawText(QPointF(2, base), idx)
            if tag:
                p.setFont(self._f_tag)
                p.setPen(T.qc(color, 200))
                p.drawText(QPointF(26, base - 1), {"live": "●", "best": "▲", "worst": "▼"}[tag])
            T.draw_tabular(p, W * 0.66, base, short(dur), self._f_row, color, Qt.AlignmentFlag.AlignRight)
            T.draw_tabular(p, W - 2, base, short(total), self._f_row, T.qc(T.TEXT_DIM), Qt.AlignmentFlag.AlignRight)
        p.restore()


class ChronoPanel(HudPanel):
    def __init__(self, stopwatch: Stopwatch, engine: TimeEngine, parent: QWidget | None = None) -> None:
        super().__init__("04", "CHRONOGRAPH", "ストップウォッチ", parent)
        self._sw = stopwatch
        self._frame = 0
        self.display = SegmentDisplay("00:00:00.00")
        self.display.set_small_tail(3)
        self.display.setMinimumHeight(36)
        self.display.setMaximumHeight(58)
        self.body.addWidget(self.display, 3)
        row = QHBoxLayout()
        row.setSpacing(6)
        self.start_btn = MechButton("START", accent=True, height=28)
        self.lap_btn = MechButton("LAP", height=28)
        self.start_btn.setToolTip("スタート / ストップ  [Space]")
        self.lap_btn.setToolTip("ラップ / リセット  [L] / [R]")
        self.start_btn.clicked.connect(stopwatch.toggle)
        self.lap_btn.clicked.connect(stopwatch.lap_or_reset)
        row.addWidget(self.start_btn, 1)
        row.addWidget(self.lap_btn, 1)
        self.body.addLayout(row)
        self.laps = LapView(stopwatch)
        self.body.addWidget(self.laps, 4)
        stopwatch.changed.connect(self._sync)
        engine.frame.connect(self._on_frame)
        self._sync()

    def _sync(self) -> None:
        running = self._sw.running
        self.start_btn.setText("STOP" if running else ("RESUME" if not self._sw.is_reset else "START"))
        self.start_btn.setChecked(False)
        self.start_btn.set_accent(not running)
        self.lap_btn.setText("LAP" if running or self._sw.is_reset else "RESET")
        self.lap_btn.setEnabled(running or not self._sw.is_reset)
        self.set_status("● RUN" if running else ("Ⅱ HOLD" if not self._sw.is_reset else ""),
                        T.VIOLET_HI if running else T.TEXT_DIM)
        self.display.set_colors(T.VIOLET_HI if running or self._sw.is_reset else "#e9dcff")
        self.display.setText(fmt_duration(self._sw.elapsed()))
        self.laps.update()

    def _on_frame(self, _t: float) -> None:
        if not self._sw.running:
            return
        self._frame += 1
        if self._frame % 2:          # 30 Hz is plenty for a centisecond readout
            return
        self.display.setText(fmt_duration(self._sw.elapsed()))
        self.laps.update()
