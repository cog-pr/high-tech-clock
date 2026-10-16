"""Application bootstrap."""
from __future__ import annotations

import sys

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPixmap, QRadialGradient
from PySide6.QtWidgets import QApplication

from . import APP_ID, APP_NAME
from . import theme as T
from .core.settings import Settings, config_dir
from .ui.main_window import MainWindow
from .ui.mechanics import gear_outline


def make_icon() -> QIcon:
    """A violet gear on a black disc, drawn at several sizes."""
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        pm = QPixmap(size, size)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QPointF(size / 2, size / 2)
        bg = QRadialGradient(c, size / 2)
        bg.setColorAt(0.0, QColor("#1b1230"))
        bg.setColorAt(1.0, QColor("#06050a"))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(bg)
        p.drawEllipse(c, size / 2 - 0.5, size / 2 - 0.5)
        gear = QPainterPath()
        gear.setFillRule(Qt.FillRule.OddEvenFill)
        poly = gear_outline(12, size * 0.30)
        poly.translate(c)
        gear.addPolygon(poly)
        gear.closeSubpath()
        gear.addEllipse(c, size * 0.12, size * 0.12)
        if size >= 32:
            T.glow_stroke(p, gear, T.qc(T.VIOLET, 220), width=size / 64, radius=size / 14)
        p.fillPath(gear, QColor(T.VIOLET_HI))
        p.setBrush(QColor(T.VIOLET))
        p.drawEllipse(c, size * 0.05, size * 0.05)
        p.end()
        icon.addPixmap(pm)
    return icon


def _windows_setup() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)   # own taskbar icon
    except Exception:
        pass


def main() -> int:
    _windows_setup()
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("ChronoMech")
    app.setStyle("Fusion")
    app.setPalette(T.dark_palette())
    app.setStyleSheet(T.stylesheet() + T.arrow_stylesheet(config_dir() / "assets"))
    app.setFont(T.font(12))
    app.setWindowIcon(make_icon())
    window = MainWindow(Settings())
    window.show()
    return app.exec()
