"""The centre-piece: a skeletonised tourbillon chronograph drawn entirely with QPainter.

Rendering is change-driven so the clock can run at the full frame rate cheaply:

    static layers (rebuilt on resize / date change)
        under  ─ movement plate (perlage), engravings, wheel shadows
        over   ─ bridges, sub-dials, date windows, chapter ring, bezel
        glass  ─ crystal reflection
    slow layer (re-rendered once a second)
        over + timer bezel + sub-dial hands + hour & minute hands + glass
    drawn per paint, only where something moved
        gear train, tourbillon (cage, escape wheel, balance, hairspring),
        seconds & chronograph hands, seconds track, HUD arcs

Every frame `_on_frame` compares the moving parts with what was last painted and
repaints only those rectangles: the tourbillon, the footprints of the sweeping
hands, the gear train and the two ends of each HUD arc. The widget is opaque (it
paints the window backdrop under itself), so these updates never reach the
widgets behind it.

Sweep modes: "smooth" moves the hands, cage and HUD arcs every frame (the gear
train at 20 Hz, where a step is under half a pixel), "mechanical" steps them 6×/s
(21 600 vph) and "quartz" once a second. The balance wheel always oscillates
continuously.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass
from datetime import datetime

from PySide6.QtCore import QPointF, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QConicalGradient,
    QFontMetricsF,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
    QRadialGradient,
)
from PySide6.QtWidgets import QSizePolicy, QWidget

from .. import theme as T
from ..core.chrono import Stopwatch
from ..core.countdown import Countdown
from ..core.engine import TimeEngine
from ..core.settings import Settings
from .mechanics import (
    GearSpec,
    bridge_path,
    draw_jewel,
    gear_outline,
    gear_path,
    render_sprite,
    solve_train,
    spiral_points,
)

TAU = math.tau
ROOT_OMEGA = TAU / 60.0                  # centre wheel turns once a minute
SWEEP_RATES = {"smooth": 0, "mechanical": 6, "quartz": 1}   # hand steps per second (0 = continuous)
SMOOTH_TRAIN_RATE = 20                   # wheel teeth move < 0.5 px per step: steps are invisible
ESCAPEMENT_BPS = 6                       # the balance & escape wheel always run at 21 600 vph
HUD_ARC_SPEED = 6.0                      # degrees per second

DIAL = 0.80                              # skeleton plate radius (units of R)
SUB_D, SUB_R = 0.40, 0.165               # sub-dials at 3 and 9 o'clock
TB_D, TB_R = 0.41, 0.20                  # tourbillon aperture at 6 o'clock
DATE_D = 0.575                           # date / day windows at 4:30 and 7:30
HUD_ARCS = ((0, 46), (62, 14), (118, 74), (228, 30), (284, 44))   # Qt degrees

MODULE = 0.0084
TRAIN = [
    GearSpec("centre", 58, "steel", spokes=5),
    GearSpec("lower_r", 24, "dark", parent="centre", angle=38, spokes=4),
    GearSpec("lower_l", 24, "violet", parent="centre", angle=142, spokes=4),
    GearSpec("third", 32, "violet", parent="centre", angle=-38, spokes=4),
    GearSpec("third_pinion", 11, "steel", parent="third", spokes=0),
    GearSpec("fourth", 40, "steel", parent="third_pinion", angle=-112, spokes=5),
    GearSpec("left", 36, "ghost", parent="centre", angle=-145, spokes=6),
    GearSpec("left_pinion", 12, "violet", parent="left", spokes=0),
    GearSpec("crown", 30, "steel", parent="left_pinion", angle=-60, spokes=4),
]


def _ease_out(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1.0 - (1.0 - t) ** 3


def quantise(x: float, rate: int) -> float:
    """Snap a time in seconds down to steps of 1/rate; rate 0 means continuous."""
    return math.floor(x * rate) / rate if rate else x


def _bounds(xs: list[float], ys: list[float], pad: float) -> QRect:
    return QRectF(min(xs) - pad, min(ys) - pad,
                  max(xs) - min(xs) + 2 * pad, max(ys) - min(ys) + 2 * pad).toAlignedRect()


def needle_rects(c: QPointF, r: float, frac: float, tail: float, tip: float,
                 pad: float, segments: int = 5) -> list[QRect]:
    """Rects covering a hand that points at dial fraction `frac`, from `tail` behind the
    pivot to `tip` (units of r). Split along its length so a diagonal hand does not
    dirty its whole bounding box."""
    a = T.clock_angle(frac)
    ux, uy = math.cos(a), math.sin(a)
    stops = [-tail + (tip + tail) * k / segments for k in range(segments + 1)]
    return [_bounds([c.x() + ux * r0 * r, c.x() + ux * r1 * r], [c.y() + uy * r0 * r, c.y() + uy * r1 * r], pad)
            for r0, r1 in zip(stops, stops[1:])]


def hud_edge_rects(c: QPointF, r: float, rot_a: float, rot_b: float, pad: float) -> list[QRect]:
    """A rotating HUD arc only changes pixels at its two ends."""
    rects = []
    for start, span in HUD_ARCS:
        for edge in (start, start + span):
            xs, ys = [], []
            for rot in (rot_a, rot_b):
                phi = math.radians(edge + rot)
                for rr in (0.975 * r, r):
                    xs.append(c.x() + rr * math.cos(phi))
                    ys.append(c.y() - rr * math.sin(phi))
            rects.append(_bounds(xs, ys, pad))
    return rects


@dataclass(frozen=True)
class Motion:
    """Where everything that moves is, sampled for one frame."""
    train: float              # clock time driving the gear train
    cage: float               # clock time driving the tourbillon cage
    sec: float                # seconds hand & track, fraction of a turn
    chrono: float | None      # chronograph hand, None while reset
    hud: float                # HUD arc rotation, degrees
    slow: tuple               # identity of the slow layer's content


def _text_centered(p: QPainter, text: str, f, color, at: QPointF) -> None:
    fm = QFontMetricsF(f)
    w = fm.horizontalAdvance(text) - f.letterSpacing()
    p.setFont(f)
    p.setPen(QColor(color))
    p.drawText(QPointF(at.x() - w / 2, at.y() + (fm.ascent() - fm.descent()) / 2), text)


def _annulus(r_out: float, r_in: float, c: QPointF = QPointF(0, 0)) -> QPainterPath:
    path = QPainterPath()
    path.setFillRule(Qt.FillRule.OddEvenFill)
    path.addEllipse(c, r_out, r_out)
    path.addEllipse(c, r_in, r_in)
    return path


def _sector(r0: float, r1: float, start: float, span: float) -> QPainterPath:
    """Annular sector in Qt angle convention (degrees, counter-clockwise positive)."""
    outer, inner = QRectF(-r1, -r1, 2 * r1, 2 * r1), QRectF(-r0, -r0, 2 * r0, 2 * r0)
    path = QPainterPath()
    path.arcMoveTo(outer, start)
    path.arcTo(outer, start, span)
    path.arcTo(inner, start + span, -span)
    path.closeSubpath()
    return path


def _metal_ring_gradient(c: QPointF, angle: float = 35.0) -> QConicalGradient:
    g = QConicalGradient(c, angle)
    for pos, col in ((0.0, "#7a6f98"), (0.13, "#2b2638"), (0.3, "#5d5379"), (0.5, "#1f1b2a"),
                     (0.65, "#6a5f88"), (0.82, "#25202f"), (1.0, "#7a6f98")):
        g.setColorAt(pos, QColor(col))
    return g


def _canvas(w: float, h: float, dpr: float) -> QPixmap:
    pm = QPixmap(max(1, round(w * dpr)), max(1, round(h * dpr)))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.GlobalColor.transparent)
    return pm


def _begin(pm: QPixmap) -> QPainter:
    p = QPainter(pm)
    p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing
                     | QPainter.RenderHint.SmoothPixmapTransform)
    return p


class Sprite:
    """A pre-rendered part drawn around a pivot; `soft` sprites are rendered at low
    resolution so the bilinear upscale doubles as a cheap blur (used for shadows)."""

    def __init__(self, bounds: QRectF, dpr: float, paint, soft: float = 1.0) -> None:
        self.offset = bounds.topLeft()
        self.pixmap = _canvas(bounds.width(), bounds.height(), dpr * soft)
        p = _begin(self.pixmap)
        p.translate(-bounds.left(), -bounds.top())
        paint(p)
        p.end()

    def draw(self, p: QPainter, at: QPointF, degrees: float, scale: float = 1.0) -> None:
        p.save()
        p.translate(at)
        p.rotate(degrees)
        if scale != 1.0:
            p.scale(scale, scale)
        p.drawPixmap(self.offset, self.pixmap)
        p.restore()


class MechanicalClock(QWidget):
    def __init__(self, engine: TimeEngine, stopwatch: Stopwatch, countdown: Countdown,
                 settings: Settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._sw = stopwatch
        self._cd = countdown
        self._settings = settings
        self.setMinimumSize(260, 260)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)    # paints its own backdrop
        self._train = solve_train(TRAIN, MODULE)
        self._gears = {g.spec.name: g for g in self._train}
        self._key: tuple | None = None
        self._built_r = 1.0
        self._half = 0
        self._layers: dict[str, QPixmap] = {}
        self._wheels: list[tuple] = []
        self._sprites: dict[str, Sprite] = {}
        self._paths: dict[str, QPainterPath] = {}
        self._slow = QPixmap()
        self._slow_key: tuple | None = None
        self._base = QPixmap()                    # backdrop + movement plate, opaque
        self._base_key: tuple | None = None
        self._backdrop = None
        self._backdrop_version = 0
        self._boot_t0 = time.perf_counter()
        self._rebuild = QTimer(self)
        self._rebuild.setSingleShot(True)
        self._rebuild.setInterval(150)
        self._rebuild.timeout.connect(self.update)
        self._pending_key: tuple | None = None
        self._pending_since = 0.0
        self._last: Motion | None = None          # what the screen currently shows
        self._frame_t = 0.0
        self._version = 0                         # bumped when the stopwatch / timer change
        self._tb_rect = QRect()
        self._inner_rect = QRect()
        self._train_rects: list[QRect] = []
        self._wheel_rects: list[QRect] = []
        self._spirals: list[QPolygonF] = []
        self._twist_max = 1.0
        stopwatch.changed.connect(self.invalidate)
        countdown.changed.connect(self.invalidate)
        engine.frame.connect(self._on_frame)

    # ── public ──
    def clock_geometry(self) -> tuple[QPointF, float]:
        side = min(self.width(), self.height())
        return QPointF(self.width() / 2, self.height() / 2), max(20.0, side / 2 - 3)

    def set_backdrop(self, painter) -> None:
        """`painter(p, rect)` paints what lies behind the clock (rect in clock coordinates)."""
        self._backdrop = painter
        self.backdrop_changed()

    def backdrop_changed(self) -> None:
        self._backdrop_version += 1
        self.update()

    def moveEvent(self, event) -> None:
        self.backdrop_changed()                   # a different part of the backdrop is behind us now
        super().moveEvent(event)

    def restart_boot(self) -> None:
        self._boot_t0 = time.perf_counter()

    def invalidate(self) -> None:
        self._version += 1
        self._last = None
        self.update()

    # ── frame scheduling ──
    def _boot(self) -> float:
        return _ease_out((time.perf_counter() - self._boot_t0) / 1.8)

    def _motion(self, now: float, e: float) -> Motion:
        rate = SWEEP_RATES.get(self._settings.get("sweep", "smooth"), 0)
        t = quantise(now, rate)
        local = datetime.fromtimestamp(t)
        sec = (local.second + local.microsecond / 1e6) / 60.0 * e
        chrono = None if self._sw.is_reset else (quantise(self._sw.elapsed(), rate) % 60.0) / 60.0
        hud = quantise(now, rate and ESCAPEMENT_BPS) * HUD_ARC_SPEED % 360.0
        return Motion(train=quantise(now, rate or SMOOTH_TRAIN_RATE), cage=t, sec=sec, chrono=chrono,
                      hud=hud, slow=(int(now), self._version, e >= 1.0))

    def _on_frame(self, now: float) -> None:
        self._frame_t = now
        last, e = self._last, self._boot()
        if last is None or e < 1.0 or self._pending_key is not None:
            self.update()
            return
        m = self._motion(now, e)
        if m.slow != last.slow or m.sec < last.sec or (m.chrono is None) != (last.chrono is None):
            self.update()                         # new second, minute wrap or chrono start/reset
            return
        c, r = self.clock_geometry()
        pad = r * 0.045 + 2                       # glow (0.02 r) + offset soft shadow (0.033 r)
        rects = [self._tb_rect]                   # the balance never rests
        if m.train != last.train:
            rects += self._train_rects
        if m.sec != last.sec:
            rects += [a.united(b) for a, b in zip(needle_rects(c, r, last.sec, 0.22, 1.0, pad),
                                                  needle_rects(c, r, m.sec, 0.22, 1.0, pad))]
        if m.chrono is not None and m.chrono != last.chrono:
            rects += [a.united(b) for a, b in zip(needle_rects(c, r, last.chrono, 0.24, 0.88, pad),
                                                  needle_rects(c, r, m.chrono, 0.24, 0.88, pad))]
        if m.hud != last.hud:
            rects += hud_edge_rects(c, r, last.hud, m.hud, 9.0)
        for rect in rects:
            self.update(rect)

    def resizeEvent(self, event) -> None:
        c, r = self.clock_geometry()
        cx, cy = c.x(), c.y()
        half = TB_R * r * 1.02 + 3
        self._tb_rect = QRectF(cx - half, cy + TB_D * r - half, 2 * half, 2 * half).toAlignedRect()
        self._wheel_rects = []
        for g in self._train:
            h = g.r_outer * r + 9                 # sprite half-size: outer radius + glow margin
            self._wheel_rects.append(QRectF(cx + g.x * r - h, cy + g.y * r - h, 2 * h, 2 * h).toAlignedRect())
        # pinions sit on their wheels' arbors, inside the wheel's rect
        self._train_rects = [rect for g, rect in zip(self._train, self._wheel_rects) if g.spec.spokes]
        k = 0.95 * r / math.sqrt(2)               # anything inside this square misses the HUD
        self._inner_rect = QRectF(cx - k, cy - k, 2 * k, 2 * k).toAlignedRect()
        self._last = None
        super().resizeEvent(event)

    # ── cache management ──
    def _ensure_layers(self, r: float, dpr: float, day) -> bool:
        """Returns True when the caches were rebuilt."""
        key = (round(r, 1), dpr, day)
        if key == self._key:
            return False
        if self._key is not None and self._key[1:] == key[1:]:
            # live window resize: stretch the old cache, rebuild once the size settles
            now = time.perf_counter()
            if key != self._pending_key:
                self._pending_key, self._pending_since = key, now
                self._rebuild.start()
                return False
            if now - self._pending_since < 0.12:
                self._rebuild.start()
                return False
        self._build(r, dpr, day)
        self._key = key
        self._pending_key = None
        return True

    def _build(self, r: float, dpr: float, day) -> None:
        self._built_r = r
        self._half = half = math.ceil(r) + 8
        self._build_paths(r)
        self._wheels = []
        for g in self._train:
            pinion = g.spec.spokes == 0
            path = gear_path(g.spec.teeth, g.r_pitch * r, kind=g.spec.kind, spokes=g.spec.spokes,
                             bore=0.22 if pinion else 0.07)
            self._wheels.append((g, *render_sprite(path, g.r_outer * r, g.spec.style, dpr)))
        ar = TB_R * r
        esc = gear_path(15, ar * 0.17, kind="escape", spokes=4, hub=0.32, spoke_w=0.14, bore=0.12)
        self._escape = render_sprite(esc, ar * 0.17, "violet", dpr)
        self._build_sprites(r, dpr)

        def layer(fn) -> QPixmap:
            pm = _canvas(2 * half, 2 * half, dpr)
            p = _begin(pm)
            p.translate(half, half)
            fn(p)
            p.end()
            return pm

        self._layers = {
            "under": layer(lambda p: self._paint_under(p, r)),
            "over": layer(lambda p: self._paint_over(p, r, day)),
            "glass": layer(lambda p: self._paint_glass(p, r)),
            "sec_ring": layer(lambda p: self._paint_glow_ring(p, 0.865 * r, max(1.2, r * 0.006), r * 0.03, 230)),
            "hud_ring": layer(lambda p: self._paint_glow_ring(p, 0.996 * r, 1.3, 5.0, 150)),
        }
        self._slow = _canvas(2 * half, 2 * half, dpr)
        self._slow_key = None
        self._base_key = None

    def _blit(self, p: QPainter, name: str, c: QPointF, s: float) -> None:
        pm = self._layers.get(name)
        if pm is None:
            return
        p.save()
        p.translate(c)
        p.scale(s, s)
        p.drawPixmap(QPointF(-self._half, -self._half), pm)
        p.restore()

    def _build_paths(self, r: float) -> None:
        P: dict[str, QPainterPath] = {}

        def poly(pts) -> QPainterPath:
            path = QPainterPath()
            path.addPolygon(QPolygonF([QPointF(x * r, y * r) for x, y in pts]))
            path.closeSubpath()
            return path

        def facets(pts) -> tuple[QPainterPath, QPainterPath]:
            """Left/right halves of a symmetric outline whose middle point is the tip."""
            left = [(0.0, pts[0][1])] + pts[: len(pts) // 2 + 1]
            return poly(left), poly([(-x, y) for x, y in left])

        hour = [(-0.021, 0.085), (-0.035, -0.06), (-0.029, -0.36), (0.0, -0.50),
                (0.029, -0.36), (0.035, -0.06), (0.021, 0.085)]
        minute = [(-0.017, 0.10), (-0.027, -0.06), (-0.019, -0.63), (0.0, -0.77),
                  (0.019, -0.63), (0.027, -0.06), (0.017, 0.10)]
        for name, pts, lume in (
            ("hour", hour, [(-0.018, -0.085), (-0.015, -0.345), (0.0, -0.445), (0.015, -0.345), (0.018, -0.085)]),
            ("minute", minute, [(-0.013, -0.09), (-0.010, -0.61), (0.0, -0.705), (0.010, -0.61), (0.013, -0.09)]),
        ):
            P[name] = poly(pts)
            P[name + "_l"], P[name + "_r"] = facets(pts)
            P[name + "_lume"] = poly(lume)

        sec = poly([(-0.0065, 0.20), (-0.0026, -0.80), (0.0, -0.84), (0.0026, -0.80), (0.0065, 0.20)])
        sec.setFillRule(Qt.FillRule.WindingFill)
        sec.addEllipse(QPointF(0, 0.15 * r), 0.024 * r, 0.024 * r)
        P["seconds"] = sec.simplified()
        P["seconds_tip"] = poly([(0.0, -0.765), (0.009, -0.72), (0.0, -0.675), (-0.009, -0.72)])
        P["seconds_hole"] = QPainterPath()
        P["seconds_hole"].addEllipse(QPointF(0, 0.15 * r), 0.012 * r, 0.012 * r)
        P["chrono"] = poly([(-0.005, 0.22), (-0.0022, -0.78), (-0.012, -0.78), (0.0, -0.86),
                            (0.012, -0.78), (0.0022, -0.78), (0.005, 0.22)])
        sr = SUB_R
        P["small"] = poly([(-sr * 0.035, sr * 0.2), (-sr * 0.014, -sr * 0.8), (0, -sr * 0.86),
                           (sr * 0.014, -sr * 0.8), (sr * 0.035, sr * 0.2)])

        ticks = QPainterPath()
        for i in range(120):
            a = i * TAU / 120
            r0 = 0.972 if i % 10 == 0 else 0.978
            ticks.moveTo(QPointF(math.cos(a) * r0 * r, math.sin(a) * r0 * r))
            ticks.lineTo(QPointF(math.cos(a) * 0.988 * r, math.sin(a) * 0.988 * r))
        P["hud_ticks"] = ticks
        hud_clip = QPainterPath()
        for start, span in HUD_ARCS:
            hud_clip.addPath(_sector(0.975 * r, 1.03 * r, start, span))
        P["hud_clip"] = hud_clip

        # tourbillon cage arms (rotating frame) and pallet fork
        ar = TB_R * r
        self._twist_max = math.radians(150.0) * 0.9           # hairspring shapes, pre-computed
        self._spirals = [spiral_points(ar * 0.10, ar * 0.42, 5.5, self._twist_max * (i / 40 - 1), 120)
                         for i in range(81)]
        cage = QPainterPath()
        cage.setFillRule(Qt.FillRule.WindingFill)
        for k in range(3):
            a = k * TAU / 3 - math.pi / 2
            ux, uy = math.cos(a), math.sin(a)
            vx, vy = -uy, ux
            reach = 0.84 if k == 0 else 0.80
            w0, w1 = 0.085, 0.05
            cage.addPolygon(QPolygonF([
                QPointF((ux * 0.1 + vx * w0) * ar, (uy * 0.1 + vy * w0) * ar),
                QPointF((ux * reach + vx * w1) * ar, (uy * reach + vy * w1) * ar),
                QPointF((ux * reach - vx * w1) * ar, (uy * reach - vy * w1) * ar),
                QPointF((ux * 0.1 - vx * w0) * ar, (uy * 0.1 - vy * w0) * ar)]))
            cage.closeSubpath()
            if k == 0:   # this arm doubles as the small-seconds pointer
                cage.addPolygon(QPolygonF([
                    QPointF(ux * 0.91 * ar, uy * 0.91 * ar),
                    QPointF((ux * 0.78 + vx * 0.07) * ar, (uy * 0.78 + vy * 0.07) * ar),
                    QPointF((ux * 0.78 - vx * 0.07) * ar, (uy * 0.78 - vy * 0.07) * ar)]))
                cage.closeSubpath()
        cage.addEllipse(QPointF(0, 0), 0.16 * ar, 0.16 * ar)
        P["cage"] = cage.simplified()
        fork = QPainterPath()
        fork.addPolygon(QPolygonF([QPointF(-0.20 * ar, -0.02 * ar), QPointF(0.20 * ar, -0.02 * ar),
                                   QPointF(0.20 * ar, 0.03 * ar), QPointF(0.03 * ar, 0.04 * ar),
                                   QPointF(0.015 * ar, 0.26 * ar), QPointF(-0.015 * ar, 0.26 * ar),
                                   QPointF(-0.03 * ar, 0.04 * ar), QPointF(-0.20 * ar, 0.03 * ar)]))
        fork.closeSubpath()
        P["fork"] = fork
        self._paths = P

    def _build_sprites(self, r: float, dpr: float) -> None:
        P = self._paths
        glow = r * 0.035

        def bounds(path: QPainterPath, margin: float) -> QRectF:
            return path.boundingRect().adjusted(-margin, -margin, margin, margin)

        def shadow(path: QPainterPath, alpha: int):
            return Sprite(bounds(path, r * 0.02), dpr, lambda p: p.fillPath(path, T.qc("#000000", alpha)), soft=0.3)

        def blade(name: str):
            def paint(p: QPainter) -> None:
                p.fillPath(P[name + "_l"], QColor("#a99ed0"))
                p.fillPath(P[name + "_r"], QColor("#433b5c"))
                p.strokePath(P[name], QPen(T.qc("#050408", 220), 0.7))
                T.glow_stroke(p, P[name + "_lume"], T.qc(T.VIOLET, 170), width=0.4, radius=r * 0.022, strength=1.2)
                p.fillPath(P[name + "_lume"], T.qc(T.VIOLET_HI))
            return paint

        def seconds(p: QPainter) -> None:
            T.glow_stroke(p, P["seconds"], T.qc(T.VIOLET, 170), width=0.4, radius=r * 0.02)
            p.fillPath(P["seconds"], QColor("#b98bff"))
            p.fillPath(P["seconds_hole"], QColor("#0b0910"))
            p.fillPath(P["seconds_tip"], QColor("#f3ebff"))

        def chrono(p: QPainter) -> None:
            T.glow_stroke(p, P["chrono"], T.qc(T.MAGENTA, 160), width=0.4, radius=r * 0.02)
            p.fillPath(P["chrono"], T.qc(T.MAGENTA))

        def small(color: str):
            def paint(p: QPainter) -> None:
                T.glow_stroke(p, P["small"], T.qc(color, 120), width=0.4, radius=SUB_R * r * 0.06)
                p.fillPath(P["small"], QColor(color))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(_metal_ring_gradient(QPointF(0, 0)))
                p.drawEllipse(QPointF(0, 0), SUB_R * r * 0.09, SUB_R * r * 0.09)
                p.setBrush(QColor("#0a0810"))
                p.drawEllipse(QPointF(0, 0), SUB_R * r * 0.03, SUB_R * r * 0.03)
            return paint

        S = {
            "hour": Sprite(bounds(P["hour"], glow), dpr, blade("hour")),
            "minute": Sprite(bounds(P["minute"], glow), dpr, blade("minute")),
            "seconds": Sprite(bounds(P["seconds"], glow), dpr, seconds),
            "chrono": Sprite(bounds(P["chrono"], glow), dpr, chrono),
            "small_violet": Sprite(bounds(P["small"], glow), dpr, small(T.VIOLET_HI)),
            "small_magenta": Sprite(bounds(P["small"], glow), dpr, small(T.MAGENTA)),
        }
        for name, alpha in (("hour", 150), ("minute", 150), ("seconds", 120), ("chrono", 120), ("small", 130)):
            S[name + "_shadow"] = shadow(P[name], alpha)

        def cap(p: QPainter) -> None:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(_metal_ring_gradient(QPointF(0, 0), 20))
            p.drawEllipse(QPointF(0, 0), r * 0.034, r * 0.034)
            draw_jewel(p, QPointF(0, 0), r * 0.013)

        S["cap"] = Sprite(QRectF(-r * 0.04, -r * 0.04, r * 0.08, r * 0.08), dpr, cap)

        # tourbillon parts, drawn every frame, so pre-rendered once
        ar = TB_R * r

        def balance(p: QPainter) -> None:
            rb = ar * 0.56
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor("#8d63d9"), ar * 0.07))
            p.drawEllipse(QPointF(0, 0), rb, rb)
            p.setPen(QPen(QColor("#c4a2ff"), max(0.6, ar * 0.012)))
            p.drawEllipse(QPointF(0, 0), rb + ar * 0.03, rb + ar * 0.03)
            p.setPen(QPen(QColor("#6a46b0"), ar * 0.055, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
            for k in range(3):
                a = k * TAU / 3 + 0.5
                p.drawLine(T.polar(0, 0, ar * 0.08, a), T.polar(0, 0, rb, a))
            p.setPen(QPen(T.qc("#08070c"), 0.6))
            p.setBrush(QColor("#d9c4ff"))
            for k in range(8):
                p.drawEllipse(T.polar(0, 0, rb + ar * 0.035, k * TAU / 8 + 0.2), ar * 0.032, ar * 0.032)

        def fork(p: QPainter) -> None:
            p.fillPath(P["fork"], QColor("#5d5379"))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(T.qc("#c27dff"))
            for sx in (-0.18, 0.18):
                p.drawRect(QRectF((sx - 0.025) * ar, -0.06 * ar, 0.05 * ar, 0.07 * ar))

        def cage(p: QPainter) -> None:
            grad = QLinearGradient(QPointF(-ar, -ar), QPointF(ar, ar))
            grad.setColorAt(0.0, QColor("#a99dd0"))
            grad.setColorAt(0.5, QColor("#4b4266"))
            grad.setColorAt(1.0, QColor("#8a7fb0"))
            p.fillPath(P["cage"], grad)
            p.strokePath(P["cage"], QPen(T.qc("#08070c", 220), 0.7))

        jewel = ar * 0.08
        S["balance"] = Sprite(QRectF(-0.68 * ar, -0.68 * ar, 1.36 * ar, 1.36 * ar), dpr, balance)
        S["fork"] = Sprite(P["fork"].boundingRect().adjusted(-2, -0.05 * ar - 2, 2, 2), dpr, fork)
        S["cage"] = Sprite(bounds(P["cage"], 2), dpr, cage)
        S["tb_jewel"] = Sprite(QRectF(-1.6 * jewel, -1.6 * jewel, 3.2 * jewel, 3.2 * jewel), dpr,
                               lambda p: draw_jewel(p, QPointF(0, 0), jewel))

        self._sprites = S

    # ── static layers ──
    @staticmethod
    def _paint_glow_ring(p: QPainter, radius: float, width: float, glow: float, alpha: int) -> None:
        ring = QPainterPath()
        ring.addEllipse(QPointF(0, 0), radius, radius)
        T.glow_stroke(p, ring, T.qc(T.VIOLET, alpha), width=width, radius=glow)

    def _paint_under(self, p: QPainter, r: float) -> None:
        p.setPen(Qt.PenStyle.NoPen)
        shadow = QRadialGradient(QPointF(0, r * 0.03), r * 1.03)
        shadow.setColorAt(0.86, T.qc("#000000", 170))
        shadow.setColorAt(1.0, T.qc("#000000", 0))
        p.setBrush(shadow)
        p.drawEllipse(QPointF(0, r * 0.03), r * 1.03, r * 1.03)

        plate_r = DIAL * r
        plate = QRadialGradient(QPointF(0, 0), plate_r)
        plate.setColorAt(0.0, QColor("#16121f"))
        plate.setColorAt(0.7, QColor("#0e0b14"))
        plate.setColorAt(1.0, QColor("#07060a"))
        p.setBrush(plate)
        p.drawEllipse(QPointF(0, 0), plate_r, plate_r)

        # perlage — the overlapping circular graining of a watch main plate
        clip = QPainterPath()
        clip.addEllipse(QPointF(0, 0), plate_r, plate_r)
        p.save()
        p.setClipPath(clip)
        p.setPen(QPen(T.qc("#050407", 150), 0.6))
        s = max(6.0, r * 0.05)
        y, row = -plate_r - s, 0
        while y < plate_r + s:
            x = -plate_r - s + (s * 0.45 if row % 2 else 0.0)
            while x < plate_r + s:
                if x * x + y * y < (plate_r + s) ** 2:
                    g = QRadialGradient(QPointF(x - s * 0.22, y - s * 0.28), s * 0.72)
                    g.setColorAt(0.0, T.qc("#2c253b", 130))
                    g.setColorAt(0.6, T.qc("#191522", 100))
                    g.setColorAt(1.0, T.qc("#0c0a11", 80))
                    p.setBrush(g)
                    p.drawEllipse(QPointF(x, y), s * 0.6, s * 0.6)
                x += s * 0.9
            y += s * 0.78
            row += 1
        p.restore()

        # engraved calibre text on the plate
        f = T.font(r * 0.026, "semibold", spacing=r * 0.004)
        for text, ang in (("CAL. CM-01", -15), ("21 600 A/h", 195), ("31 JEWELS", 165), ("TOURBILLON", 15)):
            p.save()
            if 0 < ang < 180:       # lower half: keep the engraving upright
                p.rotate(ang - 90)
                _text_centered(p, text, f, T.qc("#3a3150"), QPointF(0, 0.74 * r))
            else:
                p.rotate(ang + 90)
                _text_centered(p, text, f, T.qc("#3a3150"), QPointF(0, -0.74 * r))
            p.restore()

        # soft shadows the wheels cast on the plate
        for g in self._train:
            if g.spec.spokes == 0:
                continue
            c = QPointF((g.x + 0.007) * r, (g.y + 0.013) * r)
            rad = g.r_outer * r * 1.05
            sg = QRadialGradient(c, rad)
            sg.setColorAt(0.75, T.qc("#000000", 120))
            sg.setColorAt(1.0, T.qc("#000000", 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(sg)
            p.drawEllipse(c, rad, rad)

    def _paint_bridge(self, p: QPainter, path: QPainterPath, r: float) -> None:
        p.save()
        p.translate(r * 0.007, r * 0.013)
        p.fillPath(path, T.qc("#000000", 150))
        p.restore()
        grad = QLinearGradient(QPointF(-r * 0.7, -r * 0.8), QPointF(r * 0.7, r * 0.8))
        grad.setColorAt(0.0, QColor("#302a42"))
        grad.setColorAt(0.5, QColor("#1c1827"))
        grad.setColorAt(1.0, QColor("#2b253a"))
        p.fillPath(path, grad)
        p.save()                                   # Côtes de Genève stripes
        p.setClipPath(path)
        p.rotate(-28)
        w = r * 0.032
        for i in range(-40, 40, 2):
            band = QLinearGradient(QPointF(0, i * w), QPointF(0, (i + 1) * w))
            band.setColorAt(0.0, T.qc("#ffffff", 0))
            band.setColorAt(0.5, T.qc("#ffffff", 13))
            band.setColorAt(1.0, T.qc("#ffffff", 0))
            p.fillRect(QRectF(-r * 1.3, i * w, r * 2.6, w), band)
        p.restore()
        p.strokePath(path, QPen(T.qc("#9284ba", 150), max(1.0, r * 0.006)))   # polished bevel
        p.strokePath(path, QPen(T.qc("#07060a", 230), 0.8))

    def _paint_over(self, p: QPainter, r: float, day) -> None:
        G = self._gears

        def rim(deg: float, rr: float = DIAL - 0.02) -> tuple[float, float]:
            return rr * math.cos(math.radians(deg)), rr * math.sin(math.radians(deg))

        def piv(name: str) -> tuple[float, float]:
            return G[name].x, G[name].y

        def bridge(points, bosses):
            return bridge_path([(x * r, y * r) for x, y in points], 0.062 * r,
                               [(x * r, y * r, 0.052 * r) for x, y in bosses])

        arch = bridge([rim(-118), (-0.27, -0.585), (0.27, -0.585), rim(-62)], [])
        right = bridge([rim(-62), piv("fourth"), piv("third")], [piv("fourth"), piv("third")])
        left = bridge([rim(-118), piv("crown"), piv("left")], [piv("crown"), piv("left")])
        low_r = bridge([piv("lower_r"), rim(62)], [piv("lower_r")])
        low_l = bridge([piv("lower_l"), rim(118)], [piv("lower_l")])
        for path in (low_r, low_l, left, right, arch):
            self._paint_bridge(p, path, r)
        for name in ("fourth", "third", "crown", "left", "lower_r", "lower_l"):
            draw_jewel(p, QPointF(G[name].x * r, G[name].y * r), 0.019 * r)
        for deg in (-118, -62, 62, 118):
            x, y = rim(deg, DIAL - 0.035)
            T.draw_screw(p, QPointF(x * r, y * r), 0.02 * r, angle=math.radians(deg * 1.7))

        brand = T.font(r * 0.05, "semibold", condensed=True, spacing=r * 0.012)
        _text_centered(p, "CHRONO-MECH", brand, T.qc("#000000", 160), QPointF(r * 0.003, -0.582 * r))
        _text_centered(p, "CHRONO-MECH", brand, T.TEXT, QPointF(0, -0.586 * r))
        _text_centered(p, "SKELETON TOURBILLON CHRONOGRAPH", T.font(r * 0.021, "regular", spacing=r * 0.004),
                       T.qc(T.VIOLET_HI, 200), QPointF(0, -0.505 * r))

        self._paint_subdial(p, QPointF(-SUB_D * r, 0), SUB_R * r, "24h")
        self._paint_subdial(p, QPointF(SUB_D * r, 0), SUB_R * r, "chrono")
        self._paint_tourbillon_frame(p, QPointF(0, TB_D * r), TB_R * r, r)
        a1, a2 = math.radians(45), math.radians(135)
        self._paint_window(p, QPointF(math.cos(a1) * DATE_D * r, math.sin(a1) * DATE_D * r), f"{day.day:02d}", r)
        self._paint_window(p, QPointF(math.cos(a2) * DATE_D * r, math.sin(a2) * DATE_D * r),
                           ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")[day.weekday()], r)
        self._paint_chapter(p, r)
        self._paint_bezel(p, r)
        p.strokePath(self._paths["hud_ticks"], QPen(T.qc(T.LINE_HI, 220), 1.0))    # static HUD scale

    def _paint_subdial(self, p: QPainter, c: QPointF, sr: float, kind: str) -> None:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(T.qc("#000000", 170))
        p.drawEllipse(c + QPointF(sr * 0.03, sr * 0.07), sr * 1.04, sr * 1.04)
        p.setBrush(_metal_ring_gradient(c))
        p.drawEllipse(c, sr, sr)
        face = QRadialGradient(c, sr)
        face.setColorAt(0.0, QColor("#16121d"))
        face.setColorAt(1.0, QColor("#0a0810"))
        p.setBrush(face)
        p.drawEllipse(c, sr * 0.92, sr * 0.92)
        p.setBrush(Qt.BrushStyle.NoBrush)
        for i in range(1, 20):                      # snailed (concentric) finish
            p.setPen(QPen(T.qc("#ffffff", 11 if i % 2 else 5), 0.6))
            p.drawEllipse(c, sr * 0.9 * i / 20, sr * 0.9 * i / 20)
        band_r = sr * 0.80
        rect = QRectF(c.x() - band_r, c.y() - band_r, 2 * band_r, 2 * band_r)
        flat = Qt.PenCapStyle.FlatCap
        if kind == "24h":
            p.setPen(QPen(T.qc(T.VIOLET_DEEP, 255), sr * 0.11, Qt.PenStyle.SolidLine, flat))
            p.drawArc(rect, -180 * 16, -180 * 16)          # night: 18h → 24h → 6h
            p.setPen(QPen(T.qc("#3b3152", 150), sr * 0.11, Qt.PenStyle.SolidLine, flat))
            p.drawArc(rect, 0, -180 * 16)                  # day
            n, major, labels = 24, 6, {6: "6", 18: "18"}
        else:
            p.setPen(QPen(T.qc(T.VIOLET_DEEP, 200), sr * 0.11, Qt.PenStyle.SolidLine, flat))
            p.drawArc(rect, 0, 360 * 16)
            n, major, labels = 30, 5, {10: "10", 20: "20", 0: "30"}
        ticks_major, ticks_minor = QPainterPath(), QPainterPath()
        for i in range(n):
            a = T.clock_angle(i / n)
            big = i % major == 0
            target = ticks_major if big else ticks_minor
            target.moveTo(T.polar(c.x(), c.y(), sr * (0.70 if big else 0.76), a))
            target.lineTo(T.polar(c.x(), c.y(), sr * 0.86, a))
        p.strokePath(ticks_minor, QPen(T.qc(T.TEXT_DIM, 170), max(0.7, sr * 0.012)))
        p.strokePath(ticks_major, QPen(T.qc(T.VIOLET_HI), max(1.0, sr * 0.028)))
        f = T.font(sr * 0.17, "semibold", condensed=True)
        for i, text in labels.items():
            _text_centered(p, text, f, T.TEXT, T.polar(c.x(), c.y(), sr * 0.52, T.clock_angle(i / n)))
        caption = T.font(sr * 0.12, "semibold", spacing=sr * 0.02)
        if kind == "24h":    # moon at midnight, sun at noon
            mc = c + QPointF(0, -sr * 0.50)
            moon = QPainterPath()
            moon.addEllipse(mc, sr * 0.09, sr * 0.09)
            bite = QPainterPath()
            bite.addEllipse(mc + QPointF(sr * 0.05, -sr * 0.03), sr * 0.08, sr * 0.08)
            p.fillPath(moon.subtracted(bite), T.qc(T.VIOLET_HI))
            sc = c + QPointF(0, sr * 0.50)
            p.setPen(QPen(T.qc(T.TEXT_DIM), max(0.7, sr * 0.02)))
            for k in range(8):
                a = k * TAU / 8
                p.drawLine(T.polar(sc.x(), sc.y(), sr * 0.08, a), T.polar(sc.x(), sc.y(), sr * 0.12, a))
            p.setBrush(T.qc(T.TEXT_DIM))
            p.drawEllipse(sc, sr * 0.05, sr * 0.05)
            _text_centered(p, "24H", caption, T.qc(T.VIOLET_HI, 210), c + QPointF(0, sr * 0.26))
        else:
            _text_centered(p, "MIN", T.font(sr * 0.11, "regular", spacing=sr * 0.02),
                           T.TEXT_DIM, c + QPointF(0, -sr * 0.27))
            _text_centered(p, "CHRONO", caption, T.qc(T.VIOLET_HI, 210), c + QPointF(0, sr * 0.55))

    def _paint_tourbillon_frame(self, p: QPainter, c: QPointF, ar: float, r: float) -> None:
        p.fillPath(_annulus(ar * 1.13, ar * 0.99, c + QPointF(ar * 0.03, ar * 0.06)), T.qc("#000000", 150))
        ring = _annulus(ar * 1.12, ar)
        ring.translate(c)
        p.fillPath(ring, _metal_ring_gradient(c, 120))
        p.strokePath(ring, QPen(T.qc("#07060a"), 0.8))
        # fixed fourth wheel with internal teeth the cage's pinion rolls around
        teeth = QPainterPath()
        teeth.setFillRule(Qt.FillRule.OddEvenFill)
        teeth.addEllipse(c, ar * 1.0, ar * 1.0)
        inner = gear_outline(72, ar * 0.95, "spur")
        inner.translate(c)
        teeth.addPolygon(inner)
        p.fillPath(teeth, T.qc("#2a2438"))
        p.strokePath(teeth, QPen(T.qc("#6a5f88", 140), 0.6))
        ticks, majors = QPainterPath(), QPainterPath()
        for i in range(60):
            a = T.clock_angle(i / 60)
            path = majors if i % 15 == 0 else ticks
            path.moveTo(T.polar(c.x(), c.y(), ar * 1.025, a))
            path.lineTo(T.polar(c.x(), c.y(), ar * (1.09 if i % 5 == 0 else 1.06), a))
        p.strokePath(ticks, QPen(T.qc("#0b0910", 220), max(0.6, ar * 0.012)))
        p.strokePath(majors, QPen(T.qc(T.VIOLET_HI), max(1.0, ar * 0.022)))
        _text_centered(p, "60 SEC", T.font(r * 0.022, "semibold", spacing=r * 0.004),
                       T.qc(T.TEXT_DIM, 220), c + QPointF(0, ar * 1.27))

    def _paint_window(self, p: QPainter, c: QPointF, text: str, r: float) -> None:
        w, h = 0.14 * r, 0.082 * r
        outer = T.chamfer_path(QRectF(c.x() - w / 2 - r * 0.014, c.y() - h / 2 - r * 0.014,
                                      w + r * 0.028, h + r * 0.028), r * 0.014, tl=True, tr=True, br=True, bl=True)
        p.fillPath(outer.translated(r * 0.006, r * 0.012), T.qc("#000000", 150))
        frame = QLinearGradient(outer.boundingRect().topLeft(), outer.boundingRect().bottomRight())
        frame.setColorAt(0.0, QColor("#6d6289"))
        frame.setColorAt(0.5, QColor("#2a2538"))
        frame.setColorAt(1.0, QColor("#4a4262"))
        p.fillPath(outer, frame)
        inner = QRectF(c.x() - w / 2, c.y() - h / 2, w, h)
        p.fillRect(inner, QColor("#08070c"))
        p.fillRect(QRectF(inner.left(), inner.top(), inner.width(), h * 0.18), T.qc("#000000", 160))
        _text_centered(p, text, T.font(h * 0.68, "semibold", spacing=r * 0.004), T.VIOLET_HI, c)

    def _paint_chapter(self, p: QPainter, r: float) -> None:
        ring = _annulus(0.858 * r, DIAL * r)
        g = QRadialGradient(QPointF(0, 0), 0.858 * r)
        g.setColorAt(0.9, QColor("#0d0a12"))
        g.setColorAt(1.0, QColor("#19141f"))
        p.fillPath(ring, g)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(T.qc("#5d5379", 200), max(1.0, r * 0.004)))
        p.drawEllipse(QPointF(0, 0), DIAL * r, DIAL * r)
        fine, minute, five = QPainterPath(), QPainterPath(), QPainterPath()
        for i in range(300):
            a = T.clock_angle(i / 300)
            if i % 25 == 0:
                target, r0 = five, 0.812
            elif i % 5 == 0:
                target, r0 = minute, 0.826
            else:
                target, r0 = fine, 0.842
            target.moveTo(T.polar(0, 0, r0 * r, a))
            target.lineTo(T.polar(0, 0, 0.852 * r, a))
        p.strokePath(fine, QPen(T.qc(T.TEXT_FAINT, 200), 0.6))
        p.strokePath(minute, QPen(T.qc(T.TEXT_DIM), max(0.8, r * 0.0035)))
        p.strokePath(five, QPen(T.qc(T.VIOLET_HI), max(1.2, r * 0.007)))

        # applied hour indices: faceted metal frame with luminous core
        for i in range(12):
            r1, r0 = 0.792, (0.715 if i not in (3, 6, 9) else 0.735)
            for off in ((-0.013, 0.013) if i == 0 else (0.0,)):
                p.save()
                p.rotate(i * 30.0)
                p.translate(off * r, 0)
                hw0, hw1 = 0.011 * r, 0.0145 * r
                frame = QPolygonF([QPointF(-hw0, -r0 * r), QPointF(-hw1, -r1 * r),
                                   QPointF(hw1, -r1 * r), QPointF(hw0, -r0 * r)])
                shadow = QPainterPath()
                shadow.addPolygon(frame)
                p.fillPath(shadow.translated(r * 0.004, r * 0.008), T.qc("#000000", 160))
                left = QPainterPath()
                left.addPolygon(QPolygonF([frame[0], frame[1], QPointF(0, -r1 * r), QPointF(0, -r0 * r)]))
                right = QPainterPath()
                right.addPolygon(QPolygonF([QPointF(0, -r0 * r), QPointF(0, -r1 * r), frame[2], frame[3]]))
                p.fillPath(left, QColor("#9c90c2"))
                p.fillPath(right, QColor("#3e3656"))
                lume = QPainterPath()
                lume.addRect(QRectF(-hw0 * 0.45, -(r1 - 0.012) * r, hw0 * 0.9, (r1 - r0 - 0.024) * r))
                T.glow_stroke(p, lume, T.qc(T.VIOLET, 180), width=0.5, radius=r * 0.018, strength=1.4)
                p.fillPath(lume, T.qc(T.VIOLET_HI))
                p.restore()

    def _paint_bezel(self, p: QPainter, r: float) -> None:
        p.fillPath(_annulus(0.955 * r, 0.858 * r), QColor("#0b0910"))
        insert = _annulus(0.932 * r, 0.873 * r)
        ig = QRadialGradient(QPointF(0, 0), 0.932 * r)
        ig.setColorAt(0.93, QColor("#120f19"))
        ig.setColorAt(1.0, QColor("#1c1726"))
        p.fillPath(insert, ig)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(T.qc("#3a3350"), 0.8))
        p.drawEllipse(QPointF(0, 0), 0.873 * r, 0.873 * r)
        p.drawEllipse(QPointF(0, 0), 0.932 * r, 0.932 * r)
        p.setPen(QPen(T.qc("#000000", 230), 0.012 * r))        # groove for the seconds glow
        p.drawEllipse(QPointF(0, 0), 0.865 * r, 0.865 * r)
        f = T.font(r * 0.042, "semibold", condensed=True)       # dive-style scale
        marks = QPainterPath()
        for minute in range(1, 60):
            a = T.clock_angle(minute / 60)
            if minute % 10 == 0:
                p.save()
                p.rotate(minute * 6)
                _text_centered(p, str(minute), f, T.qc(T.TEXT_DIM), QPointF(0, -0.902 * r))
                p.restore()
            elif minute % 5 == 0:
                marks.addEllipse(T.polar(0, 0, 0.902 * r, a), 0.0075 * r, 0.0075 * r)
            elif minute < 15:
                marks.moveTo(T.polar(0, 0, 0.888 * r, a))
                marks.lineTo(T.polar(0, 0, 0.916 * r, a))
        p.strokePath(marks, QPen(T.qc(T.TEXT_DIM, 200), max(0.8, r * 0.004)))
        tri = QPainterPath()
        tri.addPolygon(QPolygonF([QPointF(0, -0.882 * r), QPointF(-0.024 * r, -0.925 * r),
                                  QPointF(0.024 * r, -0.925 * r)]))
        tri.closeSubpath()
        T.glow_stroke(p, tri, T.qc(T.VIOLET, 200), width=0.8, radius=r * 0.02, strength=1.3)
        p.fillPath(tri, T.qc(T.VIOLET_HI))
        knurl = QPainterPath()                                   # knurled grip
        knurl.setFillRule(Qt.FillRule.OddEvenFill)
        knurl.addPolygon(QPolygonF([T.polar(0, 0, (0.955 if i % 2 == 0 else 0.942) * r, i * TAU / 180)
                                    for i in range(180)]))
        knurl.closeSubpath()
        knurl.addEllipse(QPointF(0, 0), 0.934 * r, 0.934 * r)
        p.fillPath(knurl, _metal_ring_gradient(QPointF(0, 0), 60))
        p.strokePath(knurl, QPen(T.qc("#06050a", 200), 0.6))
        p.setPen(QPen(T.qc(T.LINE_HI), 1.0))
        p.drawEllipse(QPointF(0, 0), 0.965 * r, 0.965 * r)

    def _paint_glass(self, p: QPainter, r: float) -> None:
        dial = QPainterPath()
        dial.addEllipse(QPointF(0, 0), 0.858 * r, 0.858 * r)
        cut = QPainterPath()
        cut.addEllipse(QPointF(0.22 * r, 0.30 * r), 0.95 * r, 0.95 * r)
        g = QLinearGradient(QPointF(-0.6 * r, -0.8 * r), QPointF(0.1 * r, 0.1 * r))
        g.setColorAt(0.0, T.qc("#ffffff", 30))
        g.setColorAt(1.0, T.qc("#ffffff", 0))
        p.fillPath(dial.subtracted(cut), g)
        v = QRadialGradient(QPointF(0, 0), 0.858 * r)
        v.setColorAt(0.88, T.qc("#000000", 0))
        v.setColorAt(1.0, T.qc("#000000", 120))
        p.fillPath(dial, v)

    # ── frame composition ──
    def paintEvent(self, event) -> None:
        c, r = self.clock_geometry()
        now = self._frame_t if 0.0 <= time.time() - self._frame_t < 0.25 else time.time()
        rebuilt = self._ensure_layers(r, self.devicePixelRatioF(), datetime.fromtimestamp(now).date())
        s = r / self._built_r
        e = self._boot()
        m = self._motion(now, e)
        region = event.region()
        steady = e >= 1.0 and abs(s - 1.0) < 1e-6

        p = _begin(self)
        if steady:
            p.drawPixmap(QPointF(0, 0), self._ensure_base(c))
        else:                                       # boot sweep-in or live resize
            if self._backdrop is not None:
                self._backdrop(p, event.rect())
            else:
                p.fillRect(event.rect(), QColor(T.BG))
            self._blit(p, "under", c, s)
        for (g, pm, half), rect in zip(self._wheels, self._wheel_rects):
            if steady and not region.intersects(rect):
                continue
            p.save()
            p.translate(c.x() + g.x * r, c.y() + g.y * r)
            p.rotate(math.degrees(math.fmod(g.ratio * ROOT_OMEGA * m.train + g.phase, TAU)))
            p.scale(s, s)
            p.drawPixmap(QPointF(-half, -half), pm)
            p.restore()
        if region.intersects(self._tb_rect):
            self._paint_tourbillon(p, c, r, s, m.cage, now)
        if steady:
            if self._slow_key != m.slow:
                self._slow.fill(Qt.GlobalColor.transparent)
                sp = _begin(self._slow)
                self._paint_slow(sp, QPointF(self._half, self._half), r, 1.0, float(int(now)), 1.0)
                sp.end()
                self._slow_key = m.slow
            p.drawPixmap(QPointF(c.x() - self._half, c.y() - self._half), self._slow)
        else:
            self._paint_slow(p, c, r, s, now, e)
        self._paint_sweep(p, c, r, s, m, track=not self._tb_rect.contains(event.rect()))
        if not self._inner_rect.contains(event.rect()):
            self._paint_hud(p, c, r, m.hud, e)
        p.end()
        self._last = None if rebuilt else m

    def _ensure_base(self, c: QPointF) -> QPixmap:
        """Backdrop + movement plate composed once into an opaque image: one plain copy per
        paint instead of two alpha blends."""
        key = (self.size(), self._key, self._backdrop_version)
        if key != self._base_key:
            dpr = self.devicePixelRatioF()
            self._base = QPixmap(max(1, round(self.width() * dpr)), max(1, round(self.height() * dpr)))
            self._base.setDevicePixelRatio(dpr)
            self._base.fill(QColor(T.BG))
            p = _begin(self._base)
            if self._backdrop is not None:
                self._backdrop(p, self.rect())
            self._blit(p, "under", c, 1.0)
            p.end()
            self._base_key = key
        return self._base

    def _paint_tourbillon(self, p: QPainter, c: QPointF, r: float, s: float, t: float, now: float) -> None:
        """Aperture floor, then the carriage: escape wheel, pallet fork, balance, hairspring, cage."""
        ar = TB_R * r
        S = self._sprites
        beats = math.floor(now * ESCAPEMENT_BPS)
        balance = 150.0 * math.sin(TAU * (ESCAPEMENT_BPS / 2.0) * now)
        centre = QPointF(c.x(), c.y() + TB_D * r)
        p.save()
        p.translate(centre)
        floor = QRadialGradient(QPointF(0, 0), ar)
        floor.setColorAt(0.0, QColor("#1a1424"))
        floor.setColorAt(1.0, QColor("#050407"))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(floor)
        p.drawEllipse(QPointF(0, 0), ar * 1.005, ar * 1.005)
        p.rotate((t % 60.0) / 60.0 * 360.0)                    # the cage turns once a minute
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(T.qc("#4a4262"), ar * 0.05))
        p.drawEllipse(QPointF(0, 0), ar * 0.80, ar * 0.80)
        pm, half = self._escape                                 # escape wheel steps each beat
        p.save()
        p.translate(0, -0.56 * ar)
        p.rotate(beats * 12.0)
        p.scale(s, s)
        p.drawPixmap(QPointF(-half, -half), pm)
        p.restore()
        S["fork"].draw(p, QPointF(0, -0.30 * ar), 9.0 if beats % 2 else -9.0, s)   # pallet fork flicks
        S["balance"].draw(p, QPointF(0, 0), balance, s)
        p.save()                                                # hairspring breathes with the balance
        p.scale(s, s)
        p.setPen(QPen(T.qc(T.VIOLET_HI, 210), max(0.6, ar * 0.012)))
        idx = round((math.radians(balance) * 0.9 / self._twist_max + 1) * 40)
        p.drawPolyline(self._spirals[max(0, min(80, idx))])
        p.restore()
        S["cage"].draw(p, QPointF(0, 0), 0.0, s)
        p.restore()
        S["tb_jewel"].draw(p, centre, 0.0, s)

    def _paint_slow(self, p: QPainter, c: QPointF, r: float, s: float, when: float, e: float) -> None:
        """The over layer plus everything that moves too slowly to need per-frame updates."""
        local = datetime.fromtimestamp(when)
        day_secs = local.hour * 3600 + local.minute * 60 + local.second + local.microsecond / 1e6
        S = self._sprites
        self._blit(p, "over", c, s)
        self._paint_timer_bezel(p, c, r, when)
        chrono_min = (self._sw.elapsed() / 60.0) % 30.0
        sub_shadow = QPointF(SUB_R * r * 0.03, SUB_R * r * 0.05)
        for pos, deg, sprite in ((QPointF(-SUB_D * r, 0), day_secs / 86400.0 * 360.0 * e, "small_violet"),
                                 (QPointF(SUB_D * r, 0), chrono_min / 30.0 * 360.0, "small_magenta")):
            S["small_shadow"].draw(p, c + pos + sub_shadow, deg, s)
            S[sprite].draw(p, c + pos, deg, s)
        shadow = c + QPointF(r * 0.007, r * 0.013)
        for name, deg in (("hour", (day_secs / 3600.0) % 12.0 / 12.0 * 360.0 * e),
                          ("minute", (day_secs / 60.0) % 60.0 / 60.0 * 360.0 * e)):
            S[name + "_shadow"].draw(p, shadow, deg, s)
            S[name].draw(p, c, deg, s)
        self._blit(p, "glass", c, s)

    def _paint_sweep(self, p: QPainter, c: QPointF, r: float, s: float, m: Motion, track: bool) -> None:
        """Seconds track, chronograph & seconds hands and the centre cap: the fast movers."""
        S = self._sprites
        if track and m.sec > 0.0005:
            p.save()
            p.translate(c)
            p.setClipPath(_sector(0.84 * r, 0.9 * r, 90.0, -m.sec * 360.0))
            p.scale(s, s)
            p.drawPixmap(QPointF(-self._half, -self._half), self._layers["sec_ring"])
            p.restore()
        head = T.polar(c.x(), c.y(), 0.865 * r, T.clock_angle(m.sec))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(T.qc(T.VIOLET, 70))
        p.drawEllipse(head, r * 0.018, r * 0.018)
        p.setBrush(QColor("#f3ebff"))
        p.drawEllipse(head, r * 0.007, r * 0.007)
        p.save()
        p.translate(c)
        p.rotate(m.sec * 360.0)
        p.setBrush(T.qc(T.VIOLET_HI))
        p.drawPolygon(QPolygonF([QPointF(0, -0.968 * r), QPointF(-0.013 * r, -0.995 * r),
                                 QPointF(0.013 * r, -0.995 * r)]))
        p.restore()

        shadow = c + QPointF(r * 0.007, r * 0.013)
        hands = [] if m.chrono is None else [("chrono", m.chrono * 360.0)]
        hands.append(("seconds", m.sec * 360.0))
        for name, deg in hands:
            S[name + "_shadow"].draw(p, shadow, deg, s)
            S[name].draw(p, c, deg, s)
        S["cap"].draw(p, c, 0.0, s)

    def _paint_timer_bezel(self, p: QPainter, c: QPointF, r: float, t: float) -> None:
        """Project the countdown on the bezel the way a diver sets a dive bezel."""
        end = self._cd.end_epoch()
        if end is None:
            return
        local = datetime.fromtimestamp(t)
        start = (local.minute + local.second / 60.0 + local.microsecond / 6e7) / 60.0
        span = min(1.0, max(0.0, end - t) / 3600.0)
        alpha = 50 if self._cd.state == Countdown.PAUSED else 95
        rr = 0.9025 * r
        p.setPen(QPen(T.qc(T.VIOLET, alpha), 0.058 * r, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(QRectF(c.x() - rr, c.y() - rr, 2 * rr, 2 * rr),
                  round((90 - start * 360) * 16), round(-span * 360 * 16))
        p.save()
        p.translate(c)
        p.rotate((start + span) * 360.0)
        tri = QPainterPath()
        tri.addPolygon(QPolygonF([QPointF(0, -0.875 * r), QPointF(-0.02 * r, -0.935 * r),
                                  QPointF(0.02 * r, -0.935 * r)]))
        tri.closeSubpath()
        T.glow_stroke(p, tri, T.qc(T.MAGENTA, 200), width=0.8, radius=r * 0.02)
        p.fillPath(tri, T.qc("#f5d6ff"))
        p.restore()

    def _paint_hud(self, p: QPainter, c: QPointF, r: float, rot: float, e: float) -> None:
        """Glowing arcs that orbit the bezel: a fixed glow ring shown through rotating sectors,
        so its pixels never change and only the arc ends need repainting."""
        p.save()
        p.translate(c)
        p.scale(r / self._built_r, r / self._built_r)
        p.setOpacity(e)
        p.rotate(-rot)
        p.setClipPath(self._paths["hud_clip"])
        p.rotate(rot)
        p.drawPixmap(QPointF(-self._half, -self._half), self._layers["hud_ring"])
        p.restore()
