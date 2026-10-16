"""Shared HUD widget kit: machined panels, buttons, icon buttons, toggles, 7-segment display."""
from __future__ import annotations

import math

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, QSize, Qt, QVariantAnimation
from PySide6.QtGui import QColor, QFontMetricsF, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import QAbstractButton, QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget

from .. import theme as T
from .mechanics import gear_outline


# ── panel frame ──────────────────────────────────────────────────────────────
class HudPanel(QWidget):
    """A machined plate: chamfered frame, neon corner brackets, header strip, screws."""

    HEADER = 30

    def __init__(self, index: str, title: str, subtitle: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._index, self._title, self._subtitle = index, title, subtitle
        self._status, self._status_color = "", T.VIOLET_HI
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 4, 12, 10)
        root.setSpacing(6)
        header = QWidget(self)
        header.setFixedHeight(self.HEADER)
        self._tools = QHBoxLayout(header)
        self._tools.setContentsMargins(0, 0, 4, 0)
        self._tools.setSpacing(4)
        self._tools.addStretch(1)
        root.addWidget(header)
        self.body = QVBoxLayout()
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(6)
        root.addLayout(self.body, 1)
        self._f_index = T.font(10, "semibold", mono=True)
        self._f_title = T.font(13, "semibold", spacing=2.2)
        self._f_sub = T.font(11, "regular")
        self._f_status = T.font(10, "semibold", spacing=1.5)

    def add_tool(self, widget: QWidget) -> None:
        self._tools.addWidget(widget)

    def set_status(self, text: str, color: str | None = None) -> None:
        self._status, self._status_color = text, color or T.VIOLET_HI
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        c = 12.0
        frame = T.chamfer_path(r, c)
        g = QLinearGradient(0, 0, 0, r.height())
        g.setColorAt(0.0, T.qc(T.PANEL_TOP, 242))
        g.setColorAt(1.0, T.qc(T.PANEL_BOTTOM, 242))
        p.fillPath(frame, g)
        hy = r.top() + self.HEADER + 5
        p.save()
        p.setClipPath(frame)
        band = QLinearGradient(r.left(), 0, r.right(), 0)
        band.setColorAt(0.0, T.qc(T.VIOLET_DEEP, 130))
        band.setColorAt(0.55, T.qc(T.VIOLET_DEEP, 25))
        band.setColorAt(1.0, T.qc(T.VIOLET_DEEP, 0))
        p.fillRect(QRectF(r.left(), r.top(), r.width(), hy - r.top()), band)
        p.restore()
        p.strokePath(frame, QPen(T.qc(T.LINE), 1.0))

        accent = QPen(T.qc(T.VIOLET), 1.6)
        accent.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        p.setPen(accent)
        p.setBrush(Qt.BrushStyle.NoBrush)
        tl = QPainterPath(QPointF(r.left(), r.top() + c + 18))
        tl.lineTo(r.left(), r.top() + c)
        tl.lineTo(r.left() + c, r.top())
        tl.lineTo(r.left() + c + 34, r.top())
        p.drawPath(tl)
        br = QPainterPath(QPointF(r.right(), r.bottom() - c - 18))
        br.lineTo(r.right(), r.bottom() - c)
        br.lineTo(r.right() - c, r.bottom())
        br.lineTo(r.right() - c - 34, r.bottom())
        p.drawPath(br)

        p.setPen(QPen(T.qc(T.LINE), 1.0))
        p.drawLine(QPointF(r.left() + 12, hy), QPointF(r.right() - 12, hy))
        p.setPen(QPen(T.qc(T.VIOLET), 2.0))
        p.drawLine(QPointF(r.left() + 12, hy), QPointF(r.left() + 42, hy))
        p.setPen(Qt.PenStyle.NoPen)
        for i in range(3):
            p.setBrush(T.qc(T.VIOLET_LO if i else T.VIOLET, 220 - i * 60))
            p.drawRect(QRectF(r.right() - 16 - i * 6, hy - 1.5, 3, 3))

        base = r.top() + 4 + self.HEADER / 2 + 5
        x = r.left() + 16
        p.setFont(self._f_index)
        p.setPen(T.qc(T.VIOLET))
        p.drawText(QPointF(x, base), self._index)
        x += QFontMetricsF(self._f_index).horizontalAdvance(self._index) + 9
        p.setFont(self._f_title)
        p.setPen(QColor(T.TEXT))
        p.drawText(QPointF(x, base), self._title)
        x += QFontMetricsF(self._f_title).horizontalAdvance(self._title) + 6
        tools_left = r.right() - 16 - self._tools.sizeHint().width()
        status_w = QFontMetricsF(self._f_status).horizontalAdvance(self._status) + 10 if self._status else 0
        sub_w = QFontMetricsF(self._f_sub).horizontalAdvance(self._subtitle)
        if self._subtitle and x + sub_w < tools_left - status_w - 6:     # drop it when space is short
            p.setFont(self._f_sub)
            p.setPen(T.qc(T.TEXT_DIM))
            p.drawText(QPointF(x, base - 0.5), self._subtitle)
        if self._status:
            p.setFont(self._f_status)
            p.setPen(QColor(self._status_color))
            p.drawText(QPointF(tools_left - status_w + 8, base - 1), self._status)
        T.draw_screw(p, QPointF(r.right() - 6.5, r.top() + 6.5), 2.5, 0.9)
        T.draw_screw(p, QPointF(r.left() + 6.5, r.bottom() - 6.5), 2.5, 2.1)


# ── buttons ──────────────────────────────────────────────────────────────────
class _HoverButton(QAbstractButton):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._hover = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def enterEvent(self, event) -> None:
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover = False
        self.update()
        super().leaveEvent(event)


class MechButton(_HoverButton):
    """Chamfered push button; checkable buttons light up like an engaged switch."""

    def __init__(self, text: str = "", parent: QWidget | None = None, *, checkable: bool = False,
                 accent: bool = False, height: int = 28, min_width: int = 0, font_px: float = 11.5) -> None:
        super().__init__(parent)
        self.setText(text)
        self.setCheckable(checkable)
        self._accent = accent
        self._h = height
        self._min_w = min_width
        self._font = T.font(font_px, "semibold", spacing=1.6)
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)

    def set_accent(self, accent: bool) -> None:
        self._accent = accent
        self.update()

    def sizeHint(self) -> QSize:
        w = QFontMetricsF(self._font).horizontalAdvance(self.text())
        return QSize(max(self._min_w, int(w + 26)), self._h)

    def minimumSizeHint(self) -> QSize:
        w = QFontMetricsF(self._font).horizontalAdvance(self.text())
        return QSize(int(w + 12), self._h)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        c = min(7.0, r.height() * 0.28)
        path = T.chamfer_path(r, c)
        on = self.isChecked() or self.isDown()
        hover = self._hover and self.isEnabled()
        g = QLinearGradient(0, r.top(), 0, r.bottom())
        if not self.isEnabled():
            g.setColorAt(0, T.qc(T.METAL_1, 150))
            g.setColorAt(1, T.qc(T.METAL_0, 150))
            border, text = T.qc(T.LINE), T.qc(T.TEXT_FAINT)
        elif on:
            g.setColorAt(0, T.qc("#6a3fb5"))
            g.setColorAt(1, T.qc("#38196e"))
            border, text = T.qc(T.VIOLET_HI), QColor("#ffffff")
        else:
            g.setColorAt(0, T.qc("#1a1426" if hover else "#15111f"))
            g.setColorAt(1, T.qc("#100c18" if hover else "#0c0a13"))
            border = T.qc(T.VIOLET if hover else (T.VIOLET_LO if self._accent else T.LINE_HI))
            text = T.qc(T.VIOLET_HI if (hover or self._accent) else T.TEXT)
        p.fillPath(path, g)
        if (hover or on) and self.isEnabled():
            p.strokePath(path, QPen(T.qc(T.VIOLET, 70), 3.0))
        p.strokePath(path, QPen(border, 1.0))
        p.setPen(QPen(T.qc(T.VIOLET_HI, 230 if (hover or on) else 110), 1.4))
        p.drawLine(QPointF(r.left() + 1, r.top() + c), QPointF(r.left() + c, r.top() + 1))
        p.setFont(self._font)
        p.setPen(text)
        p.drawText(r.adjusted(self._font.letterSpacing() / 2, 0, 0, 0), Qt.AlignmentFlag.AlignCenter, self.text())


def draw_icon(p: QPainter, name: str, r: QRectF, color: QColor | str, width: float = 1.4) -> None:
    """Tiny vector icon set so the UI needs no image assets."""
    p.save()
    pen = QPen(QColor(color), width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    cx, cy = r.center().x(), r.center().y()
    s = min(r.width(), r.height()) / 2

    def pt(x: float, y: float) -> QPointF:
        return QPointF(cx + x * s, cy + y * s)

    if name == "close":
        p.drawLine(pt(-0.55, -0.55), pt(0.55, 0.55))
        p.drawLine(pt(0.55, -0.55), pt(-0.55, 0.55))
    elif name == "min":
        p.drawLine(pt(-0.6, 0.15), pt(0.6, 0.15))
    elif name == "max":
        p.drawRect(QRectF(cx - 0.55 * s, cy - 0.55 * s, 1.1 * s, 1.1 * s))
    elif name == "restore":
        p.drawRect(QRectF(cx - 0.6 * s, cy - 0.3 * s, 0.9 * s, 0.9 * s))
        p.drawPolyline(QPolygonF([pt(-0.3, -0.3), pt(-0.3, -0.6), pt(0.6, -0.6), pt(0.6, 0.3), pt(0.3, 0.3)]))
    elif name in ("plus", "minus"):
        p.drawLine(pt(-0.6, 0), pt(0.6, 0))
        if name == "plus":
            p.drawLine(pt(0, -0.6), pt(0, 0.6))
    elif name in ("left", "right"):
        k = -1 if name == "left" else 1
        p.drawPolyline(QPolygonF([pt(-0.25 * k, -0.55), pt(0.3 * k, 0), pt(-0.25 * k, 0.55)]))
    elif name == "pin":
        p.drawPolygon(QPolygonF([pt(-0.35, -0.75), pt(0.35, -0.75), pt(0.25, -0.15), pt(-0.25, -0.15)]))
        p.drawLine(pt(-0.6, -0.15), pt(0.6, -0.15))
        p.drawLine(pt(0, -0.15), pt(0, 0.8))
    elif name in ("sound", "mute"):
        p.drawPolygon(QPolygonF([pt(-0.75, -0.25), pt(-0.4, -0.25), pt(0.0, -0.6), pt(0.0, 0.6),
                                 pt(-0.4, 0.25), pt(-0.75, 0.25)]))
        if name == "sound":
            for rr in (0.35, 0.65):
                p.drawArc(QRectF(cx - rr * s, cy - rr * s, 2 * rr * s, 2 * rr * s), -50 * 16, 100 * 16)
        else:
            p.drawLine(pt(0.25, -0.3), pt(0.75, 0.3))
            p.drawLine(pt(0.75, -0.3), pt(0.25, 0.3))
    elif name == "focus":
        for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            p.drawPolyline(QPolygonF([pt(0.7 * sx, 0.25 * sy), pt(0.7 * sx, 0.7 * sy), pt(0.25 * sx, 0.7 * sy)]))
        p.drawEllipse(pt(0, 0), 0.12 * s, 0.12 * s)
    elif name == "gear":
        poly = gear_outline(8, 0.55 * s)
        poly.translate(cx, cy)
        p.drawPolygon(poly)
        p.drawEllipse(pt(0, 0), 0.22 * s, 0.22 * s)
    elif name == "help":
        path = QPainterPath(pt(-0.35, -0.35))
        path.cubicTo(pt(-0.35, -0.85), pt(0.45, -0.85), pt(0.4, -0.35))
        path.cubicTo(pt(0.38, -0.05), pt(0.0, -0.05), pt(0.0, 0.25))
        p.drawPath(path)
        p.drawPoint(pt(0, 0.62))
    elif name == "edit":
        p.drawPolygon(QPolygonF([pt(-0.6, 0.6), pt(-0.5, 0.25), pt(0.3, -0.55), pt(0.55, -0.3),
                                 pt(-0.25, 0.5)]))
    elif name == "trash":
        p.drawLine(pt(-0.65, -0.45), pt(0.65, -0.45))
        p.drawPolyline(QPolygonF([pt(-0.2, -0.45), pt(-0.2, -0.7), pt(0.2, -0.7), pt(0.2, -0.45)]))
        p.drawPolygon(QPolygonF([pt(-0.5, -0.45), pt(-0.4, 0.7), pt(0.4, 0.7), pt(0.5, -0.45)]))
    p.restore()


class IconButton(_HoverButton):
    def __init__(self, icon: str, parent: QWidget | None = None, *, size: int = 26, checkable: bool = False,
                 tooltip: str = "", danger: bool = False, frameless: bool = False) -> None:
        super().__init__(parent)
        self._icon = icon
        self._danger = danger
        self._frameless = frameless
        self.setCheckable(checkable)
        self.setFixedSize(size, size)
        if tooltip:
            self.setToolTip(tooltip)

    def set_icon(self, icon: str) -> None:
        self._icon = icon
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = T.chamfer_path(r, 5.0)
        on = self.isChecked() or self.isDown()
        if self._hover and self._danger:
            p.fillPath(path, T.qc("#4a1030", 220))
            p.strokePath(path, QPen(T.qc(T.ALERT), 1.0))
            color = QColor("#ffffff")
        elif on:
            p.fillPath(path, T.qc("#4b2490", 220))
            p.strokePath(path, QPen(T.qc(T.VIOLET_HI), 1.0))
            color = QColor("#ffffff")
        elif self._hover:
            p.fillPath(path, T.qc(T.VIOLET_DEEP, 150))
            p.strokePath(path, QPen(T.qc(T.VIOLET), 1.0))
            color = T.qc(T.VIOLET_HI)
        else:
            if not self._frameless:
                p.fillPath(path, T.qc("#0f0c17", 200))
                p.strokePath(path, QPen(T.qc(T.LINE_HI), 1.0))
            color = T.qc(T.TEXT_DIM if self.isEnabled() else T.TEXT_FAINT)
        inset = r.width() * 0.27
        draw_icon(p, self._icon, r.adjusted(inset, inset, -inset, -inset), color)


class ToggleSwitch(_HoverButton):
    """A sliding mechanical switch."""

    def __init__(self, checked: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setFixedSize(44, 20)
        self._pos = 1.0 if checked else 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(140)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._on_anim)
        self.toggled.connect(self._animate)

    def _animate(self, on: bool) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def _on_anim(self, value) -> None:
        self._pos = float(value)
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        paint_switch(p, QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), self._pos, self._hover)


def paint_switch(p: QPainter, r: QRectF, pos: float, hover: bool = False) -> None:
    track = T.chamfer_path(r, 5.0, tl=True, br=True)
    on = pos > 0.5
    p.fillPath(track, T.mix("#0d0b13", "#2e1660", pos))
    p.strokePath(track, QPen(T.qc(T.VIOLET if (on or hover) else T.LINE_HI), 1.0))
    if on:
        p.strokePath(track, QPen(T.qc(T.VIOLET, 60), 3.0))
    p.setPen(QPen(T.qc("#ffffff", 30), 1.0))
    for i in range(3):                       # grip ridges inside the track
        x = r.left() + 8 + i * 3 if pos > 0.5 else r.right() - 8 - i * 3
        p.drawLine(QPointF(x, r.top() + 6), QPointF(x, r.bottom() - 6))
    kw = r.height() - 6
    kx = r.left() + 3 + (r.width() - 6 - kw) * pos
    knob = T.chamfer_path(QRectF(kx, r.top() + 3, kw, kw), 3.0)
    p.fillPath(knob, T.mix(T.METAL_4, T.VIOLET_HI, pos))
    p.strokePath(knob, QPen(T.qc("#08070c", 200), 0.8))


# ── 7-segment display ────────────────────────────────────────────────────────
_SEG_CHARS = {
    "0": "abcdef", "1": "bc", "2": "abdeg", "3": "abcdg", "4": "bcfg", "5": "acdfg",
    "6": "acdefg", "7": "abc", "8": "abcdefg", "9": "abcdfg", "-": "g", " ": "", "_": "d",
    "A": "abcefg", "B": "cdefg", "C": "adef", "D": "bcdeg", "E": "adefg", "F": "aefg",
    "H": "bcefg", "L": "def", "O": "abcdef", "P": "abefg", "R": "eg", "S": "acdfg",
    "T": "defg", "U": "bcdef", "N": "ceg", "Y": "bcdfg",
}
_T_SEG = 0.22


def _segment_polys() -> dict[str, list[tuple[float, float]]]:
    h, g = _T_SEG / 2, 0.035

    def hseg(y: float):
        return [(g, y), (g + h, y - h), (1 - g - h, y - h), (1 - g, y), (1 - g - h, y + h), (g + h, y + h)]

    def vseg(x: float, y0: float, y1: float):
        return [(x, y0 + g), (x + h, y0 + g + h), (x + h, y1 - g - h), (x, y1 - g),
                (x - h, y1 - g - h), (x - h, y0 + g + h)]

    return {"a": hseg(0), "g": hseg(1), "d": hseg(2), "f": vseg(0, 0, 1), "b": vseg(1, 0, 1),
            "e": vseg(0, 1, 2), "c": vseg(1, 1, 2)}


_SEGMENTS = _segment_polys()


class SegmentDisplay(QWidget):
    """Font-independent seven-segment readout with unlit ghost segments and a neon glow."""

    def __init__(self, text: str = "", parent: QWidget | None = None, *, color: str = T.VIOLET_HI,
                 glow: str = T.VIOLET, skew: float = 0.10,
                 align: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignCenter) -> None:
        super().__init__(parent)
        self._text = text
        self._color, self._glow = color, glow
        self._skew = skew
        self._align = align
        self._dim_tail = 0          # number of trailing chars drawn smaller (e.g. centiseconds)
        self._glyphs: dict[tuple, tuple[QPixmap, float]] = {}
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumHeight(20)

    def setText(self, text: str) -> None:
        if text != self._text:
            self._text = text
            self.update()

    def text(self) -> str:
        return self._text

    def set_colors(self, color: str, glow: str | None = None) -> None:
        self._color, self._glow = color, glow or self._glow
        self.update()

    def set_small_tail(self, count: int) -> None:
        self._dim_tail = count
        self.update()

    @staticmethod
    def _advance(ch: str, u: float) -> float:
        if ch == ":":
            return 0.62 * u
        if ch == ".":
            return 0.5 * u
        return (1 + _T_SEG) * u + 0.42 * u

    def paintEvent(self, _event) -> None:
        if not self._text:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        n_tail = self._dim_tail
        tail_scale = 0.62

        def width_for(u: float) -> float:
            head = self._text[:len(self._text) - n_tail] if n_tail else self._text
            tail = self._text[len(head):]
            return (sum(self._advance(ch, u) for ch in head)
                    + sum(self._advance(ch, u * tail_scale) for ch in tail) - 0.42 * u)

        u = H * 0.86 / (2 + _T_SEG)
        need = width_for(u) + self._skew * H
        if need > W * 0.98:
            u *= W * 0.98 / need
        total = width_for(u)
        if self._align & Qt.AlignmentFlag.AlignLeft:
            x = 2.0
        elif self._align & Qt.AlignmentFlag.AlignRight:
            x = W - total - 2.0 - self._skew * H * 0.5
        else:
            x = (W - total) / 2
        digit_h = (2 + _T_SEG) * u
        top = (H - digit_h) / 2
        mid = top + digit_h / 2
        dpr = self.devicePixelRatioF()
        for i, ch in enumerate(self._text):
            uu = u * tail_scale if n_tail and i >= len(self._text) - n_tail else u
            gh = (2 + _T_SEG) * uu
            base_y = top + digit_h - gh                       # tail digits share the baseline
            pm, margin = self._glyph(ch, uu, u, dpr)
            shift = self._skew * (mid - (base_y + gh))        # the italic slant is about `mid`
            p.drawPixmap(QPointF(x + shift - margin, base_y - margin), pm)
            x += self._advance(ch, uu)

    def _glyph(self, ch: str, uu: float, u: float, dpr: float) -> tuple[QPixmap, float]:
        """One character with its ghost segments and glow, rendered once: stroking the glow on
        every repaint is what made a 30 Hz stopwatch readout expensive."""
        key = (ch, round(uu, 2), round(u, 2), self._color, self._glow, self._skew, dpr)
        hit = self._glyphs.get(key)
        if hit is not None:
            return hit
        if len(self._glyphs) > 96:
            self._glyphs.clear()
        hh = _T_SEG / 2
        gh = (2 + _T_SEG) * uu
        margin = max(2.0, u * 0.55) / 2 + 2
        pm = QPixmap(max(1, math.ceil(((1 + _T_SEG) * uu + self._skew * gh + 2 * margin) * dpr)),
                     max(1, math.ceil((gh + 2 * margin) * dpr)))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.GlobalColor.transparent)

        def mp(px: float, py: float) -> QPointF:
            y = (py + hh) * uu
            return QPointF(margin + (px + hh) * uu + self._skew * (gh - y), margin + y)

        lit, ghost = QPainterPath(), QPainterPath()
        lit.setFillRule(Qt.FillRule.WindingFill)
        if ch == ":":
            for cy in (0.6, 1.4):
                lit.addPolygon(QPolygonF([mp(0.12, cy - 0.12), mp(0.36, cy - 0.12),
                                          mp(0.36, cy + 0.12), mp(0.12, cy + 0.12)]))
                lit.closeSubpath()
        elif ch == ".":
            lit.addPolygon(QPolygonF([mp(0.02, 1.86), mp(0.26, 1.86), mp(0.26, 2.1), mp(0.02, 2.1)]))
            lit.closeSubpath()
        else:
            on = _SEG_CHARS.get(ch.upper(), "")
            for name, pts in _SEGMENTS.items():
                target = lit if name in on else ghost
                target.addPolygon(QPolygonF([mp(px, py) for px, py in pts]))
                target.closeSubpath()
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillPath(ghost, T.qc(T.VIOLET_DEEP, 95))
        p.strokePath(lit, QPen(T.qc(self._glow, 34), max(2.0, u * 0.55)))
        p.strokePath(lit, QPen(T.qc(self._glow, 60), max(1.0, u * 0.22)))
        p.fillPath(lit, QColor(self._color))
        p.end()
        self._glyphs[key] = (pm, margin)
        return pm, margin


def elide_px(text: str, fm: QFontMetricsF, width: float) -> str:
    return fm.elidedText(text, Qt.TextElideMode.ElideRight, max(0.0, width))


def fmt_duration(seconds: float, cs: bool = True) -> str:
    seconds = max(0.0, seconds)
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    if cs:
        return f"{h:02d}:{m:02d}:{s:02d}.{int((seconds - math.floor(seconds)) * 100):02d}"
    return f"{h:02d}:{m:02d}:{s:02d}"
