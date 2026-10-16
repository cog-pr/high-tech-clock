"""01 · WORLD TIME — configurable list of time zones with a 24 h day/night strip."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFontMetricsF, QPainter, QPen
from PySide6.QtWidgets import QMenu, QWidget

from ... import theme as T
from ...core.cities import zone
from ...core.settings import Settings
from ..widgets import HudPanel, IconButton, elide_px


def fmt_offset(offset: timedelta | None) -> str:
    if offset is None:
        return "UTC"
    minutes = int(offset.total_seconds() // 60)
    sign = "+" if minutes >= 0 else "−"
    h, m = divmod(abs(minutes), 60)
    return f"UTC{sign}{h:02d}:{m:02d}"


class WorldClockView(QWidget):
    changed = Signal()

    def __init__(self, settings: Settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._hover = -1
        self._scroll = 0.0
        self.use_24h = True
        self.setMouseTracking(True)
        self.setMinimumHeight(60)
        self._f_city = T.font(12.5, "semibold", spacing=1.4)
        self._f_meta = T.font(10, "regular", spacing=0.6)
        self._f_time = T.font(21, "semilight")
        self._f_sec = T.font(12, "regular")
        self._f_tag = T.font(9.5, "semibold", spacing=0.8)

    @property
    def entries(self) -> list[dict]:
        return self._settings["world_clocks"]

    def _row_h(self) -> float:
        n = max(1, len(self.entries))
        return max(32.0, min(50.0, self.height() / n))

    def _max_scroll(self) -> float:
        return max(0.0, len(self.entries) * self._row_h() - self.height())

    def wheelEvent(self, event) -> None:
        self._scroll = max(0.0, min(self._max_scroll(), self._scroll - event.angleDelta().y() / 3))
        self.update()

    def mouseMoveEvent(self, event) -> None:
        row = int((event.position().y() + self._scroll) // self._row_h())
        row = row if 0 <= row < len(self.entries) else -1
        if row != self._hover:
            self._hover = row
            self.update()

    def leaveEvent(self, _event) -> None:
        self._hover = -1
        self.update()

    def contextMenuEvent(self, event) -> None:
        row = int((event.pos().y() + self._scroll) // self._row_h())
        if not 0 <= row < len(self.entries):
            return
        menu = QMenu(self)
        up = menu.addAction("▲  上へ移動 / MOVE UP")
        down = menu.addAction("▼  下へ移動 / MOVE DOWN")
        menu.addSeparator()
        remove = menu.addAction("✕  削除 / REMOVE")
        up.setEnabled(row > 0)
        down.setEnabled(row < len(self.entries) - 1)
        chosen = menu.exec(event.globalPos())
        items = self.entries
        if chosen is remove:
            items.pop(row)
        elif chosen is up:
            items[row - 1], items[row] = items[row], items[row - 1]
        elif chosen is down:
            items[row + 1], items[row] = items[row], items[row + 1]
        else:
            return
        self._scroll = min(self._scroll, self._max_scroll())
        self.changed.emit()
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        now_utc = datetime.now(timezone.utc)
        local_date = datetime.now().date()
        rh = self._row_h()
        W = self.width()
        fm_city = QFontMetricsF(self._f_city)
        if not self.entries:
            p.setFont(self._f_meta)
            p.setPen(T.qc(T.TEXT_FAINT))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "＋ で都市を追加 / ADD A CITY")
            return
        for i, entry in enumerate(self.entries):
            y = i * rh - self._scroll
            if y + rh < 0 or y > self.height():
                continue
            row = QRectF(0, y, W, rh)
            if i == self._hover:
                p.fillRect(row.adjusted(0, 1, 0, -1), T.qc(T.VIOLET_DEEP, 90))
                p.fillRect(QRectF(0, y + 4, 2, rh - 8), T.qc(T.VIOLET))
            tz = zone(entry.get("tz", ""))
            name = entry.get("name") or entry.get("tz", "?")
            if tz is None:
                p.setFont(self._f_city)
                p.setPen(T.qc(T.ALERT))
                p.drawText(QPointF(8, y + rh / 2 + 4), f"{name}  ·  TZ ERROR")
                continue
            t = now_utc.astimezone(tz)
            days = (t.date() - local_date).days
            hour_frac = (t.hour + t.minute / 60) / 24

            time_w = T.tabular_width("00:00", self._f_time) + T.tabular_width(":00", self._f_sec) + 4
            name_base = y + rh / 2 - 1
            p.setFont(self._f_city)
            p.setPen(QColor(T.TEXT))
            p.drawText(QPointF(8, name_base), elide_px(name, fm_city, W - time_w - 26))
            meta = fmt_offset(t.utcoffset()) + "  ·  " + t.strftime("%a").upper()
            p.setFont(self._f_meta)
            p.setPen(T.qc(T.TEXT_DIM))
            p.drawText(QPointF(8, name_base + 13), meta)
            if days:
                tag = f"{days:+d}D"
                tx = 8 + QFontMetricsF(self._f_meta).horizontalAdvance(meta) + 8
                tr = QRectF(tx, name_base + 3, QFontMetricsF(self._f_tag).horizontalAdvance(tag) + 8, 13)
                p.fillPath(T.chamfer_path(tr, 3), T.qc(T.VIOLET_DEEP, 220))
                p.setFont(self._f_tag)
                p.setPen(T.qc(T.VIOLET_HI))
                p.drawText(tr, Qt.AlignmentFlag.AlignCenter, tag)

            hh = t.hour if self.use_24h else (t.hour % 12 or 12)
            hm = f"{hh:02d}:{t.minute:02d}"
            baseline = name_base + 6
            right = W - 6
            sec_w = T.draw_tabular(p, right, baseline, f":{t.second:02d}", self._f_sec, T.TEXT_DIM,
                                   Qt.AlignmentFlag.AlignRight)
            day_time = 6 <= t.hour < 18
            T.draw_tabular(p, right - sec_w - 2, baseline, hm, self._f_time,
                           T.TEXT if day_time else T.VIOLET_HI, Qt.AlignmentFlag.AlignRight)
            if not self.use_24h:
                p.setFont(self._f_tag)
                p.setPen(T.qc(T.TEXT_DIM))
                p.drawText(QPointF(right - sec_w + 2, baseline - 12), "AM" if t.hour < 12 else "PM")

            # 24-hour strip under the time: night is shaded, the marker is that city's hour
            sy = y + rh - 5
            x0, x1 = right - time_w, right
            p.setPen(Qt.PenStyle.NoPen)
            p.fillRect(QRectF(x0, sy, x1 - x0, 2), T.qc(T.LINE))
            p.fillRect(QRectF(x0, sy, (x1 - x0) * 0.25, 2), T.qc(T.VIOLET_DEEP))
            p.fillRect(QRectF(x0 + (x1 - x0) * 0.75, sy, (x1 - x0) * 0.25, 2), T.qc(T.VIOLET_DEEP))
            p.fillRect(QRectF(x0 + (x1 - x0) * 0.25, sy, (x1 - x0) * 0.5, 2), T.qc(T.LINE_HI))
            mx = x0 + (x1 - x0) * hour_frac
            p.setBrush(T.qc(T.VIOLET, 80))
            p.drawEllipse(QPointF(mx, sy + 1), 4, 4)
            p.setBrush(T.qc(T.VIOLET_HI))
            p.drawEllipse(QPointF(mx, sy + 1), 2, 2)
            if i < len(self.entries) - 1:
                p.setPen(QPen(T.qc(T.LINE, 120), 1, Qt.PenStyle.DotLine))
                p.drawLine(QPointF(0, y + rh - 0.5), QPointF(W, y + rh - 0.5))


class WorldClockPanel(HudPanel):
    add_requested = Signal()

    def __init__(self, settings: Settings, parent: QWidget | None = None) -> None:
        super().__init__("01", "WORLD TIME", "世界時計", parent)
        self.view = WorldClockView(settings, self)
        self.body.addWidget(self.view)
        add = IconButton("plus", tooltip="都市を追加 / Add city", size=22)
        add.clicked.connect(self.add_requested)
        self.add_tool(add)
        self.view.changed.connect(settings.save)

    def refresh(self) -> None:
        self.view.update()
