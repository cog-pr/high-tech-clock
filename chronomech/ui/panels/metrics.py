"""08 · TIME INDEX — how far through the day/week/month/year we are, plus machine time."""
from __future__ import annotations

import calendar
import time
from datetime import datetime, timedelta, timezone

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFontMetricsF, QPainter
from PySide6.QtWidgets import QWidget

from ... import theme as T
from ..widgets import HudPanel


def progress(now: datetime) -> list[tuple[str, str, float]]:
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = day_start - timedelta(days=now.weekday())
    month_start = day_start.replace(day=1)
    year_start = month_start.replace(month=1)
    month_days = calendar.monthrange(now.year, now.month)[1]
    year_days = 366 if calendar.isleap(now.year) else 365
    secs = (now - day_start).total_seconds()
    return [
        ("DAY", "日", secs / 86400),
        ("WEEK", "週", (now - week_start).total_seconds() / (7 * 86400)),
        ("MONTH", "月", (now - month_start).total_seconds() / (month_days * 86400)),
        ("YEAR", "年", (now - year_start).total_seconds() / (year_days * 86400)),
    ]


class TimeIndexView(QWidget):
    SEGMENTS = 24

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(84)
        self._f_label = T.font(10.5, "semibold", spacing=1.4)
        self._f_pct = T.font(12, "regular")
        self._f_meta = T.font(9.5, "regular", mono=True)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        now = datetime.now()
        rows = progress(now)
        footer = 16.0
        rh = (H - footer) / len(rows)
        label_w, pct_w = 64.0, 60.0
        bar_x, bar_w = label_w, W - label_w - pct_w
        for i, (name, jp, frac) in enumerate(rows):
            y = i * rh
            cy = y + rh / 2
            p.setFont(self._f_label)
            p.setPen(QColor(T.TEXT))
            p.drawText(QPointF(0, cy + 4), name)
            p.setPen(T.qc(T.TEXT_FAINT))
            p.drawText(QPointF(44, cy + 4), jp)
            n = self.SEGMENTS
            gap = 2.0
            sw = (bar_w - gap * (n - 1)) / n
            sh = min(10.0, rh * 0.5)
            filled = frac * n
            for k in range(n):
                cell = QRectF(bar_x + k * (sw + gap), cy - sh / 2, sw, sh)
                level = max(0.0, min(1.0, filled - k))
                p.fillRect(cell, T.qc(T.VIOLET_DEEP, 120))
                if level > 0:
                    lit = QRectF(cell.left(), cell.top(), cell.width() * level, cell.height())
                    p.fillRect(lit, T.mix(T.VIOLET_LO, T.VIOLET_HI, k / n))
            T.draw_tabular(p, W, cy + 5, f"{frac * 100:6.2f}%", self._f_pct, T.VIOLET_HI, Qt.AlignmentFlag.AlignRight)
        utc = datetime.now(timezone.utc)
        beats = ((utc.hour * 3600 + utc.minute * 60 + utc.second + 3600) % 86400) / 86.4   # Swatch .beat
        items = [f"UNIX {int(time.time())}", f"DOY {now.timetuple().tm_yday:03d}",
                 f"ISO W{now.isocalendar()[1]:02d}", f"@{beats:06.2f}"]
        fm = QFontMetricsF(self._f_meta)
        meta = items[0]
        for item in items[1:]:                      # keep whatever fits
            if fm.horizontalAdvance(meta + "   " + item) > W:
                break
            meta += "   " + item
        p.setFont(self._f_meta)
        p.setPen(T.qc(T.TEXT_DIM))
        p.drawText(QRectF(0, H - footer, W, footer), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, meta)


class TimeIndexPanel(HudPanel):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("08", "TIME INDEX", "進捗", parent)
        self.view = TimeIndexView(self)
        self.body.addWidget(self.view)

    def refresh(self) -> None:
        self.view.update()
