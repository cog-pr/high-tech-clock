"""07 · SYSTEM — CPU / memory / disk / network / power telemetry via psutil."""
from __future__ import annotations

import math
import os
import sys
import threading
import time
from collections import deque

from PySide6.QtCore import QObject, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from ... import theme as T
from ..widgets import HudPanel

try:
    import psutil
except ImportError:          # the panel degrades gracefully without it
    psutil = None


def fmt_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit in ("B", "KB") else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def fmt_uptime(seconds: float) -> str:
    d, rem = divmod(int(seconds), 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    return f"{d}D {h:02d}:{m:02d}" if d else f"{h:02d}:{m:02d}"


class Telemetry(QObject):
    """Samples psutil once a second on a worker thread (some calls, e.g. network
    counters on Windows, take >10 ms and would otherwise stutter the animation)."""

    updated = Signal()
    _sampled = Signal(object)        # emitted by the worker, delivered queued on the GUI thread
    HISTORY = 90

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.available = psutil is not None
        self.cpu = 0.0
        self.cores: list[float] = []
        self.mem = (0.0, 0, 1)
        self.disk = (0.0, 0, 1)
        self.net = (0.0, 0.0)
        self.battery: tuple[float, bool] | None = None
        self.uptime = 0.0
        self.procs = 0
        self.cpu_hist: deque[float] = deque([0.0] * self.HISTORY, maxlen=self.HISTORY)
        self.down_hist: deque[float] = deque([0.0] * self.HISTORY, maxlen=self.HISTORY)
        self.up_hist: deque[float] = deque([0.0] * self.HISTORY, maxlen=self.HISTORY)
        self.disk_label = (os.environ.get("SystemDrive", "C:") if sys.platform == "win32" else "/")
        self._disk_path = self.disk_label + "\\" if sys.platform == "win32" else "/"
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._sampled.connect(self._apply)
        if self.available:
            self._thread = threading.Thread(target=self._run, name="telemetry", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    def _run(self) -> None:
        psutil.cpu_percent(None)
        psutil.cpu_percent(None, percpu=True)
        last_net, last_t, tick = None, 0.0, 0
        while not self._stop.wait(1.0):
            tick += 1
            snap: dict = {}
            try:
                snap["cpu"] = psutil.cpu_percent(None)
                snap["cores"] = psutil.cpu_percent(None, percpu=True)
                vm = psutil.virtual_memory()
                snap["mem"] = (vm.percent, vm.used, vm.total)
                net, now = psutil.net_io_counters(), time.monotonic()
                if net is not None and last_net is not None and now > last_t:
                    dt = now - last_t
                    snap["net"] = (max(0.0, (net.bytes_recv - last_net.bytes_recv) / dt),
                                   max(0.0, (net.bytes_sent - last_net.bytes_sent) / dt))
                last_net, last_t = net, now
                if tick % 5 == 1:                     # slow-moving values: every 5 s
                    du = psutil.disk_usage(self._disk_path)
                    snap["disk"] = (du.percent, du.used, du.total)
                    snap["uptime"] = time.time() - psutil.boot_time()
                    snap["procs"] = len(psutil.pids())
                    try:
                        bat = psutil.sensors_battery()
                    except Exception:
                        bat = None
                    snap["battery"] = (bat.percent, bool(bat.power_plugged)) if bat else None
            except Exception:
                pass
            if self._stop.is_set():
                break
            self._sampled.emit(snap)

    def _apply(self, snap: dict) -> None:
        for key in ("cpu", "cores", "mem", "net", "disk", "procs", "battery"):
            if key in snap:
                setattr(self, key, snap[key])
        self.uptime = snap.get("uptime", self.uptime + 1)
        self.cpu_hist.append(self.cpu)
        self.down_hist.append(self.net[0])
        self.up_hist.append(self.net[1])
        self.updated.emit()


class SystemView(QWidget):
    # name, weight, min width, priority (higher survives longer on narrow windows)
    MODULES = [("cpu", 0.9, 92, 9), ("cores", 1.0, 90, 2), ("scope", 1.9, 150, 5), ("mem", 1.25, 120, 8),
               ("disk", 1.05, 110, 4), ("net", 1.5, 140, 6), ("power", 1.0, 100, 3)]

    def __init__(self, telemetry: Telemetry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._t = telemetry
        self.setMinimumHeight(72)
        telemetry.updated.connect(self.update)
        self._f_label = T.font(9.5, "semibold", spacing=1.4)
        self._f_big = T.font(20, "semilight")
        self._f_mid = T.font(13, "regular")
        self._f_small = T.font(10, "regular")

    def _layout(self) -> list[tuple[str, QRectF]]:
        W, H = self.width(), self.height()
        mods = list(self.MODULES)
        gap = 14.0
        while mods and sum(m[2] for m in mods) + gap * (len(mods) - 1) > W:
            mods.remove(min(mods, key=lambda m: m[3]))
        free = W - gap * (len(mods) - 1)
        total_w = sum(m[1] for m in mods)
        out, x = [], 0.0
        for name, weight, _min_w, _prio in mods:
            w = free * weight / total_w
            out.append((name, QRectF(x, 0, w, H)))
            x += w + gap
        return out

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self._t.available:
            p.setFont(self._f_mid)
            p.setPen(T.qc(T.TEXT_DIM))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                       "psutil が見つかりません  ·  pip install psutil でシステム監視が有効になります")
            return
        layout = self._layout()
        for i, (name, r) in enumerate(layout):
            getattr(self, "_m_" + name)(p, r)
            if i < len(layout) - 1:
                x = r.right() + 7
                p.setPen(QPen(T.qc(T.LINE), 1))
                p.drawLine(QPointF(x, 6), QPointF(x, r.bottom() - 6))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(T.qc(T.VIOLET_LO))
                p.drawRect(QRectF(x - 1.5, r.center().y() - 1.5, 3, 3))

    # ── modules ──
    def _label(self, p: QPainter, r: QRectF, text: str) -> None:
        p.setFont(self._f_label)
        p.setPen(T.qc(T.TEXT_DIM))
        p.drawText(QPointF(r.left(), r.top() + 10), text)

    def _bar(self, p: QPainter, r: QRectF, frac: float, segments: int = 16) -> None:
        gap = 2.0
        sw = (r.width() - gap * (segments - 1)) / segments
        lit = frac * segments
        for k in range(segments):
            cell = QRectF(r.left() + k * (sw + gap), r.top(), sw, r.height())
            p.fillRect(cell, T.qc(T.VIOLET_DEEP, 120))
            level = max(0.0, min(1.0, lit - k))
            if level > 0:
                hot = frac > 0.9 and k >= segments * 0.85
                p.fillRect(QRectF(cell.left(), cell.top(), cell.width() * level, cell.height()),
                           T.qc(T.ALERT) if hot else T.mix(T.VIOLET_LO, T.VIOLET_HI, k / segments))

    def _m_cpu(self, p: QPainter, r: QRectF) -> None:
        side = min(r.width(), r.height()) - 4
        c = QPointF(r.left() + side / 2 + 2, r.center().y())
        rad = side / 2 - 4
        rect = QRectF(c.x() - rad, c.y() - rad, 2 * rad, 2 * rad)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(T.qc(T.VIOLET_DEEP, 200), 6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
        p.drawArc(rect, 225 * 16, -270 * 16)
        frac = self._t.cpu / 100
        if frac > 0:
            arc = QPainterPath()
            arc.arcMoveTo(rect, 225)
            arc.arcTo(rect, 225, -270 * frac)
            color = T.ALERT if frac > 0.9 else T.VIOLET
            p.strokePath(arc, QPen(T.qc(color, 60), 10, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
            p.strokePath(arc, QPen(T.qc(color), 5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
        for k in range(11):
            a = math.radians(225 - 27 * k)
            o = QPointF(math.cos(a), -math.sin(a))
            p.setPen(QPen(T.qc(T.TEXT_FAINT), 1))
            p.drawLine(c + o * (rad + 5), c + o * (rad + 8))
        T.draw_tabular(p, c.x(), c.y() + 6, f"{self._t.cpu:.0f}", T.font(rad * 0.62, "semilight"), T.TEXT,
                       Qt.AlignmentFlag.AlignHCenter)
        p.setFont(self._f_label)
        p.setPen(T.qc(T.TEXT_DIM))
        p.drawText(QRectF(c.x() - rad, c.y() + rad * 0.45, 2 * rad, 14), Qt.AlignmentFlag.AlignCenter, "CPU %")

    def _m_cores(self, p: QPainter, r: QRectF) -> None:
        cores = self._t.cores or [0.0]
        self._label(p, r, f"CORES · {len(cores)}")
        area = QRectF(r.left(), r.top() + 18, r.width(), r.height() - 22)
        n = len(cores)
        gap = 1.5 if n > 16 else 2.5
        bw = max(1.0, (area.width() - gap * (n - 1)) / n)
        for i, v in enumerate(cores):
            x = area.left() + i * (bw + gap)
            p.fillRect(QRectF(x, area.top(), bw, area.height()), T.qc(T.VIOLET_DEEP, 110))
            h = area.height() * v / 100
            g = QLinearGradient(0, area.bottom(), 0, area.top())
            g.setColorAt(0.0, QColor(T.VIOLET_LO))
            g.setColorAt(1.0, QColor(T.ALERT if v > 90 else T.VIOLET_HI))
            p.fillRect(QRectF(x, area.bottom() - h, bw, h), g)

    def _scope(self, p: QPainter, area: QRectF, values, vmax: float, color: str, fill: bool) -> None:
        n = len(values)
        if n < 2:
            return
        path = QPainterPath()
        for i, v in enumerate(values):
            pt = QPointF(area.left() + area.width() * i / (n - 1),
                         area.bottom() - area.height() * min(1.0, v / vmax if vmax else 0))
            if i == 0:
                path.moveTo(pt)
            else:
                path.lineTo(pt)
        if fill:
            under = QPainterPath(path)
            under.lineTo(area.bottomRight())
            under.lineTo(area.bottomLeft())
            under.closeSubpath()
            g = QLinearGradient(0, area.top(), 0, area.bottom())
            g.setColorAt(0.0, T.qc(color, 90))
            g.setColorAt(1.0, T.qc(color, 0))
            p.fillPath(under, g)
        p.strokePath(path, QPen(T.qc(color, 70), 3.5))
        p.strokePath(path, QPen(QColor(color), 1.2))

    def _grid(self, p: QPainter, area: QRectF) -> None:
        p.fillRect(area, T.qc("#07060b", 200))
        p.setPen(QPen(T.qc(T.LINE, 150), 1))
        for k in range(1, 4):
            y = area.top() + area.height() * k / 4
            p.drawLine(QPointF(area.left(), y), QPointF(area.right(), y))
        for k in range(1, 9):
            x = area.left() + area.width() * k / 9
            p.drawLine(QPointF(x, area.top()), QPointF(x, area.bottom()))
        p.setPen(QPen(T.qc(T.LINE_HI), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(area)

    def _m_scope(self, p: QPainter, r: QRectF) -> None:
        self._label(p, r, "CPU LOAD · 90 s")
        area = QRectF(r.left(), r.top() + 17, r.width(), r.height() - 20)
        self._grid(p, area)
        self._scope(p, area.adjusted(1, 3, -1, -1), list(self._t.cpu_hist), 100.0, T.VIOLET, True)

    def _m_mem(self, p: QPainter, r: QRectF) -> None:
        pct, used, total = self._t.mem
        self._label(p, r, "MEMORY")
        T.draw_tabular(p, r.left(), r.top() + 40, f"{pct:.0f}%", self._f_big, T.TEXT)
        p.setFont(self._f_small)
        p.setPen(T.qc(T.TEXT_DIM))
        p.drawText(QPointF(r.left(), r.top() + 57), f"{fmt_bytes(used)} / {fmt_bytes(total)}")
        self._bar(p, QRectF(r.left(), r.bottom() - 12, r.width(), 8), pct / 100)

    def _m_disk(self, p: QPainter, r: QRectF) -> None:
        pct, used, total = self._t.disk
        self._label(p, r, f"DISK {self._t.disk_label}")
        T.draw_tabular(p, r.left(), r.top() + 40, f"{pct:.0f}%", self._f_big, T.TEXT)
        p.setFont(self._f_small)
        p.setPen(T.qc(T.TEXT_DIM))
        p.drawText(QPointF(r.left(), r.top() + 57), f"{fmt_bytes(used)} / {fmt_bytes(total)}")
        self._bar(p, QRectF(r.left(), r.bottom() - 12, r.width(), 8), pct / 100, 12)

    def _m_net(self, p: QPainter, r: QRectF) -> None:
        down, up = self._t.net
        self._label(p, r, "NETWORK")
        p.setFont(self._f_mid)
        p.setPen(T.qc(T.VIOLET_HI))
        p.drawText(QPointF(r.left(), r.top() + 30), f"↓ {fmt_bytes(down)}/s")
        p.setPen(T.qc(T.MAGENTA))
        p.drawText(QPointF(r.left() + r.width() * 0.52, r.top() + 30), f"↑ {fmt_bytes(up)}/s")
        area = QRectF(r.left(), r.top() + 38, r.width(), r.height() - 41)
        self._grid(p, area)
        peak = max(max(self._t.down_hist), max(self._t.up_hist), 64 * 1024)
        self._scope(p, area.adjusted(1, 3, -1, -1), list(self._t.down_hist), peak, T.VIOLET, True)
        self._scope(p, area.adjusted(1, 3, -1, -1), list(self._t.up_hist), peak, T.MAGENTA, False)

    def _m_power(self, p: QPainter, r: QRectF) -> None:
        self._label(p, r, "POWER")
        bat = self._t.battery
        if bat:
            pct, plugged = bat
            T.draw_tabular(p, r.left(), r.top() + 40, f"{pct:.0f}%", self._f_big, T.TEXT)
            p.setFont(self._f_small)
            p.setPen(T.qc(T.VIOLET_HI if plugged else T.TEXT_DIM))
            p.drawText(QPointF(r.left() + 52, r.top() + 38), "⚡ AC" if plugged else "BATTERY")
        else:
            p.setFont(self._f_big)
            p.setPen(QColor(T.TEXT))
            p.drawText(QPointF(r.left(), r.top() + 40), "AC")
        p.setFont(self._f_small)
        p.setPen(T.qc(T.TEXT_DIM))
        p.drawText(QPointF(r.left(), r.top() + 57), f"UPTIME {fmt_uptime(self._t.uptime)}")
        p.drawText(QPointF(r.left(), r.top() + 71), f"PROC   {self._t.procs}")


class SystemPanel(HudPanel):
    def __init__(self, telemetry: Telemetry, parent: QWidget | None = None) -> None:
        super().__init__("07", "SYSTEM MONITOR", "システム", parent)
        self.view = SystemView(telemetry, self)
        self.body.addWidget(self.view)
        self.set_status("● LIVE" if telemetry.available else "OFFLINE",
                        T.VIOLET_HI if telemetry.available else T.TEXT_FAINT)
