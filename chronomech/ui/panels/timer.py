"""05 · TIMER — countdown with presets; scroll the dial like a crown to adjust."""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget

from ... import theme as T
from ...core.countdown import Countdown
from ...core.engine import TimeEngine
from ..widgets import HudPanel, MechButton

PRESETS = [("1M", 60), ("3M", 180), ("5M", 300), ("10M", 600), ("15M", 900), ("25M", 1500)]


def fmt_timer(seconds: float) -> str:
    total = int(math.ceil(max(0.0, seconds) - 1e-6))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


class TimerDial(QWidget):
    custom_requested = Signal()

    def __init__(self, countdown: Countdown, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._cd = countdown
        self.setMinimumSize(96, 96)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.SizeVerCursor)
        self.setToolTip("ホイール: ±1分 (Shift: ±10秒)\nダブルクリック: 時間を入力")
        self._f_state = T.font(9, "semibold", spacing=1.6)
        self._f_total = T.font(9.5, "regular")

    def wheelEvent(self, event) -> None:
        step = 10 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 60
        delta = event.angleDelta().y() or event.angleDelta().x()
        self._cd.add(step if delta > 0 else -step)

    def mouseDoubleClickEvent(self, _event) -> None:
        self.custom_requested.emit()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        side = min(self.width(), self.height())
        c = QPointF(self.width() / 2, self.height() / 2)
        r = side / 2 - 4
        cd = self._cd
        frac = cd.progress()
        state = cd.state
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#0b0911"))
        p.drawEllipse(c, r, r)
        ticks, majors = QPainterPath(), QPainterPath()
        for i in range(60):
            a = T.clock_angle(i / 60)
            target = majors if i % 5 == 0 else ticks
            target.moveTo(T.polar(c.x(), c.y(), r * (0.86 if i % 5 == 0 else 0.9), a))
            target.lineTo(T.polar(c.x(), c.y(), r * 0.97, a))
        p.strokePath(ticks, QPen(T.qc(T.TEXT_FAINT), 1))
        p.strokePath(majors, QPen(T.qc(T.TEXT_DIM), 1.6))
        ring_r = r * 0.76
        rect = QRectF(c.x() - ring_r, c.y() - ring_r, 2 * ring_r, 2 * ring_r)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(T.qc(T.VIOLET_DEEP, 200), r * 0.1, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
        p.drawEllipse(c, ring_r, ring_r)
        if frac > 0:
            arc = QPainterPath()
            arc.arcMoveTo(rect, 90)
            arc.arcTo(rect, 90, -360 * frac)
            color = T.ALERT if (state == Countdown.RUNNING and cd.remaining() <= 10) else T.VIOLET
            p.strokePath(arc, QPen(T.qc(color, 60), r * 0.16, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
            p.strokePath(arc, QPen(T.qc(color), r * 0.08, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
            head = T.polar(c.x(), c.y(), ring_r, T.clock_angle(frac))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#f6eeff"))
            p.drawEllipse(head, r * 0.045, r * 0.045)
        text = fmt_timer(cd.remaining())
        f_time = T.font(r * (0.30 if len(text) <= 5 else 0.24), "semilight")
        color = T.ALERT if state == Countdown.DONE else (T.TEXT if state == Countdown.RUNNING else T.VIOLET_HI)
        T.draw_tabular(p, c.x(), c.y() + r * 0.10, text, f_time, color, Qt.AlignmentFlag.AlignHCenter)
        label = {Countdown.IDLE: "READY", Countdown.RUNNING: "RUNNING",
                 Countdown.PAUSED: "PAUSED", Countdown.DONE: "COMPLETE"}[state]
        p.setFont(self._f_state)
        p.setPen(T.qc(T.VIOLET_HI if state == Countdown.RUNNING else T.TEXT_DIM))
        p.drawText(QRectF(c.x() - r, c.y() - r * 0.42, 2 * r, r * 0.2), Qt.AlignmentFlag.AlignCenter, label)
        p.setFont(self._f_total)
        p.setPen(T.qc(T.TEXT_FAINT))
        p.drawText(QRectF(c.x() - r, c.y() + r * 0.24, 2 * r, r * 0.2), Qt.AlignmentFlag.AlignCenter,
                   "SET " + fmt_timer(cd.duration))


class TimerPanel(HudPanel):
    custom_requested = Signal()

    def __init__(self, countdown: Countdown, engine: TimeEngine, parent: QWidget | None = None) -> None:
        super().__init__("05", "TIMER", "タイマー", parent)
        self._cd = countdown
        row = QHBoxLayout()
        row.setSpacing(10)
        self.dial = TimerDial(countdown)
        self.dial.custom_requested.connect(self.custom_requested)
        row.addWidget(self.dial, 5)
        side = QVBoxLayout()
        side.setSpacing(5)
        grid = QGridLayout()
        grid.setSpacing(5)
        for i, (label, secs) in enumerate(PRESETS):
            b = MechButton(label, height=24, font_px=10.5)
            b.setToolTip("25M = ポモドーロ" if secs == 1500 else f"{secs // 60} 分")
            b.clicked.connect(lambda _=False, s=secs: countdown.set_duration(s))
            grid.addWidget(b, i // 3, i % 3)
        side.addLayout(grid)
        side.addStretch(1)
        self.start_btn = MechButton("START", accent=True, height=27)
        self.start_btn.setToolTip("スタート / 一時停止  [T]")
        self.reset_btn = MechButton("RESET", height=27)
        self.start_btn.clicked.connect(countdown.toggle)
        self.reset_btn.clicked.connect(countdown.reset)
        side.addWidget(self.start_btn)
        side.addWidget(self.reset_btn)
        row.addLayout(side, 4)
        self.body.addLayout(row)
        countdown.changed.connect(self._sync)
        engine.frame.connect(self._on_frame)
        self._frame = 0
        self._sync()

    def _sync(self) -> None:
        state = self._cd.state
        self.start_btn.setText({Countdown.RUNNING: "PAUSE", Countdown.PAUSED: "RESUME"}.get(state, "START"))
        self.start_btn.set_accent(state != Countdown.RUNNING)
        self.set_status({Countdown.RUNNING: "● ARMED", Countdown.PAUSED: "Ⅱ HOLD",
                         Countdown.DONE: "■ DONE"}.get(state, ""),
                        T.ALERT if state == Countdown.DONE else T.VIOLET_HI)
        self.dial.update()

    def _on_frame(self, _t: float) -> None:
        self._cd.poll()
        if self._cd.state == Countdown.RUNNING:
            self._frame += 1
            if self._frame % 3 == 0:
                self.dial.update()
