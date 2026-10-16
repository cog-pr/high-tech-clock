"""06 · ALARM — repeating / one-shot alarms with per-weekday selection."""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QFontMetricsF, QPainter, QPen
from PySide6.QtWidgets import QMenu, QWidget

from ... import theme as T
from ...core.alarms import AlarmManager
from ..widgets import HudPanel, IconButton, paint_switch

DAY_ORDER = [6, 0, 1, 2, 3, 4, 5]           # display Sunday first; values are Python weekdays
DAY_LETTERS = ["S", "M", "T", "W", "T", "F", "S"]


def describe_days(days: list[int]) -> str:
    s = set(days)
    if not s:
        return "ONCE"
    if s == set(range(7)):
        return "EVERY DAY"
    if s == {0, 1, 2, 3, 4}:
        return "WEEKDAYS"
    if s == {5, 6}:
        return "WEEKENDS"
    return ""


class AlarmView(QWidget):
    edit_requested = Signal(object)          # Alarm

    ROW_H = 46.0

    def __init__(self, manager: AlarmManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._m = manager
        self._hover = -1
        self._scroll = 0.0
        self.use_24h = True
        self.setMouseTracking(True)
        self.setMinimumHeight(60)
        self._f_time = T.font(22, "semilight")
        self._f_ampm = T.font(10, "semibold")
        self._f_label = T.font(10.5, "regular")
        self._f_day = T.font(9, "semibold")
        self._f_next = T.font(10, "semibold", spacing=1.0)
        manager.changed.connect(self.update)

    def _list_h(self) -> float:
        return self.height() - 18

    def _row_at(self, y: float) -> int:
        if y > self._list_h():
            return -1
        i = int((y + self._scroll) // self.ROW_H)
        return i if 0 <= i < len(self._m.alarms) else -1

    def _switch_rect(self, i: int) -> QRectF:
        y = i * self.ROW_H - self._scroll
        return QRectF(self.width() - 46, y + self.ROW_H / 2 - 9, 42, 18)

    def wheelEvent(self, event) -> None:
        limit = max(0.0, len(self._m.alarms) * self.ROW_H - self._list_h())
        self._scroll = max(0.0, min(limit, self._scroll - event.angleDelta().y() / 3))
        self.update()

    def mouseMoveEvent(self, event) -> None:
        row = self._row_at(event.position().y())
        if row != self._hover:
            self._hover = row
            self.update()
        over_switch = row >= 0 and self._switch_rect(row).contains(event.position())
        self.setCursor(Qt.CursorShape.PointingHandCursor if row >= 0 and over_switch else Qt.CursorShape.ArrowCursor)

    def leaveEvent(self, _event) -> None:
        self._hover = -1
        self.update()

    def mousePressEvent(self, event) -> None:
        row = self._row_at(event.position().y())
        if row >= 0 and event.button() == Qt.MouseButton.LeftButton:
            alarm = self._m.alarms[row]
            if self._switch_rect(row).adjusted(-6, -8, 4, 8).contains(event.position()):
                self._m.set_enabled(alarm.id, not alarm.enabled)

    def mouseDoubleClickEvent(self, event) -> None:
        row = self._row_at(event.position().y())
        if row >= 0 and not self._switch_rect(row).adjusted(-6, -8, 4, 8).contains(event.position()):
            self.edit_requested.emit(self._m.alarms[row])

    def contextMenuEvent(self, event) -> None:
        row = self._row_at(event.pos().y())
        if row < 0:
            return
        alarm = self._m.alarms[row]
        menu = QMenu(self)
        edit = menu.addAction("✎  編集 / EDIT")
        toggle = menu.addAction("◉  無効化 / DISABLE" if alarm.enabled else "◉  有効化 / ENABLE")
        menu.addSeparator()
        delete = menu.addAction("✕  削除 / DELETE")
        chosen = menu.exec(event.globalPos())
        if chosen is edit:
            self.edit_requested.emit(alarm)
        elif chosen is toggle:
            self._m.set_enabled(alarm.id, not alarm.enabled)
        elif chosen is delete:
            self._m.remove(alarm.id)

    def _fmt(self, hour: int, minute: int) -> tuple[str, str]:
        if self.use_24h:
            return f"{hour:02d}:{minute:02d}", ""
        return f"{hour % 12 or 12:02d}:{minute:02d}", ("AM" if hour < 12 else "PM")

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W = self.width()
        alarms = self._m.alarms
        lh = self._list_h()
        if not alarms:
            p.setFont(self._f_label)
            p.setPen(T.qc(T.TEXT_FAINT))
            p.drawText(QRectF(0, 0, W, lh), Qt.AlignmentFlag.AlignCenter, "NO ALARMS  ·  ＋ で追加")
        p.save()
        p.setClipRect(QRectF(0, 0, W, lh))
        for i, alarm in enumerate(alarms):
            y = i * self.ROW_H - self._scroll
            if y + self.ROW_H < 0 or y > lh:
                continue
            on = alarm.enabled
            if i == self._hover:
                p.fillRect(QRectF(0, y + 1, W, self.ROW_H - 2), T.qc(T.VIOLET_DEEP, 90))
                p.fillRect(QRectF(0, y + 5, 2, self.ROW_H - 10), T.qc(T.VIOLET))
            text, ampm = self._fmt(alarm.hour, alarm.minute)
            tw = T.draw_tabular(p, 8, y + 27, text, self._f_time, T.TEXT if on else T.TEXT_FAINT)
            if ampm:
                p.setFont(self._f_ampm)
                p.setPen(T.qc(T.TEXT_DIM))
                p.drawText(QPointF(12 + tw, y + 27), ampm)
            label = alarm.label or describe_days(alarm.days) or "ALARM"
            p.setFont(self._f_label)
            p.setPen(T.qc(T.TEXT_DIM if on else T.TEXT_FAINT))
            fm = QFontMetricsF(self._f_label)
            p.drawText(QPointF(9, y + 41), fm.elidedText(label, Qt.TextElideMode.ElideRight, W * 0.42))
            # weekday strip
            dx0 = W * 0.47
            step = min(13.0, (W - 54 - dx0) / 7)
            p.setFont(self._f_day)
            for k, wd in enumerate(DAY_ORDER):
                active = (not alarm.days) or wd in alarm.days
                cx = dx0 + k * step
                if alarm.days and wd in alarm.days:
                    p.setPen(T.qc(T.VIOLET_HI if on else T.TEXT_DIM))
                else:
                    p.setPen(T.qc(T.TEXT_FAINT, 140 if active else 110))
                p.drawText(QRectF(cx, y + 14, step, 14), Qt.AlignmentFlag.AlignCenter, DAY_LETTERS[k])
                if alarm.days and wd in alarm.days and on:
                    p.fillRect(QRectF(cx + step / 2 - 3, y + 29, 6, 2), T.qc(T.VIOLET))
            paint_switch(p, self._switch_rect(i), 1.0 if on else 0.0, i == self._hover)
            if i < len(alarms) - 1:
                p.setPen(QPen(T.qc(T.LINE, 120), 1, Qt.PenStyle.DotLine))
                p.drawLine(QPointF(0, y + self.ROW_H - 0.5), QPointF(W, y + self.ROW_H - 0.5))
        p.restore()
        p.setPen(QPen(T.qc(T.LINE), 1))
        p.drawLine(QPointF(0, lh + 1.5), QPointF(W, lh + 1.5))
        nxt = self._m.next_alarm(datetime.now())
        p.setFont(self._f_next)
        if nxt:
            alarm, when = nxt
            delta = when - datetime.now()
            mins = int(delta.total_seconds() // 60) + 1
            h, m = divmod(mins, 60)
            d, h = divmod(h, 24)
            span = (f"{d}D {h}H" if d else (f"{h}H {m:02d}M" if h else f"{m}M"))
            t, ampm = self._fmt(when.hour, when.minute)
            p.setPen(T.qc(T.VIOLET_HI))
            p.drawText(QRectF(0, lh + 3, W, 15), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       f"NEXT ▸ {t}{(' ' + ampm) if ampm else ''}")
            p.setPen(T.qc(T.TEXT_DIM))
            p.drawText(QRectF(0, lh + 3, W, 15), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       f"T−{span}")
        else:
            p.setPen(T.qc(T.TEXT_FAINT))
            p.drawText(QRectF(0, lh + 3, W, 15), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       "NEXT ▸ ——")


class AlarmPanel(HudPanel):
    add_requested = Signal()

    def __init__(self, manager: AlarmManager, parent: QWidget | None = None) -> None:
        super().__init__("06", "ALARM", "アラーム", parent)
        self.view = AlarmView(manager, self)
        self.body.addWidget(self.view)
        add = IconButton("plus", size=22, tooltip="アラームを追加 / Add alarm")
        add.clicked.connect(self.add_requested)
        self.add_tool(add)

    def refresh(self) -> None:
        self.view.update()
