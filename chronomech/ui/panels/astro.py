"""03 · ASTRO — moon phase (with traditional Japanese name) and the sun's 24 h path."""
from __future__ import annotations

import math
from datetime import datetime

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFontMetricsF, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget

from ... import theme as T
from ...core.astro import moon_info, sun_info
from ...core.settings import Settings
from ..widgets import HudPanel


def draw_moon(p: QPainter, c: QPointF, r: float, elongation: float, mirror: bool = False) -> None:
    """Lit limb + elliptical terminator; `elongation` 0 = new, 180 = full."""
    p.save()
    halo = QRadialGradient(c, r * 1.6)
    halo.setColorAt(0.55, T.qc(T.VIOLET, 50))
    halo.setColorAt(1.0, T.qc(T.VIOLET, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(halo)
    p.drawEllipse(c, r * 1.6, r * 1.6)
    p.setBrush(QColor("#18122a"))                      # earthshine side
    p.drawEllipse(c, r, r)
    waxing = elongation < 180.0
    k = math.cos(math.radians(elongation))             # 1 new → −1 full
    lit_right = waxing != mirror
    half = QPainterPath()
    rect = QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r)
    half.moveTo(c.x(), c.y() - r)
    half.arcTo(rect, 90, -180 if lit_right else 180)
    half.closeSubpath()
    term = QPainterPath()
    term.addEllipse(c, r * abs(k), r)
    lit = half.subtracted(term) if k > 0 else half.united(term)
    g = QRadialGradient(c - QPointF(r * 0.3, r * 0.35), r * 1.4)
    g.setColorAt(0.0, QColor("#f7f0ff"))
    g.setColorAt(0.55, QColor("#cdb2ff"))
    g.setColorAt(1.0, QColor("#8a63d6"))
    p.fillPath(lit, g)
    p.save()                                          # a few maria for texture
    p.setClipPath(lit)
    p.setBrush(T.qc("#5e3fa0", 70))
    for dx, dy, rr in ((-0.25, -0.2, 0.22), (0.2, 0.1, 0.16), (-0.05, 0.35, 0.18), (0.32, -0.32, 0.1)):
        p.drawEllipse(c + QPointF(dx * r, dy * r), rr * r, rr * r)
    p.restore()
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(T.qc(T.VIOLET_HI, 90), 1))
    p.drawEllipse(c, r, r)
    p.restore()


class AstroView(QWidget):
    def __init__(self, settings: Settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self.use_24h = True
        self.setMinimumHeight(88)
        self._f_name = T.font(12.5, "semibold", spacing=1.2)
        self._f_jp = T.font(12, "regular")
        self._f_meta = T.font(10, "regular", spacing=0.6)
        self._f_label = T.font(9.5, "semibold", spacing=1.0)
        self._moon = None
        self._sun = None
        self.refresh()

    def refresh(self) -> None:
        now = datetime.now()
        loc = self._settings["location"]
        self._moon = moon_info(now)
        self._sun = sun_info(now.date(), float(loc.get("lat", 0)), float(loc.get("lon", 0)))
        self.update()

    def _hm(self, t: datetime | None) -> str:
        if t is None:
            return "--:--"
        if self.use_24h:
            return t.strftime("%H:%M")
        return f"{t.hour % 12 or 12}:{t.minute:02d}{'a' if t.hour < 12 else 'p'}"

    def paintEvent(self, _event) -> None:
        if self._moon is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        moon, sun = self._moon, self._sun
        loc = self._settings["location"]
        compact = H < 125              # short window: drop the sun trace, keep the numbers
        top_h = H - 18 if compact else H * 0.56
        mr = min(top_h * 0.40, W * 0.13)
        mc = QPointF(mr * 1.25, top_h / 2)
        draw_moon(p, mc, mr, moon.elongation, mirror=float(loc.get("lat", 0)) < 0)
        x = mc.x() + mr * 1.6 + 6
        tw = W - x
        p.setFont(self._f_name)
        p.setPen(QColor(T.TEXT))
        p.drawText(QPointF(x, top_h / 2 - 12), QFontMetricsF(self._f_name).elidedText(
            moon.name, Qt.TextElideMode.ElideRight, tw))
        p.setFont(self._f_jp)
        p.setPen(T.qc(T.VIOLET_HI))
        jp = f"月齢 {moon.age:4.1f}" + (f"  ·  {moon.name_jp}" if moon.name_jp else "")
        p.drawText(QPointF(x, top_h / 2 + 5), jp)
        p.setFont(self._f_meta)
        p.setPen(T.qc(T.TEXT_DIM))
        nxt = (f"FULL IN {moon.days_to_full:.1f}D" if moon.waxing else f"NEW IN {moon.days_to_new:.1f}D")
        p.drawText(QPointF(x, top_h / 2 + 21), f"ILLUM {moon.illumination * 100:4.1f}%   ·   {nxt}")

        if not compact:
            self._paint_sun_trace(p, W, H, top_h + 6, sun, loc)

        p.setFont(self._f_meta)
        p.setPen(T.qc(T.TEXT_DIM))
        if sun.polar:
            text = "MIDNIGHT SUN · 白夜" if sun.polar == "day" else "POLAR NIGHT · 極夜"
            p.drawText(QRectF(0, H - 14, W, 14), Qt.AlignmentFlag.AlignCenter, text)
        else:
            length = (sun.sunset - sun.sunrise).total_seconds() / 60
            p.drawText(QRectF(2, H - 14, W, 14), Qt.AlignmentFlag.AlignLeft, f"▲ {self._hm(sun.sunrise)}")
            p.drawText(QRectF(0, H - 14, W, 14), Qt.AlignmentFlag.AlignCenter,
                       f"DAYLIGHT {int(length // 60)}h{int(length % 60):02d}m")
            p.drawText(QRectF(0, H - 14, W - 2, 14), Qt.AlignmentFlag.AlignRight, f"▼ {self._hm(sun.sunset)}")

    def _paint_sun_trace(self, p: QPainter, W: float, H: float, top: float, sun, loc: dict) -> None:
        """24 h oscilloscope trace of the sun — above the horizon by day, below at night."""
        y0 = top
        plot = QRectF(4, y0 + 12, W - 8, H - y0 - 26)
        horizon = plot.center().y() + plot.height() * 0.12
        amp_up, amp_dn = plot.top() - horizon, plot.bottom() - horizon
        p.setFont(self._f_label)
        p.setPen(T.qc(T.TEXT_DIM))
        p.drawText(QPointF(plot.left(), y0 + 6), "SUN")
        p.setPen(T.qc(T.TEXT_FAINT))
        p.drawText(QRectF(0, y0 - 4, W - 4, 14), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                   f"{loc.get('name', 'LOCATION')}  {abs(float(loc.get('lat', 0))):.1f}°"
                   f"{'N' if float(loc.get('lat', 0)) >= 0 else 'S'}")

        def hours(t: datetime) -> float:
            return t.hour + t.minute / 60 + t.second / 3600

        if sun.sunrise and sun.sunset:
            rise, sett = hours(sun.sunrise), hours(sun.sunset)
            if sett < rise:
                sett += 24
        else:
            rise, sett = (0.0, 24.0) if sun.polar == "day" else (12.0, 12.0)

        def alt(h: float) -> float:
            day_len = sett - rise
            hh = h if h >= rise else h + 24
            if day_len > 0 and rise <= hh <= sett:
                return math.sin(math.pi * (hh - rise) / day_len)
            night = 24 - day_len
            return -math.sin(math.pi * ((hh - sett) % 24) / night) if night > 0 else 0.0

        def pt(h: float) -> QPointF:
            a = alt(h)
            y = horizon + (a * amp_up if a >= 0 else -a * amp_dn)
            return QPointF(plot.left() + plot.width() * h / 24, y)

        p.setPen(QPen(T.qc(T.LINE_HI), 1))
        p.drawLine(QPointF(plot.left(), horizon), QPointF(plot.right(), horizon))
        for hh in range(0, 25, 6):
            x = plot.left() + plot.width() * hh / 24
            p.drawLine(QPointF(x, horizon - 2), QPointF(x, horizon + 2))
        day_path, night_path = QPainterPath(), QPainterPath()
        steps = 96
        prev_day = None
        for i in range(steps + 1):
            h = 24 * i / steps
            q = pt(h)
            is_day = alt(h) >= 0
            target = day_path if is_day else night_path
            if prev_day is None or is_day != prev_day:
                target.moveTo(q)
            else:
                target.lineTo(q)
            prev_day = is_day
        p.strokePath(night_path, QPen(T.qc(T.VIOLET_LO, 150), 1.2, Qt.PenStyle.DashLine))
        T.glow_stroke(p, day_path, T.qc(T.VIOLET_HI, 220), width=1.4, radius=4)
        now = datetime.now()
        q = pt(hours(now))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(T.qc("#ffd9ff", 60))
        p.drawEllipse(q, 7, 7)
        p.setBrush(QColor("#fff4ff") if alt(hours(now)) >= 0 else T.qc(T.VIOLET_LO))
        p.drawEllipse(q, 3.5, 3.5)


class AstroPanel(HudPanel):
    def __init__(self, settings: Settings, parent: QWidget | None = None) -> None:
        super().__init__("03", "ASTRO", "月相・日照", parent)
        self.view = AstroView(settings, self)
        self.body.addWidget(self.view)

    def refresh(self) -> None:
        self.view.refresh()
