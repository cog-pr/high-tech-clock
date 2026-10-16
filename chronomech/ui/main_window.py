"""Main window: the clock in the centre, function modules wired around it."""
from __future__ import annotations

import math

from PySide6.QtCore import (
    QByteArray,
    QEasingCurve,
    QEvent,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRect,
    QRectF,
    Qt,
    QTimer,
)
from PySide6.QtGui import QColor, QKeySequence, QPainter, QPen, QPixmap, QRadialGradient, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsOpacityEffect,
    QGridLayout,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME
from .. import theme as T
from ..core.alarms import AlarmManager
from ..core.chrono import Stopwatch
from ..core.countdown import Countdown
from ..core.engine import TimeEngine
from ..core.settings import Settings, config_dir
from ..core.sound import SoundSystem
from .clock import MechanicalClock
from .dialogs import AlarmDialog, CityDialog, HelpDialog, SettingsDialog, TimerSetDialog
from .digital import DigitalReadout
from .overlay import Alert, AlertOverlay
from .panels.alarm import AlarmPanel
from .panels.astro import AstroPanel
from .panels.calendar import CalendarPanel
from .panels.chrono import ChronoPanel
from .panels.metrics import TimeIndexPanel
from .panels.system import SystemPanel, Telemetry
from .panels.timer import TimerPanel, fmt_timer
from .panels.world import WorldClockPanel
from .titlebar import TitleBar
from .widgets import HudPanel


class Backdrop(QWidget):
    """Blueprint grid, halo and circuit traces linking every module to the clock (cached)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._cache: QPixmap | None = None
        self._clock: MechanicalClock | None = None
        self._left: list[QWidget] = []
        self._right: list[QWidget] = []
        self._f_tag = T.font(9, "semibold", mono=True)

    def set_targets(self, clock: MechanicalClock, left: list[QWidget], right: list[QWidget]) -> None:
        self._clock, self._left, self._right = clock, left, right
        self.invalidate()

    def invalidate(self) -> None:
        self._cache = None
        self.update()
        if self._clock is not None:          # the clock is opaque and paints our pixels itself
            self._clock.backdrop_changed()

    def resizeEvent(self, _event) -> None:
        self._cache = None

    def _ensure_cache(self) -> QPixmap:
        if (self._cache is None or self._cache.deviceIndependentSize().toSize() != self.size()
                or self._cache.devicePixelRatio() != self.devicePixelRatioF()):   # e.g. moved to another monitor
            self._cache = self._render()
        return self._cache

    def _blit(self, p: QPainter, target: QRectF, source: QRectF) -> None:
        cache = self._ensure_cache()
        dpr = cache.devicePixelRatio()
        p.drawPixmap(target, cache, QRectF(source.topLeft() * dpr, source.size() * dpr))

    def paint_behind(self, p: QPainter, child: QWidget, rect: QRect) -> None:
        """Paint the backdrop under `child` (rect in child coordinates). This lets the clock be
        an opaque widget, so its many small per-frame updates never repaint the window behind it."""
        self._blit(p, QRectF(rect), QRectF(rect.translated(child.mapTo(self, QPoint(0, 0)))))

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        r = QRectF(event.rect())
        self._blit(p, r, r)

    def _render(self) -> QPixmap:
        dpr = self.devicePixelRatioF()
        pm = QPixmap(max(1, round(self.width() * dpr)), max(1, round(self.height() * dpr)))
        pm.setDevicePixelRatio(dpr)
        pm.fill(QColor(T.BG))
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        p.setPen(QPen(QColor(T.BG_GRID), 1))
        for x in range(0, W, 24):
            p.drawLine(x, 0, x, H)
        for y in range(0, H, 24):
            p.drawLine(0, y, W, y)
        p.setPen(QPen(QColor(T.BG_GRID_MAJOR), 1))
        for x in range(0, W, 120):
            p.drawLine(x, 0, x, H)
        for y in range(0, H, 120):
            p.drawLine(0, y, W, y)
        clock = self._clock
        if clock is not None and clock.isVisible():
            c, r = clock.clock_geometry()
            c = QPointF(clock.mapTo(self, c.toPoint()))
            halo = QRadialGradient(c, r * 1.55)
            halo.setColorAt(0.0, T.qc(T.VIOLET, 46))
            halo.setColorAt(0.6, T.qc(T.VIOLET, 14))
            halo.setColorAt(1.0, T.qc(T.VIOLET, 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(halo)
            p.drawEllipse(c, r * 1.55, r * 1.55)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(T.qc(T.LINE, 200), 1, Qt.PenStyle.DashLine))
            p.drawEllipse(c, r * 1.07, r * 1.07)
            p.setPen(QPen(T.qc(T.LINE_HI, 120), 1))
            p.drawEllipse(c, r * 1.13, r * 1.13)
            for k in range(72):                   # radar ticks
                a = k * math.tau / 72
                r0 = r * (1.10 if k % 6 == 0 else 1.115)
                p.drawLine(T.polar(c.x(), c.y(), r0, a), T.polar(c.x(), c.y(), r * 1.13, a))
            self._traces(p, c, r)
        # corner brackets of the work area
        p.setPen(QPen(T.qc(T.VIOLET_LO), 1.5))
        for sx, sy in ((0, 0), (1, 0), (0, 1), (1, 1)):
            x, y = (4 if sx == 0 else W - 5), (4 if sy == 0 else H - 5)
            dx, dy = (16 if sx == 0 else -16), (16 if sy == 0 else -16)
            p.drawLine(QPointF(x, y), QPointF(x + dx, y))
            p.drawLine(QPointF(x, y), QPointF(x, y + dy))
        p.end()
        return pm

    def _traces(self, p: QPainter, c: QPointF, r: float) -> None:
        ring = r * 1.07
        p.setFont(self._f_tag)
        for side, panels in ((-1, self._left), (1, self._right)):
            for i, panel in enumerate(panels):
                if not panel.isVisible():
                    continue
                top_left = panel.mapTo(self, panel.rect().topLeft())
                y = top_left.y() + HudPanel.HEADER / 2 + 6
                x0 = top_left.x() + panel.width() + 2 if side < 0 else top_left.x() - 2
                dy = max(-ring * 0.92, min(ring * 0.92, y - c.y()))
                ex = c.x() + side * math.sqrt(max(0.0, ring * ring - dy * dy))
                end = QPointF(ex, c.y() + dy)
                elbow_x = x0 - side * 18
                knee = QPointF(elbow_x, y)
                # horizontal run, then a 45° dog-leg onto the ring
                run = abs(end.x() - elbow_x) - abs(end.y() - y)
                mid = QPointF(elbow_x - side * max(0.0, run), y)
                p.setPen(QPen(T.qc(T.LINE_HI, 200), 1))
                p.drawLine(QPointF(x0, y), knee)
                p.drawLine(knee, mid)
                p.drawLine(mid, end)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(T.qc(T.VIOLET_LO))
                p.drawRect(QRectF(x0 - 2.5 if side > 0 else x0 - 0.5, y - 2.5, 3, 5))
                p.setBrush(T.qc(T.VIOLET, 90))
                p.drawEllipse(end, 5, 5)
                p.setBrush(T.qc(T.VIOLET_HI))
                p.drawEllipse(end, 2.2, 2.2)
                p.setPen(T.qc(T.TEXT_FAINT))
                tag = f"CH-{(i + 1) if side < 0 else (i + 4):02d}"
                tx = knee.x() + (4 if side < 0 else -40)
                p.drawText(QPointF(tx, y - 5), tag)


class MainWindow(QWidget):
    GRIP = 6

    def __init__(self, settings: Settings) -> None:
        flags = (Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowSystemMenuHint
                 | Qt.WindowType.WindowMinMaxButtonsHint)
        super().__init__(None, flags)
        self.settings = settings
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(1020, 700)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)

        # ── models ──
        self.engine = TimeEngine(int(settings["fps"]), self)
        self.stopwatch = Stopwatch(self)
        self.countdown = Countdown(float(settings["timer_seconds"]), self)
        self.alarms = AlarmManager(settings, self)
        self.telemetry = Telemetry(self)
        self.sound = SoundSystem(config_dir() / "sounds", float(settings["volume"]), self)
        self.sound.tick_enabled = bool(settings["tick_sound"])

        # ── layout ──
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(0)
        self.titlebar = TitleBar(self)
        root.addWidget(self.titlebar)
        self.body = Backdrop(self)
        root.addWidget(self.body, 1)

        self.world = WorldClockPanel(settings)
        self.calendar = CalendarPanel()
        self.astro = AstroPanel(settings)
        self.chrono = ChronoPanel(self.stopwatch, self.engine)
        self.timer = TimerPanel(self.countdown, self.engine)
        self.alarm = AlarmPanel(self.alarms)
        self.system = SystemPanel(self.telemetry)
        self.index = TimeIndexPanel()
        self.clock = MechanicalClock(self.engine, self.stopwatch, self.countdown, settings)
        self.readout = DigitalReadout(self.engine)

        grid = QGridLayout(self.body)
        grid.setContentsMargins(16, 14, 16, 14)
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(14)
        self.left_col = self._column([(self.world, 7), (self.calendar, 6), (self.astro, 5)])
        self.right_col = self._column([(self.chrono, 6), (self.timer, 5), (self.alarm, 5)])
        center = QVBoxLayout()
        center.setSpacing(4)
        center.addWidget(self.clock, 1)
        center.addWidget(self.readout)
        self.bottom = QWidget()
        bl = QHBoxLayout(self.bottom)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(18)
        bl.addWidget(self.index, 3)
        bl.addWidget(self.system, 8)
        grid.addWidget(self.left_col, 0, 0)
        grid.addLayout(center, 0, 1)
        grid.addWidget(self.right_col, 0, 2)
        grid.addWidget(self.bottom, 1, 0, 1, 3)
        grid.setColumnStretch(1, 1)
        grid.setRowStretch(0, 1)
        self.body.set_targets(self.clock, [self.world, self.calendar, self.astro],
                              [self.chrono, self.timer, self.alarm])
        self.clock.set_backdrop(lambda p, rect: self.body.paint_behind(p, self.clock, rect))
        self.overlay = AlertOverlay(self.body)
        self._apply_display_prefs()

        # ── wiring ──
        tb = self.titlebar
        tb.min_btn.clicked.connect(self.showMinimized)
        tb.max_btn.clicked.connect(self.toggle_maximized)
        tb.close_btn.clicked.connect(self.close)
        tb.sound_btn.setChecked(self.sound.tick_enabled)
        tb.sound_btn.toggled.connect(self._set_tick)
        tb.pin_btn.setChecked(bool(settings["always_on_top"]))
        tb.pin_btn.toggled.connect(self._set_on_top)
        tb.focus_btn.toggled.connect(self._set_focus)
        tb.settings_btn.clicked.connect(self.open_settings)
        tb.help_btn.clicked.connect(lambda: HelpDialog(self).exec())
        self.world.add_requested.connect(self.add_city)
        self.alarm.add_requested.connect(lambda: self.edit_alarm(None))
        self.alarm.view.edit_requested.connect(self.edit_alarm)
        self.timer.custom_requested.connect(self.set_timer_custom)
        self.countdown.changed.connect(self._remember_timer)
        self.countdown.finished.connect(self._timer_done)
        self.alarms.triggered.connect(self._alarm_fired)
        self.overlay.dismissed.connect(self._alert_closed)
        self.overlay.snoozed.connect(self._alert_snoozed)
        self.engine.second.connect(self._on_second)
        self.engine.minute.connect(lambda _now: self.astro.refresh())
        self.engine.day.connect(self._on_day)
        self._shortcuts()

        self._restore_geometry()
        if settings["always_on_top"]:
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        tb.focus_btn.setChecked(bool(settings["focus_mode"]))
        self.engine.start()
        QTimer.singleShot(0, self._boot_sequence)

    # ── construction helpers ──
    @staticmethod
    def _column(items: list[tuple[QWidget, int]]) -> QWidget:
        col = QWidget()
        lay = QVBoxLayout(col)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)
        for w, stretch in items:
            lay.addWidget(w, stretch)
        return col

    def _shortcuts(self) -> None:
        def bind(keys: str, fn, dismisses_alert: bool = False) -> None:
            # shortcuts see keys before the overlay does, so they must route to it while it is up
            def run() -> None:
                if self.overlay.active:
                    if dismisses_alert:
                        self.overlay.dismiss()
                    return
                fn()

            sc = QShortcut(QKeySequence(keys), self)
            sc.setContext(Qt.ShortcutContext.WindowShortcut)
            sc.activated.connect(run)

        bind("Space", self.stopwatch.toggle, dismisses_alert=True)
        bind("L", self.stopwatch.lap)
        bind("R", lambda: None if self.stopwatch.running else self.stopwatch.reset())
        bind("T", self.countdown.toggle)
        bind("F", self.titlebar.focus_btn.toggle)
        bind("P", self.titlebar.pin_btn.toggle)
        bind("M", self.titlebar.sound_btn.toggle)
        bind("F11", self.toggle_fullscreen)
        bind("F1", lambda: HelpDialog(self).exec())
        bind("Ctrl+,", self.open_settings)
        bind("Ctrl+Q", self.close)
        bind("Esc", self._escape, dismisses_alert=True)

    def _boot_sequence(self) -> None:
        """Panels power up one after another while the clock hands sweep into place."""
        self.clock.restart_boot()
        self._fx = []
        order = [self.world, self.chrono, self.calendar, self.timer, self.astro, self.alarm, self.index, self.system]
        for i, w in enumerate(order):
            fx = QGraphicsOpacityEffect(w)
            fx.setOpacity(0.0)
            w.setGraphicsEffect(fx)
            anim = QPropertyAnimation(fx, b"opacity", self)
            anim.setDuration(420)
            anim.setStartValue(0.0)
            anim.setEndValue(1.0)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            anim.finished.connect(lambda w=w: w.setGraphicsEffect(None))   # effects cost per paint
            QTimer.singleShot(250 + i * 90, anim.start)
            self._fx.append(anim)

    # ── window chrome ──
    def toggle_maximized(self) -> None:
        if self.isFullScreen():
            return
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self._leave_fullscreen()
        else:
            self._was_maximized = self.isMaximized()
            self.showFullScreen()

    def _leave_fullscreen(self) -> None:
        if getattr(self, "_was_maximized", False):
            self.showMaximized()
        else:
            self.showNormal()

    def _escape(self) -> None:
        if self.isFullScreen():
            self._leave_fullscreen()
        elif self.titlebar.focus_btn.isChecked():
            self.titlebar.focus_btn.setChecked(False)

    def _edges(self, pos) -> Qt.Edge:
        if self.isMaximized() or self.isFullScreen():
            return Qt.Edge(0)
        g, w, h = self.GRIP, self.width(), self.height()
        edges = Qt.Edge(0)
        if pos.x() <= g:
            edges |= Qt.Edge.LeftEdge
        elif pos.x() >= w - g:
            edges |= Qt.Edge.RightEdge
        if pos.y() <= g:
            edges |= Qt.Edge.TopEdge
        elif pos.y() >= h - g:
            edges |= Qt.Edge.BottomEdge
        return edges

    def mouseMoveEvent(self, event) -> None:
        e = self._edges(event.position().toPoint())
        L, R, Tp, B = Qt.Edge.LeftEdge, Qt.Edge.RightEdge, Qt.Edge.TopEdge, Qt.Edge.BottomEdge
        if e in (L | Tp, R | B):
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif e in (R | Tp, L | B):
            self.setCursor(Qt.CursorShape.SizeBDiagCursor)
        elif e in (L, R):
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        elif e in (Tp, B):
            self.setCursor(Qt.CursorShape.SizeVerCursor)
        else:
            self.unsetCursor()

    def mousePressEvent(self, event) -> None:
        edges = self._edges(event.position().toPoint())
        if event.button() == Qt.MouseButton.LeftButton and edges and self.windowHandle():
            self.windowHandle().startSystemResize(edges)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(T.BG))
        p.setPen(QPen(T.qc(T.LINE_HI), 1))
        p.drawRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5))
        p.setPen(QPen(T.qc(T.VIOLET), 2))
        w, h = self.width(), self.height()
        for x, y, dx, dy in ((1, 1, 26, 26), (w - 1, 1, -26, 26), (1, h - 1, 26, -26), (w - 1, h - 1, -26, -26)):
            p.drawLine(QPointF(x, y), QPointF(x + dx, y))
            p.drawLine(QPointF(x, y), QPointF(x, y + dy))

    def changeEvent(self, event) -> None:
        if event.type() == QEvent.Type.WindowStateChange:
            self.titlebar.set_maximized(self.isMaximized() or self.isFullScreen())
            self.engine.set_active(not self.isMinimized())
            QTimer.singleShot(0, self.body.invalidate)
        super().changeEvent(event)

    def resizeEvent(self, event) -> None:
        side = int(max(272, min(360, self.width() * 0.215)))
        self.left_col.setFixedWidth(side)
        self.right_col.setFixedWidth(side)
        self.bottom.setFixedHeight(int(max(128, min(168, self.height() * 0.17))))
        super().resizeEvent(event)

    def showEvent(self, event) -> None:
        self.engine.set_active(True)
        super().showEvent(event)

    def hideEvent(self, event) -> None:
        self.engine.set_active(False)
        super().hideEvent(event)

    def _restore_geometry(self) -> None:
        geo = self.settings["geometry"]
        if isinstance(geo, str) and geo:
            if self.restoreGeometry(QByteArray.fromBase64(geo.encode())):
                return
        screen = QApplication.primaryScreen()
        avail = screen.availableGeometry() if screen else None
        if avail is None:
            self.resize(1440, 900)
            return
        w = int(min(1500, avail.width() * 0.92))
        h = int(min(940, avail.height() * 0.92))
        self.resize(max(self.minimumWidth(), w), max(self.minimumHeight(), h))
        self.move(avail.center().x() - self.width() // 2, avail.center().y() - self.height() // 2)

    def closeEvent(self, event) -> None:
        self.settings["geometry"] = bytes(self.saveGeometry().toBase64()).decode()
        self.settings.save()
        self.sound.stop_alarm()
        self.telemetry.stop()
        super().closeEvent(event)

    # ── behaviour ──
    def _on_second(self, now) -> None:
        self.countdown.poll()
        self.alarms.check(now)
        self.sound.tick()
        self.world.refresh()
        self.index.refresh()
        self.alarm.refresh()
        self.titlebar.blink()

    def _on_day(self, now) -> None:
        self.calendar.view.set_today(now.date())
        self.astro.refresh()

    def _set_tick(self, on: bool) -> None:
        self.sound.tick_enabled = on
        self.settings["tick_sound"] = on
        self.settings.save()

    def _set_on_top(self, on: bool) -> None:
        if bool(self.windowFlags() & Qt.WindowType.WindowStaysOnTopHint) != on:
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, on)
            self.show()
        self.settings["always_on_top"] = on
        self.settings.save()

    def _set_focus(self, on: bool) -> None:
        for w in (self.left_col, self.right_col, self.bottom):
            w.setVisible(not on)
        self.settings["focus_mode"] = on
        self.settings.save()
        QTimer.singleShot(0, self.body.invalidate)

    def _apply_display_prefs(self) -> None:
        use_24h = bool(self.settings["use_24h"])
        for view in (self.world.view, self.alarm.view, self.astro.view, self.readout):
            view.use_24h = use_24h
        self.readout.refresh(self.engine.now())
        self.engine.set_fps(int(self.settings["fps"]))
        self.sound.set_volume(float(self.settings["volume"]))
        mode = {"mechanical": "MECH 21 600 A/h", "smooth": "SMOOTH SWEEP", "quartz": "QUARTZ 1 Hz"}
        self.titlebar.mode = f"{mode.get(self.settings['sweep'], '')}   ·   {self.engine.fps} FPS"
        self.titlebar.update()
        self.astro.refresh()
        self.clock.invalidate()
        for w in (self.world, self.alarm, self.astro):
            w.update()

    def _remember_timer(self) -> None:
        if self.countdown.state == Countdown.IDLE and self.settings["timer_seconds"] != self.countdown.duration:
            self.settings["timer_seconds"] = self.countdown.duration
            self.settings.save()

    def open_settings(self) -> None:
        dlg = SettingsDialog(self.settings, self)
        if dlg.exec():
            dlg.apply()
            self.sound.tick_enabled = bool(self.settings["tick_sound"])
            self.titlebar.sound_btn.setChecked(self.sound.tick_enabled)
            self.titlebar.pin_btn.setChecked(bool(self.settings["always_on_top"]))
            self._apply_display_prefs()

    def add_city(self) -> None:
        dlg = CityDialog(self)
        if dlg.exec() and dlg.entry:
            self.settings["world_clocks"].append(dlg.entry)
            self.settings.save()
            self.world.refresh()

    def edit_alarm(self, alarm) -> None:
        dlg = AlarmDialog(alarm, bool(self.settings["use_24h"]), self)
        if not dlg.exec():
            return
        if dlg.deleted and alarm is not None:
            self.alarms.remove(alarm.id)
        elif alarm is None:
            self.alarms.add(dlg.result_alarm())
        else:
            self.alarms.update(dlg.result_alarm())

    def set_timer_custom(self) -> None:
        dlg = TimerSetDialog(self.countdown.duration, self)
        if dlg.exec() and dlg.seconds() > 0:
            self.countdown.set_duration(dlg.seconds())

    def _raise_alert(self, alert: Alert) -> None:
        self.sound.start_alarm()
        if self.isMinimized():
            self.showNormal()
        self.raise_()
        self.activateWindow()
        QApplication.alert(self, 0)
        self.overlay.push(alert)

    def _alarm_fired(self, alarm) -> None:
        h = alarm.hour if self.settings["use_24h"] else (alarm.hour % 12 or 12)
        suffix = "" if self.settings["use_24h"] else (" AM" if alarm.hour < 12 else " PM")
        self._raise_alert(Alert("ALARM", f"{h:02d}:{alarm.minute:02d}{suffix}", alarm.label or "アラーム", True, alarm))

    def _timer_done(self) -> None:
        self._raise_alert(Alert("TIMER COMPLETE", "00:00", f"{fmt_timer(self.countdown.duration)} のタイマーが終了しました",
                                False, "timer"))

    def _alert_closed(self, alert: Alert) -> None:
        if alert.payload == "timer" and self.countdown.state == Countdown.DONE:
            self.countdown.reset()
        if not self.overlay.active:
            self.sound.stop_alarm()

    def _alert_snoozed(self, alert: Alert) -> None:
        self.alarms.snooze(alert.payload, 5)
        if not self.overlay.active:
            self.sound.stop_alarm()
