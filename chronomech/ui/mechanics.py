"""Procedural watch-movement parts: meshing gear trains, bridges, jewels.

Gears are generated as QPainterPaths (trapezoidal teeth, spoked windows) and
pre-rendered into sprites; meshing gears get a phase offset so their teeth
interlock while rotating at the correct (inverse tooth-count) ratio.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QPainter,
    QPainterPath,
    QPainterPathStroker,
    QPen,
    QPixmap,
    QPolygonF,
    QRadialGradient,
)

from .. import theme as T

TAU = math.tau


def _p(r: float, a: float) -> QPointF:
    return QPointF(r * math.cos(a), r * math.sin(a))


# ── gear geometry ────────────────────────────────────────────────────────────
def gear_outline(teeth: int, r_pitch: float, kind: str = "spur") -> QPolygonF:
    pitch = TAU / teeth
    m = 2.0 * r_pitch / teeth
    pts: list[QPointF] = []
    if kind == "escape":                       # Swiss-lever club teeth
        ra, rd = r_pitch, r_pitch * 0.66
        for i in range(teeth):
            a = i * pitch
            pts += [_p(rd, a - pitch * 0.32), _p(ra, a + pitch * 0.02),
                    _p(ra * 0.95, a + pitch * 0.14), _p(rd * 1.05, a + pitch * 0.16)]
        return QPolygonF(pts)
    ra, rd = r_pitch + 0.92 * m, r_pitch - 1.12 * m
    for i in range(teeth):
        a = i * pitch
        if kind == "ratchet":
            pts += [_p(rd, a), _p(ra, a + pitch * 0.06), _p(rd + 0.3 * m, a + pitch * 0.82)]
        else:
            pts += [_p(rd, a - pitch * 0.30), _p(r_pitch - 0.2 * m, a - pitch * 0.235),
                    _p(ra, a - pitch * 0.13), _p(ra, a + pitch * 0.13),
                    _p(r_pitch - 0.2 * m, a + pitch * 0.235), _p(rd, a + pitch * 0.30),
                    _p(rd, a + pitch * 0.5)]
    return QPolygonF(pts)


def gear_path(teeth: int, r_pitch: float, *, kind: str = "spur", spokes: int = 5,
              hub: float = 0.27, spoke_w: float = 0.10, bore: float = 0.07) -> QPainterPath:
    path = QPainterPath()
    path.setFillRule(Qt.FillRule.OddEvenFill)
    path.addPolygon(gear_outline(teeth, r_pitch, kind))
    path.closeSubpath()
    m = 2.0 * r_pitch / teeth
    root = r_pitch * 0.66 if kind == "escape" else r_pitch - 1.12 * m
    if spokes:
        r_out = root - max(1.1 * m, r_pitch * 0.09)
        r_in = r_pitch * hub
        w = r_pitch * spoke_w
        for k in range(spokes):
            a0 = k * TAU / spokes + 0.35
            a1 = a0 + TAU / spokes
            d_out = math.asin(min(0.99, w / 2 / r_out))
            d_in = math.asin(min(0.99, w / 2 / r_in))
            o0, o1, i0, i1 = a0 + d_out, a1 - d_out, a0 + d_in, a1 - d_in
            if o1 - o0 < 0.05 or i1 - i0 < 0.05:
                continue
            win = QPainterPath()
            win.moveTo(_p(r_out, o0))
            win.arcTo(QRectF(-r_out, -r_out, 2 * r_out, 2 * r_out), -math.degrees(o0), -math.degrees(o1 - o0))
            win.lineTo(_p(r_in, i1))
            win.arcTo(QRectF(-r_in, -r_in, 2 * r_in, 2 * r_in), -math.degrees(i1), math.degrees(i1 - i0))
            win.closeSubpath()
            path.addPath(win)
    if bore:
        path.addEllipse(QPointF(0, 0), r_pitch * bore, r_pitch * bore)
    return path


# ── gear trains ──────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class GearSpec:
    name: str
    teeth: int
    style: str = "steel"
    parent: str | None = None
    angle: float | None = None     # direction from parent centre in degrees; None = same arbor
    spokes: int = 5
    kind: str = "spur"
    x: float = 0.0                 # root position (units of clock radius)
    y: float = 0.0


@dataclass(frozen=True)
class Gear:
    spec: GearSpec
    x: float
    y: float
    r_pitch: float
    ratio: float                   # angular velocity relative to the root wheel (signed)
    phase: float                   # radians

    @property
    def r_outer(self) -> float:
        return self.r_pitch + 0.92 * 2.0 * self.r_pitch / self.spec.teeth


def solve_train(specs: list[GearSpec], module: float) -> list[Gear]:
    """Place every wheel tangent to its parent and derive ratio + meshing phase.

    For a driven wheel at direction φ from its driver:  θc = −k·θp + φ(1+k) + π − π/Nc
    with k = Np/Nc. This puts a tooth gap of the child exactly where the parent's
    tooth sits on the line of centres, and keeps it there as both rotate.
    """
    solved: dict[str, Gear] = {}
    for s in specs:
        rp = module * s.teeth / 2.0
        if s.parent is None:
            g = Gear(s, s.x, s.y, rp, 1.0, 0.0)
        else:
            par = solved[s.parent]
            if s.angle is None:
                g = Gear(s, par.x, par.y, rp, par.ratio, par.phase)
            else:
                phi = math.radians(s.angle)
                d = par.r_pitch + rp
                k = par.spec.teeth / s.teeth
                phase = -k * par.phase + phi * (1 + k) + math.pi - math.pi / s.teeth
                g = Gear(s, par.x + d * math.cos(phi), par.y + d * math.sin(phi), rp, -par.ratio * k, phase)
        solved[s.name] = g
    return list(solved.values())


# ── rendering ────────────────────────────────────────────────────────────────
_STYLES = {
    "steel": {"fill": [(0.0, "#3d3652"), (0.45, "#2a2539"), (0.85, "#1e1a2a"), (1.0, "#352e48")],
              "edge": "#6f6294", "rings": 16, "glow": None},
    "violet": {"fill": [(0.0, "#55309a"), (0.5, "#3a1f6e"), (0.88, "#28144f"), (1.0, "#5a34a0")],
               "edge": "#b58cff", "rings": 14, "glow": None},
    "ghost": {"fill": [(0.0, "#2a9d5cff"), (1.0, "#0c9d5cff")],
              "edge": T.VIOLET, "rings": 0, "glow": T.VIOLET},
    "dark": {"fill": [(0.0, "#26212f"), (1.0, "#15121c")], "edge": "#4a4160", "rings": 8, "glow": None},
}


def render_sprite(path: QPainterPath, r_outer: float, style: str, dpr: float) -> tuple[QPixmap, float]:
    """Rasterise a part once; it is then only rotated/blitted every frame."""
    spec = _STYLES.get(style, _STYLES["steel"])
    half = math.ceil(r_outer + 7)
    pm = QPixmap(max(1, round(2 * half * dpr)), max(1, round(2 * half * dpr)))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.translate(half, half)
    if spec["glow"]:
        T.glow_stroke(p, path, T.qc(spec["glow"], 200), width=1.0, radius=6.0, strength=1.2)
    grad = QRadialGradient(QPointF(0, 0), r_outer)
    for pos, col in spec["fill"]:
        grad.setColorAt(pos, QColor(col))
    p.fillPath(path, grad)
    if spec["rings"]:
        p.save()
        p.setClipPath(path)
        p.setBrush(Qt.BrushStyle.NoBrush)
        for i in range(spec["rings"]):
            r = r_outer * (0.22 + 0.78 * i / spec["rings"])
            p.setPen(QPen(T.qc("#ffffff", 9 if i % 2 else 16), 0.6))
            p.drawEllipse(QPointF(0, 0), r, r)
        p.restore()
    p.strokePath(path, QPen(QColor(spec["edge"]), 0.9))
    p.end()
    return pm, half


def bridge_path(points: list[tuple[float, float]], width: float,
                bosses: list[tuple[float, float, float]] = ()) -> QPainterPath:
    """A bridge is a thick stroked centre line, unioned with round bosses over pivots."""
    centre = QPainterPath(QPointF(*points[0]))
    for pt in points[1:]:
        centre.lineTo(QPointF(*pt))
    stroker = QPainterPathStroker()
    stroker.setWidth(width)
    stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
    stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    shape = stroker.createStroke(centre)
    for x, y, r in bosses:
        boss = QPainterPath()
        boss.addEllipse(QPointF(x, y), r, r)
        shape = shape.united(boss)
    return shape.simplified()


def draw_jewel(p: QPainter, c: QPointF, r: float) -> None:
    """An amethyst bearing jewel in a polished chaton."""
    p.save()
    p.setPen(QPen(T.qc("#08070c"), max(0.5, r * 0.12)))
    chaton = QRadialGradient(c - QPointF(r * 0.4, r * 0.5), r * 1.9)
    chaton.setColorAt(0.0, QColor("#8f84b0"))
    chaton.setColorAt(1.0, QColor("#2e2840"))
    p.setBrush(chaton)
    p.drawEllipse(c, r * 1.5, r * 1.5)
    stone = QRadialGradient(c - QPointF(r * 0.35, r * 0.35), r * 1.25)
    stone.setColorAt(0.0, QColor("#f6e6ff"))
    stone.setColorAt(0.22, QColor("#c27dff"))
    stone.setColorAt(0.7, QColor("#6420b8"))
    stone.setColorAt(1.0, QColor("#2b0b5c"))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(stone)
    p.drawEllipse(c, r, r)
    p.setBrush(T.qc("#0a0610", 220))
    p.drawEllipse(c, r * 0.22, r * 0.22)
    p.restore()


def spiral_points(r0: float, r1: float, turns: float, twist: float, n: int = 140) -> QPolygonF:
    """Archimedean hairspring; `twist` winds the inner end, the outer stud stays put."""
    pts = []
    for i in range(n + 1):
        u = i / n
        r = r0 + (r1 - r0) * u
        a = u * turns * TAU + twist * (1.0 - u)
        pts.append(_p(r, a))
    return QPolygonF(pts)
