"""Digital readout strip under the clock: date block · 7-segment time · zone block."""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QWidget

from .. import theme as T
from ..core.engine import TimeEngine
from .panels.world import fmt_offset
from .widgets import SegmentDisplay

WEEKDAYS_EN = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"]
WEEKDAYS_JP = ["月曜日", "火曜日", "水曜日", "木曜日", "金曜日", "土曜日", "日曜日"]


class _InfoBlock(QWidget):
    def __init__(self, align: Qt.AlignmentFlag, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._align = align
        self._top, self._bottom = "", ""
        self.setFixedWidth(170)
        self._f_top = T.font(15, "semibold", spacing=1.6)
        self._f_bottom = T.font(10.5, "regular", spacing=1.0)

    def set_lines(self, top: str, bottom: str) -> None:
        if (top, bottom) != (self._top, self._bottom):
            self._top, self._bottom = top, bottom
            self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        left = bool(self._align & Qt.AlignmentFlag.AlignLeft)
        flags = (Qt.AlignmentFlag.AlignLeft if left else Qt.AlignmentFlag.AlignRight) | Qt.AlignmentFlag.AlignVCenter
        pad = 14
        p.setFont(self._f_top)
        p.setPen(T.qc(T.TEXT))
        p.drawText(QRectF(pad if left else 0, H * 0.18, W - pad, H * 0.36), flags, self._top)
        p.setFont(self._f_bottom)
        p.setPen(T.qc(T.TEXT_DIM))
        p.drawText(QRectF(pad if left else 0, H * 0.54, W - pad, H * 0.3), flags, self._bottom)
        # bracket that ties the block to the 7-segment display
        p.setPen(QPen(T.qc(T.VIOLET_LO), 1.4))
        x = 2.0 if left else W - 2.0
        d = 6.0 if left else -6.0
        p.drawLine(QPointF(x + d, 6), QPointF(x, 6))
        p.drawLine(QPointF(x, 6), QPointF(x, H - 6))
        p.drawLine(QPointF(x, H - 6), QPointF(x + d, H - 6))


class DigitalReadout(QWidget):
    def __init__(self, engine: TimeEngine, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.use_24h = True
        self.setFixedHeight(62)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)
        lay.setSpacing(10)
        self.left = _InfoBlock(Qt.AlignmentFlag.AlignLeft)
        self.seg = SegmentDisplay("00:00:00")
        self.seg.setMaximumWidth(330)
        self.right = _InfoBlock(Qt.AlignmentFlag.AlignRight)
        lay.addStretch(1)
        lay.addWidget(self.left)
        lay.addWidget(self.seg, 4)
        lay.addWidget(self.right)
        lay.addStretch(1)
        engine.second.connect(self.refresh)
        self.refresh(datetime.now())

    def resizeEvent(self, event) -> None:
        side = int(min(170, (self.width() - 350) / 2))       # info blocks yield to the digits
        for block in (self.left, self.right):
            block.setVisible(side >= 120)
            block.setFixedWidth(max(120, side))
        super().resizeEvent(event)

    def refresh(self, now: datetime) -> None:
        hour = now.hour if self.use_24h else (now.hour % 12 or 12)
        self.seg.setText(f"{hour:02d}:{now.minute:02d}:{now.second:02d}")
        self.left.set_lines(now.strftime("%Y.%m.%d"), f"{WEEKDAYS_EN[now.weekday()]} · {WEEKDAYS_JP[now.weekday()]}")
        zone = fmt_offset(now.astimezone().utcoffset())
        top = zone if self.use_24h else f"{'AM' if now.hour < 12 else 'PM'}  ·  {zone}"
        self.right.set_lines(top, f"DAY {now.timetuple().tm_yday:03d}  ·  W{now.isocalendar()[1]:02d}")
