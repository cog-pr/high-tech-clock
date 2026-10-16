"""Visual language: colour tokens, fonts, stylesheet and shared painting helpers."""
from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QImage,
    QPainter,
    QPainterPath,
    QPalette,
    QPen,
    QPolygonF,
)

TAU = math.tau

# ── colour tokens ────────────────────────────────────────────────────────────
BG = "#06050a"
BG_GRID = "#0d0a14"
BG_GRID_MAJOR = "#151021"
PANEL_TOP = "#130f1d"
PANEL_BOTTOM = "#0a0810"
LINE = "#2a2040"
LINE_HI = "#45336a"
VIOLET = "#9d5cff"
VIOLET_HI = "#cbaaff"
VIOLET_LO = "#5b3699"
VIOLET_DEEP = "#28154a"
MAGENTA = "#e05cff"
TEXT = "#ece4ff"
TEXT_DIM = "#9283b2"
TEXT_FAINT = "#564a70"
METAL_0 = "#0e0c14"
METAL_1 = "#1a1624"
METAL_2 = "#2a2538"
METAL_3 = "#433b57"
METAL_4 = "#6d6389"
ALERT = "#ff5ca8"


def qc(color: str | QColor, alpha: int | None = None) -> QColor:
    """QColor from a token, optionally with an alpha override (0-255)."""
    c = QColor(color)
    if alpha is not None:
        c.setAlpha(max(0, min(255, int(alpha))))
    return c


def mix(a: str | QColor, b: str | QColor, t: float) -> QColor:
    ca, cb = QColor(a), QColor(b)
    t = max(0.0, min(1.0, t))
    return QColor(
        round(ca.red() + (cb.red() - ca.red()) * t),
        round(ca.green() + (cb.green() - ca.green()) * t),
        round(ca.blue() + (cb.blue() - ca.blue()) * t),
        round(ca.alpha() + (cb.alpha() - ca.alpha()) * t),
    )


# ── fonts ────────────────────────────────────────────────────────────────────
_FALLBACK = ["Segoe UI", "DIN Alternate", "Roboto Condensed", "Helvetica Neue", "Arial"]
_MONO = ["Cascadia Mono", "Consolas", "SF Mono", "Menlo", "DejaVu Sans Mono", "Courier New"]
_CJK = ["Yu Gothic UI", "Meiryo UI", "Hiragino Sans", "Noto Sans CJK JP", "Noto Sans JP"]
_WEIGHTS = {
    "light": (" Light", QFont.Weight.Light),
    "semilight": (" SemiLight", QFont.Weight.Normal),
    "regular": ("", QFont.Weight.Normal),
    "semibold": (" SemiBold", QFont.Weight.DemiBold),
    "bold": ("", QFont.Weight.Bold),
}


def font(px: float, weight: str = "regular", *, condensed: bool = False,
         mono: bool = False, spacing: float = 0.0) -> QFont:
    """Bahnschrift (a DIN-like face shipped with Windows) with graceful fallbacks."""
    suffix, qweight = _WEIGHTS.get(weight, _WEIGHTS["regular"])
    f = QFont()
    if mono:
        families = _MONO + _CJK
    else:
        named = "Bahnschrift" + suffix + (" SemiCondensed" if condensed else "")
        families = [named, "Bahnschrift"] + _FALLBACK + _CJK
    f.setFamilies(families)
    f.setPixelSize(max(1, int(round(px))))
    f.setWeight(qweight)
    if spacing:
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
    f.setHintingPreference(QFont.HintingPreference.PreferVerticalHinting)
    return f


_cell_cache: dict[str, float] = {}


def digit_cell(f: QFont) -> float:
    key = f.key()
    if key not in _cell_cache:
        fm = QFontMetricsF(f)
        _cell_cache[key] = max(fm.horizontalAdvance(d) for d in "0123456789")
    return _cell_cache[key]


def tabular_width(text: str, f: QFont) -> float:
    fm = QFontMetricsF(f)
    cell = digit_cell(f)
    return sum(cell if ch.isdigit() else fm.horizontalAdvance(ch) for ch in text)


def draw_tabular(p: QPainter, x: float, baseline: float, text: str, f: QFont,
                 color: QColor | str, align: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignLeft) -> float:
    """Draw text with fixed-width digits so changing numbers never jitter."""
    fm = QFontMetricsF(f)
    cell = digit_cell(f)
    total = tabular_width(text, f)
    if align & Qt.AlignmentFlag.AlignRight:
        x -= total
    elif align & Qt.AlignmentFlag.AlignHCenter:
        x -= total / 2
    p.setFont(f)
    p.setPen(QColor(color))
    for ch in text:
        if ch.isdigit():
            p.drawText(QPointF(x + (cell - fm.horizontalAdvance(ch)) / 2, baseline), ch)
            x += cell
        else:
            p.drawText(QPointF(x, baseline), ch)
            x += fm.horizontalAdvance(ch)
    return total


# ── painting helpers ─────────────────────────────────────────────────────────
def polar(cx: float, cy: float, r: float, a: float) -> QPointF:
    """Point at angle `a` (radians, screen coordinates: 0 = 3 o'clock, clockwise)."""
    return QPointF(cx + r * math.cos(a), cy + r * math.sin(a))


def clock_angle(fraction: float) -> float:
    """Angle (radians) for a dial fraction where 0 = 12 o'clock, clockwise."""
    return fraction * TAU - math.pi / 2


def chamfer_path(r: QRectF, c: float, *, tl: bool = True, tr: bool = False,
                 br: bool = True, bl: bool = False) -> QPainterPath:
    """Rectangle with 45° cut corners — the basic 'machined plate' shape."""
    x0, y0, x1, y1 = r.left(), r.top(), r.right(), r.bottom()
    path = QPainterPath()
    path.moveTo(x0 + (c if tl else 0), y0)
    if tr:
        path.lineTo(x1 - c, y0)
        path.lineTo(x1, y0 + c)
    else:
        path.lineTo(x1, y0)
    if br:
        path.lineTo(x1, y1 - c)
        path.lineTo(x1 - c, y1)
    else:
        path.lineTo(x1, y1)
    if bl:
        path.lineTo(x0 + c, y1)
        path.lineTo(x0, y1 - c)
    else:
        path.lineTo(x0, y1)
    if tl:
        path.lineTo(x0, y0 + c)
    path.closeSubpath()
    return path


def glow_stroke(p: QPainter, path: QPainterPath, color: QColor | str, width: float = 1.5,
                radius: float = 6.0, strength: float = 1.0, steps: int = 3) -> None:
    """Stroke a path with a soft neon halo underneath."""
    base = QColor(color)
    for i in range(steps, 0, -1):
        halo = QColor(base)
        halo.setAlphaF(min(1.0, base.alphaF() * 0.16 * strength * (steps - i + 1) / steps))
        pen = QPen(halo, width + radius * i / steps)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.strokePath(path, pen)
    pen = QPen(base, width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.strokePath(path, pen)


def draw_screw(p: QPainter, c: QPointF, r: float, angle: float = 0.6) -> None:
    """A small slotted screw head."""
    p.save()
    p.setPen(QPen(qc(METAL_4, 160), max(0.6, r * 0.18)))
    p.setBrush(qc(METAL_2))
    p.drawEllipse(c, r, r)
    p.setPen(QPen(qc(METAL_0), max(0.8, r * 0.32)))
    d = QPointF(math.cos(angle) * r * 0.7, math.sin(angle) * r * 0.7)
    p.drawLine(c - d, c + d)
    p.restore()


# ── application-wide palette & stylesheet ────────────────────────────────────
def dark_palette() -> QPalette:
    pal = QPalette()
    role, group = QPalette.ColorRole, QPalette.ColorGroup
    pal.setColor(role.Window, QColor(BG))
    pal.setColor(role.WindowText, QColor(TEXT))
    pal.setColor(role.Base, QColor("#0b0911"))
    pal.setColor(role.AlternateBase, QColor("#120e1b"))
    pal.setColor(role.Text, QColor(TEXT))
    pal.setColor(role.Button, QColor("#140f1f"))
    pal.setColor(role.ButtonText, QColor(TEXT))
    pal.setColor(role.Highlight, QColor(VIOLET_LO))
    pal.setColor(role.HighlightedText, QColor("#ffffff"))
    pal.setColor(role.ToolTipBase, QColor("#120e1b"))
    pal.setColor(role.ToolTipText, QColor(TEXT))
    pal.setColor(role.PlaceholderText, QColor(TEXT_FAINT))
    pal.setColor(role.Link, QColor(VIOLET_HI))
    pal.setColor(role.BrightText, QColor(ALERT))
    for r in (role.Text, role.WindowText, role.ButtonText):
        pal.setColor(group.Disabled, r, QColor(TEXT_FAINT))
    return pal


def stylesheet() -> str:
    return f"""
    QToolTip {{
        background: #120e1b; color: {TEXT}; border: 1px solid {VIOLET_LO};
        padding: 5px 8px; font-family: "Bahnschrift", "Segoe UI"; font-size: 12px;
    }}
    QMenu {{
        background: #0f0c17; color: {TEXT}; border: 1px solid {LINE_HI}; padding: 4px;
        font-family: "Bahnschrift", "Segoe UI", "Yu Gothic UI"; font-size: 13px;
    }}
    QMenu::item {{ padding: 6px 22px 6px 14px; }}
    QMenu::item:selected {{ background: {VIOLET_DEEP}; color: #ffffff; }}
    QMenu::separator {{ height: 1px; background: {LINE}; margin: 4px 6px; }}
    QLabel {{ color: {TEXT}; background: transparent; }}
    QLineEdit, QComboBox, QTimeEdit, QDoubleSpinBox, QSpinBox {{
        background: #0b0911; color: {TEXT}; border: 1px solid {LINE_HI};
        padding: 5px 8px; selection-background-color: {VIOLET_LO};
        font-family: "Bahnschrift", "Segoe UI", "Yu Gothic UI"; font-size: 14px;
        min-height: 22px;
    }}
    QLineEdit:focus, QComboBox:focus, QTimeEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus {{
        border: 1px solid {VIOLET};
    }}
    QComboBox QAbstractItemView {{
        background: #0f0c17; color: {TEXT}; border: 1px solid {LINE_HI};
        selection-background-color: {VIOLET_DEEP}; outline: none;
    }}
    QSlider::groove:horizontal {{ height: 4px; background: #1c1628; }}
    QSlider::sub-page:horizontal {{ background: {VIOLET}; }}
    QSlider::handle:horizontal {{
        width: 10px; margin: -6px 0; background: {VIOLET_HI}; border: 1px solid {VIOLET};
    }}
    QScrollBar:vertical {{ background: transparent; width: 6px; margin: 0; }}
    QScrollBar::handle:vertical {{ background: {LINE_HI}; min-height: 24px; }}
    QScrollBar::handle:vertical:hover {{ background: {VIOLET_LO}; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
    QListView {{ background: #0b0911; color: {TEXT}; border: 1px solid {LINE_HI}; }}
    """


def arrow_stylesheet(folder: Path) -> str:
    """Stylesheets can only show arrow glyphs from image files, so draw two tiny PNGs."""
    try:
        folder.mkdir(parents=True, exist_ok=True)
        files = {}
        for name, pts in (("down", [(1, 1), (9, 1), (5, 6)]), ("up", [(1, 6), (9, 6), (5, 1)])):
            path = folder / f"arrow_{name}_v1.png"
            if not path.exists():
                img = QImage(20, 14, QImage.Format.Format_ARGB32_Premultiplied)
                img.fill(0)
                p = QPainter(img)
                p.setRenderHint(QPainter.RenderHint.Antialiasing)
                p.scale(2, 2)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(VIOLET_HI))
                p.drawPolygon(QPolygonF([QPointF(x, y) for x, y in pts]))
                p.end()
                if not img.save(str(path)):
                    return ""
            files[name] = path.as_posix()
    except OSError:
        return ""
    return f"""
    QComboBox::drop-down {{ subcontrol-origin: padding; subcontrol-position: center right; width: 24px; border: none; }}
    QComboBox::down-arrow {{ image: url("{files['down']}"); width: 10px; height: 7px; }}
    QAbstractSpinBox::up-button {{ subcontrol-origin: border; subcontrol-position: top right; width: 20px; border: none; }}
    QAbstractSpinBox::down-button {{ subcontrol-origin: border; subcontrol-position: bottom right; width: 20px; border: none; }}
    QAbstractSpinBox::up-arrow {{ image: url("{files['up']}"); width: 9px; height: 6px; }}
    QAbstractSpinBox::down-arrow {{ image: url("{files['down']}"); width: 9px; height: 6px; }}
    QAbstractSpinBox::up-button:hover, QAbstractSpinBox::down-button:hover {{ background: {VIOLET_DEEP}; }}
    """
