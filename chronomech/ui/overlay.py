"""Full-window alert overlay used by alarms and the countdown timer."""
from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QFontMetricsF, QPainter, QPen
from PySide6.QtWidgets import QWidget

from .. import theme as T
from .widgets import MechButton


@dataclass
class Alert:
    kind: str             # "ALARM" / "TIMER"
    headline: str         # big text, e.g. "07:00"
    detail: str           # label / description
    snooze: bool
    payload: Any = None


class AlertOverlay(QWidget):
    dismissed = Signal(object)      # Alert
    snoozed = Signal(object)        # Alert

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.hide()
        self._queue: list[Alert] = []
        self._t0 = 0.0
        self._pulse = QTimer(self)
        self._pulse.setInterval(33)
        self._pulse.timeout.connect(self.update)
        self.snooze_btn = MechButton("SNOOZE  5M", self, height=36, min_width=160, font_px=12.5)
        self.dismiss_btn = MechButton("DISMISS", self, accent=True, height=36, min_width=160, font_px=12.5)
        self.snooze_btn.clicked.connect(self.snooze)
        self.dismiss_btn.clicked.connect(self.dismiss)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        parent.installEventFilter(self)                     # always cover the whole parent
        self._f_kind = T.font(13, "semibold", spacing=6)
        self._f_head = T.font(64, "light")
        self._f_detail = T.font(16, "regular", spacing=1)
        self._f_hint = T.font(10, "regular", spacing=1.2)

    @property
    def active(self) -> bool:
        return bool(self._queue)

    def eventFilter(self, watched, event) -> bool:
        if watched is self.parentWidget() and event.type() == QEvent.Type.Resize:
            self.setGeometry(self.parentWidget().rect())
        return False

    def push(self, alert: Alert) -> None:
        self._queue.append(alert)
        self._show_current()

    def _show_current(self) -> None:
        if not self._queue:
            self._pulse.stop()
            self.hide()
            return
        self.snooze_btn.setVisible(self._queue[0].snooze)
        self.setGeometry(self.parentWidget().rect())
        self._place_buttons()
        self._t0 = time.perf_counter()
        self.raise_()
        self.show()
        self.setFocus()
        self._pulse.start()
        self.update()

    def dismiss(self) -> None:
        if self._queue:
            self.dismissed.emit(self._queue.pop(0))
        self._show_current()

    def snooze(self) -> None:
        if self._queue and self._queue[0].snooze:
            self.snoozed.emit(self._queue.pop(0))
        self._show_current()

    def _card(self) -> QRectF:
        w = min(560.0, self.width() - 40.0)
        h = 280.0
        return QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)

    def _place_buttons(self) -> None:
        card = self._card()
        y = int(card.bottom() - 58)
        bw = 170
        if self._queue and self._queue[0].snooze:
            self.snooze_btn.setGeometry(int(card.center().x() - bw - 8), y, bw, 36)
            self.dismiss_btn.setGeometry(int(card.center().x() + 8), y, bw, 36)
        else:
            self.dismiss_btn.setGeometry(int(card.center().x() - bw / 2), y, bw, 36)

    def resizeEvent(self, _event) -> None:
        self._place_buttons()

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Escape, Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.dismiss()
        elif event.key() == Qt.Key.Key_S:
            self.snooze()

    def mousePressEvent(self, event) -> None:
        event.accept()                    # swallow clicks so the UI underneath stays inert

    def paintEvent(self, _event) -> None:
        if not self._queue:
            return
        alert = self._queue[0]
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = time.perf_counter() - self._t0
        pulse = 0.5 + 0.5 * math.sin(t * 5.0)
        p.fillRect(self.rect(), T.qc("#030206", 205))
        card = self._card()
        frame = T.chamfer_path(card, 18, tl=True, tr=True, br=True, bl=True)
        for i in range(4, 0, -1):
            p.strokePath(frame, QPen(T.qc(T.VIOLET, int(20 + 30 * pulse) // i), 2 + i * 6))
        p.fillPath(frame, T.qc("#0d0a15"))
        p.strokePath(frame, QPen(T.mix(T.VIOLET, "#ffffff", pulse * 0.4), 1.6))
        # hazard stripes across the top of the card
        band = QRectF(card.left() + 18, card.top() + 14, card.width() - 36, 10)
        p.save()
        p.setClipRect(band)
        p.fillRect(band, T.qc(T.VIOLET_DEEP))
        p.setPen(QPen(T.qc(T.VIOLET, 200), 5))
        x = band.left() - 20 + (t * 30) % 14
        while x < band.right() + 20:
            p.drawLine(QPointF(x, band.bottom()), QPointF(x + 10, band.top()))
            x += 14
        p.restore()
        p.setFont(self._f_kind)
        p.setPen(T.qc(T.VIOLET_HI))
        p.drawText(QRectF(card.left(), card.top() + 34, card.width(), 22), Qt.AlignmentFlag.AlignCenter,
                   f"▲  {alert.kind}  ▲")
        T.draw_tabular(p, card.center().x(), card.top() + 132, alert.headline, self._f_head,
                       T.mix(T.TEXT, "#ffffff", pulse), Qt.AlignmentFlag.AlignHCenter)
        p.setFont(self._f_detail)
        p.setPen(T.qc(T.TEXT_DIM))
        fm = QFontMetricsF(self._f_detail)
        p.drawText(QRectF(card.left() + 20, card.top() + 148, card.width() - 40, 26), Qt.AlignmentFlag.AlignCenter,
                   fm.elidedText(alert.detail, Qt.TextElideMode.ElideRight, card.width() - 40))
        p.setFont(self._f_hint)
        p.setPen(T.qc(T.TEXT_FAINT))
        hint = "ENTER / ESC: DISMISS    S: SNOOZE" if alert.snooze else "ENTER / ESC: DISMISS"
        if len(self._queue) > 1:
            hint += f"    ·    +{len(self._queue) - 1} PENDING"
        p.drawText(QRectF(card.left(), card.bottom() - 18, card.width(), 14), Qt.AlignmentFlag.AlignCenter, hint)
