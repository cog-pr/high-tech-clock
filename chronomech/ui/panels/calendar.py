"""02 · CALENDAR — month grid with ISO week numbers; wheel or arrows to navigate."""
from __future__ import annotations

import calendar
from datetime import date, timedelta

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from ... import theme as T
from ..widgets import HudPanel, IconButton, MechButton

MONTHS = ["JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE", "JULY", "AUGUST",
          "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER"]
WEEKDAYS = ["SU", "MO", "TU", "WE", "TH", "FR", "SA"]   # Sunday first, as on Japanese calendars


class CalendarView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._today = date.today()
        self._view = self._today.replace(day=1)
        self.setMinimumHeight(118)
        self._f_month = T.font(15, "semibold", spacing=2.0)
        self._f_year = T.font(11, "regular", spacing=1.2)
        self._f_head = T.font(9.5, "semibold", spacing=1.0)
        self._f_week = T.font(9, "regular", mono=True)
        self._day_fonts: tuple[float, object, object] | None = None

    def _fonts_for(self, row_h: float):
        px = max(9.0, min(12.5, row_h * 0.62))
        if self._day_fonts is None or self._day_fonts[0] != px:
            self._day_fonts = (px, T.font(px, "regular"), T.font(px, "bold"))
        return self._day_fonts[1], self._day_fonts[2]

    def set_today(self, today: date) -> None:
        if today != self._today:
            if self._view == self._today.replace(day=1):
                self._view = today.replace(day=1)
            self._today = today
            self.update()

    def shift(self, months: int) -> None:
        y, m = divmod(self._view.year * 12 + self._view.month - 1 + months, 12)
        self._view = date(y, m + 1, 1)
        self.update()

    def go_today(self) -> None:
        self._view = self._today.replace(day=1)
        self.update()

    def wheelEvent(self, event) -> None:
        self.shift(-1 if event.angleDelta().y() > 0 else 1)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        v = self._view
        p.setFont(self._f_month)
        p.setPen(QColor(T.TEXT))
        p.drawText(QPointF(2, 16), MONTHS[v.month - 1])
        p.setFont(self._f_year)
        p.setPen(T.qc(T.TEXT_DIM))
        p.drawText(QRectF(0, 2, W - 2, 18), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                   f"{v.year}  ·  {v.month:02d}月")

        top = 26.0 if H >= 150 else 22.0
        week_col = 24.0
        cw = (W - week_col) / 7
        head_h = 16.0 if H >= 150 else 13.0
        rh = (H - top - head_h) / 6
        f_day, f_day_b = self._fonts_for(rh)
        p.setFont(self._f_head)
        for i, wd in enumerate(WEEKDAYS):
            color = T.qc(T.ALERT, 200) if i == 0 else (T.qc("#9ab0ff", 220) if i == 6 else T.qc(T.TEXT_DIM))
            p.setPen(color)
            p.drawText(QRectF(week_col + i * cw, top, cw, head_h), Qt.AlignmentFlag.AlignCenter, wd)
        p.setPen(T.qc(T.TEXT_FAINT))
        p.drawText(QRectF(0, top, week_col, head_h), Qt.AlignmentFlag.AlignCenter, "W")
        p.setPen(QPen(T.qc(T.LINE), 1))
        p.drawLine(QPointF(0, top + head_h), QPointF(W, top + head_h))

        first = v - timedelta(days=(v.weekday() + 1) % 7)      # the Sunday on/before the 1st
        for row in range(6):
            y = top + head_h + row * rh
            monday = first + timedelta(days=row * 7 + 1)
            p.setFont(self._f_week)
            p.setPen(T.qc(T.TEXT_FAINT))
            p.drawText(QRectF(0, y, week_col, rh), Qt.AlignmentFlag.AlignCenter, f"{monday.isocalendar()[1]:02d}")
            for col in range(7):
                d = first + timedelta(days=row * 7 + col)
                cell = QRectF(week_col + col * cw, y, cw, rh)
                in_month = d.month == v.month
                if d == self._today:
                    box = cell.adjusted(2, 1.5, -2, -1.5)
                    path = T.chamfer_path(box, 4)
                    p.fillPath(path, T.qc(T.VIOLET, 60))
                    p.strokePath(path, QPen(T.qc(T.VIOLET, 90), 4))
                    p.fillPath(path, T.qc("#5a2fa8"))
                    p.strokePath(path, QPen(T.qc(T.VIOLET_HI), 1))
                    p.setFont(f_day_b)
                    p.setPen(QColor("#ffffff"))
                else:
                    p.setFont(f_day)
                    if not in_month:
                        p.setPen(T.qc(T.TEXT_FAINT, 120))
                    elif col == 0:
                        p.setPen(T.qc(T.ALERT, 210))
                    elif col == 6:
                        p.setPen(T.qc("#9ab0ff", 230))
                    else:
                        p.setPen(QColor(T.TEXT))
                p.drawText(cell, Qt.AlignmentFlag.AlignCenter, str(d.day))
        days_in = calendar.monthrange(v.year, v.month)[1]
        if v == self._today.replace(day=1):
            done = self._today.day / days_in
            p.fillRect(QRectF(0, H - 2, W, 2), T.qc(T.LINE))
            p.fillRect(QRectF(0, H - 2, W * done, 2), T.qc(T.VIOLET))


class CalendarPanel(HudPanel):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("02", "CALENDAR", "カレンダー", parent)
        self.view = CalendarView(self)
        self.body.addWidget(self.view)
        prev = IconButton("left", size=22, tooltip="前の月 / Previous month")
        today = MechButton("TODAY", height=22, font_px=9.5)
        today.setToolTip("今月に戻る / Back to this month")
        nxt = IconButton("right", size=22, tooltip="次の月 / Next month")
        prev.clicked.connect(lambda: self.view.shift(-1))
        nxt.clicked.connect(lambda: self.view.shift(1))
        today.clicked.connect(self.view.go_today)
        for w in (prev, today, nxt):
            self.add_tool(w)
