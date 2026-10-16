"""Frameless HUD title bar: drag to move, double-click to maximise, mode toggles."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFontMetricsF, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QWidget

from .. import __version__
from .. import theme as T
from .mechanics import gear_outline
from .widgets import IconButton


class TitleBar(QWidget):
    HEIGHT = 40

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(self.HEIGHT)
        self.status = "SYSTEM ONLINE"
        self.mode = ""
        self._blink = False
        self._f_title = T.font(15, "semibold", condensed=True, spacing=3.2)
        self._f_sub = T.font(10, "regular", spacing=1.6)
        self._f_status = T.font(10, "semibold", spacing=1.6)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 8, 0)
        lay.setSpacing(5)
        lay.addStretch(1)
        self.sound_btn = IconButton("mute", checkable=True, tooltip="秒針の刻み音  [M]")
        self.pin_btn = IconButton("pin", checkable=True, tooltip="常に手前に表示  [P]")
        self.focus_btn = IconButton("focus", checkable=True, tooltip="フォーカスモード (時計のみ)  [F]")
        self.settings_btn = IconButton("gear", tooltip="設定  [Ctrl+,]")
        self.help_btn = IconButton("help", tooltip="ショートカット一覧  [F1]")
        for b in (self.sound_btn, self.pin_btn, self.focus_btn, self.settings_btn, self.help_btn):
            lay.addWidget(b)
        sep = QFrame()
        sep.setFixedSize(1, 20)
        sep.setStyleSheet(f"background: {T.LINE_HI};")
        lay.addSpacing(6)
        lay.addWidget(sep)
        lay.addSpacing(6)
        self.min_btn = IconButton("min", frameless=True, tooltip="最小化")
        self.max_btn = IconButton("max", frameless=True, tooltip="最大化")
        self.close_btn = IconButton("close", frameless=True, danger=True, tooltip="終了")
        for b in (self.min_btn, self.max_btn, self.close_btn):
            lay.addWidget(b)
        self.sound_btn.toggled.connect(lambda on: self.sound_btn.set_icon("sound" if on else "mute"))

    def set_maximized(self, maximized: bool) -> None:
        self.max_btn.set_icon("restore" if maximized else "max")
        self.max_btn.setToolTip("元に戻す" if maximized else "最大化")

    def blink(self) -> None:
        self._blink = not self._blink
        self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.window().windowHandle():
            self.window().windowHandle().startSystemMove()

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            win = self.window()
            if hasattr(win, "toggle_maximized"):
                win.toggle_maximized()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        g = QLinearGradient(0, 0, 0, H)
        g.setColorAt(0.0, QColor("#110d1a"))
        g.setColorAt(1.0, QColor("#09070e"))
        p.fillRect(self.rect(), g)
        # diagonal hazard hatching behind the logo
        p.save()
        p.setClipRect(QRectF(0, 0, 54, H))
        p.setPen(QPen(T.qc(T.VIOLET_DEEP, 160), 5))
        for x in range(-40, 80, 12):
            p.drawLine(QPointF(x, H), QPointF(x + H, 0))
        p.restore()
        p.fillRect(QRectF(0, 0, 54, H), T.qc("#000000", 90))
        # logo: a small glowing gear
        poly = gear_outline(10, 9.5)
        poly.translate(27, H / 2)
        path = QPainterPath()
        path.addPolygon(poly)
        path.closeSubpath()
        path.addEllipse(QPointF(27, H / 2), 3.6, 3.6)
        path.setFillRule(Qt.FillRule.OddEvenFill)
        T.glow_stroke(p, path, T.qc(T.VIOLET, 200), width=1.0, radius=6)
        p.fillPath(path, T.qc(T.VIOLET_HI))
        x = 66.0
        base = H / 2 + 5.5
        p.setFont(self._f_title)
        p.setPen(QColor(T.TEXT))
        p.drawText(QPointF(x, base), "CHRONO-MECH")
        x += QFontMetricsF(self._f_title).horizontalAdvance("CHRONO-MECH") + 6
        p.setFont(self._f_sub)
        p.setPen(T.qc(T.TEXT_DIM))
        sub = f"MK-II  //  MECHANICAL CHRONOMETER SYSTEM  v{__version__}"
        p.drawText(QPointF(x, base - 1), sub)
        sub_end = x + QFontMetricsF(self._f_sub).horizontalAdvance(sub)
        # centred status readout
        status = f"{self.status}   ·   {self.mode}" if self.mode else self.status
        fm = QFontMetricsF(self._f_status)
        sw = fm.horizontalAdvance(status) + 18
        sx = W / 2 - sw / 2
        if sx > sub_end + 24 and sx + sw < W - 300:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(T.qc(T.VIOLET if self._blink else T.VIOLET_LO))
            p.drawEllipse(QPointF(sx + 4, H / 2), 3.2, 3.2)
            p.setFont(self._f_status)
            p.setPen(T.qc(T.VIOLET_HI))
            p.drawText(QPointF(sx + 16, base - 1), status)
            p.setPen(QPen(T.qc(T.LINE_HI), 1))
            p.drawLine(QPointF(sx - 40, H / 2), QPointF(sx - 10, H / 2))
            p.drawLine(QPointF(sx + sw + 8, H / 2), QPointF(sx + sw + 38, H / 2))
        # bottom edge: rail with bright segments
        p.setPen(QPen(T.qc(T.LINE_HI), 1))
        p.drawLine(QPointF(0, H - 0.5), QPointF(W, H - 0.5))
        p.setPen(QPen(T.qc(T.VIOLET), 2))
        p.drawLine(QPointF(0, H - 1), QPointF(54, H - 1))
        p.drawLine(QPointF(W / 2 - 60, H - 1), QPointF(W / 2 + 60, H - 1))
