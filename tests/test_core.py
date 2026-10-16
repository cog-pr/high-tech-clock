"""Core logic tests: `python -m unittest discover -s tests`"""
from __future__ import annotations

import math
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PySide6.QtCore import QCoreApplication

from chronomech.core.alarms import Alarm, AlarmManager
from chronomech.core.astro import moon_info, sun_info
from chronomech.core.chrono import Stopwatch
from chronomech.core.countdown import Countdown
from PySide6.QtCore import QPointF

from chronomech import theme as T
from chronomech.core.settings import Settings
from chronomech.ui.clock import HUD_ARCS, MODULE, ROOT_OMEGA, TRAIN, hud_edge_rects, needle_rects, quantise
from chronomech.ui.mechanics import solve_train

app = QCoreApplication.instance() or QCoreApplication([])


class GearTrainTest(unittest.TestCase):
    def test_meshing_wheels_stay_interlocked(self):
        """A tooth of the driver on the line of centres always faces a gap of the driven wheel:
        Np·(φ−θp)/2π + Nc·(φ+π−θc)/2π ≡ ½ (mod 1) for every moment t."""
        gears = {g.spec.name: g for g in solve_train(TRAIN, MODULE)}
        pairs = [(s.parent, s.name) for s in TRAIN if s.parent and s.angle is not None]
        self.assertGreater(len(pairs), 4)
        for t in (0.0, 1.7, 33.3, 1.79e9):
            for parent, child in pairs:
                p, c = gears[parent], gears[child]
                phi = math.atan2(c.y - p.y, c.x - p.x)
                tp = p.ratio * ROOT_OMEGA * t + p.phase
                tc = c.ratio * ROOT_OMEGA * t + c.phase
                u = p.spec.teeth * (phi - tp) / math.tau + c.spec.teeth * (phi + math.pi - tc) / math.tau
                frac = (u - 0.5) % 1.0
                self.assertLess(min(frac, 1 - frac), 1e-4, f"{parent}->{child} at t={t}")

    def test_wheels_are_tangent(self):
        gears = {g.spec.name: g for g in solve_train(TRAIN, MODULE)}
        for s in TRAIN:
            if s.parent and s.angle is not None:
                p, c = gears[s.parent], gears[s.name]
                self.assertAlmostEqual(math.hypot(c.x - p.x, c.y - p.y), p.r_pitch + c.r_pitch, places=9)


class SweepTest(unittest.TestCase):
    def test_quantise(self):
        self.assertEqual(quantise(12.3456, 0), 12.3456)             # smooth: untouched
        self.assertAlmostEqual(quantise(12.40, 6), 12 + 2 / 6)      # mechanical: 1/6 s beats
        self.assertEqual(quantise(12.99, 1), 12.0)                  # quartz: whole seconds

    def test_needle_rects_cover_the_hand(self):
        c, r = QPointF(400, 300), 250.0
        for frac in (0.0, 0.1, 0.125, 0.37, 0.5, 0.81):
            rects = needle_rects(c, r, frac, 0.22, 1.0, pad=4)
            a = T.clock_angle(frac)
            for k in range(-22, 101):                            # every point along the hand
                d = k / 100 * r
                pt = QPointF(c.x() + d * math.cos(a), c.y() + d * math.sin(a)).toPoint()
                self.assertTrue(any(rect.contains(pt) for rect in rects), (frac, k))

    def test_hud_edge_rects_cover_moving_arc_ends(self):
        c, r = QPointF(400, 400), 300.0
        rects = hud_edge_rects(c, r, 10.0, 10.4, pad=3)
        self.assertEqual(len(rects), 2 * len(HUD_ARCS))
        for start, span in HUD_ARCS:
            for edge in (start, start + span):
                for rot in (10.0, 10.2, 10.4):
                    phi = math.radians(edge + rot)
                    pt = QPointF(c.x() + 0.99 * r * math.cos(phi), c.y() - 0.99 * r * math.sin(phi)).toPoint()
                    self.assertTrue(any(rect.contains(pt) for rect in rects), (edge, rot))


class AlarmTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.settings = Settings(Path(self.tmp.name) / "s.json")

    def tearDown(self):
        self.tmp.cleanup()

    def test_next_occurrence_respects_weekdays(self):
        fri_evening = datetime(2026, 10, 16, 19, 0)          # Friday
        weekdays = Alarm(7, 0, days=[0, 1, 2, 3, 4])
        self.assertEqual(weekdays.next_occurrence(fri_evening), datetime(2026, 10, 19, 7, 0))   # Monday
        daily = Alarm(20, 30)
        self.assertEqual(daily.next_occurrence(fri_evening), datetime(2026, 10, 16, 20, 30))
        self.assertIsNone(Alarm(7, 0, enabled=False).next_occurrence(fri_evening))

    def test_fires_once_and_one_shot_disarms(self):
        m = AlarmManager(self.settings)
        fired = []
        m.triggered.connect(fired.append)
        once = Alarm(8, 15, days=[])
        m.add(once)
        for sec in range(0, 60, 7):
            m.check(datetime(2026, 10, 17, 8, 15, sec))
        self.assertEqual(len(fired), 1)
        self.assertFalse(once.enabled)
        reloaded = AlarmManager(Settings(self.settings.path))
        self.assertFalse(reloaded.alarms[0].enabled)

    def test_snooze(self):
        m = AlarmManager(self.settings)
        fired = []
        m.triggered.connect(fired.append)
        a = Alarm(9, 0)
        m.snooze(a, minutes=5)
        m.check(datetime.now() + timedelta(minutes=4))
        self.assertEqual(fired, [])
        m.check(datetime.now() + timedelta(minutes=6))
        self.assertEqual(fired, [a])


class CountdownTest(unittest.TestCase):
    def test_lifecycle(self):
        cd = Countdown(60)
        done = []
        cd.finished.connect(lambda: done.append(True))
        cd.start()
        self.assertEqual(cd.state, Countdown.RUNNING)
        cd.pause()
        left = cd.remaining()
        time.sleep(0.05)
        self.assertAlmostEqual(cd.remaining(), left, places=6)
        cd.add(30)
        self.assertAlmostEqual(cd.remaining(), left + 30, places=3)
        cd.start()
        cd._end = time.perf_counter() - 0.01        # pretend the time is up
        cd.poll()
        self.assertEqual(cd.state, Countdown.DONE)
        self.assertEqual(done, [True])
        cd.reset()
        self.assertEqual(cd.remaining(), 60)

    def test_add_never_drops_below_one_second(self):
        cd = Countdown(30)
        cd.start()
        cd.add(-120)
        self.assertGreater(cd.remaining(), 0.5)


class StopwatchTest(unittest.TestCase):
    def test_laps_and_reset(self):
        sw = Stopwatch()
        sw.lap_or_reset()                            # no-op while reset
        self.assertTrue(sw.is_reset)
        sw.start()
        sw._t0 -= 10
        sw.lap()
        sw._t0 -= 5
        sw.lap()
        self.assertEqual([l.index for l in sw.laps], [1, 2])
        self.assertAlmostEqual(sw.laps[1].duration, 5.0, places=1)
        sw.stop()
        sw.lap_or_reset()                            # stopped → reset
        self.assertTrue(sw.is_reset)


class AstroTest(unittest.TestCase):
    def test_moon_phases(self):
        new = moon_info(datetime(2024, 4, 8, 18, 21, tzinfo=timezone.utc))      # solar eclipse
        full = moon_info(datetime(2024, 4, 23, 23, 49, tzinfo=timezone.utc))
        self.assertLess(new.illumination, 0.01)
        self.assertGreater(full.illumination, 0.99)
        self.assertEqual(full.name, "FULL MOON")
        quarter = moon_info(datetime(2024, 4, 15, 19, 13, tzinfo=timezone.utc))  # first quarter
        self.assertAlmostEqual(quarter.illumination, 0.5, delta=0.03)
        self.assertTrue(quarter.waxing)

    def test_sunrise_sunset_tokyo(self):
        info = sun_info(datetime(2026, 10, 16).date(), 35.6812, 139.7671)
        rise = info.sunrise.astimezone(timezone.utc)       # naive local → aware UTC
        sett = info.sunset.astimezone(timezone.utc)
        self.assertLess(abs(rise - datetime(2026, 10, 15, 20, 47, tzinfo=timezone.utc)), timedelta(minutes=4))
        self.assertLess(abs(sett - datetime(2026, 10, 16, 8, 5, tzinfo=timezone.utc)), timedelta(minutes=4))

    def test_polar_night(self):
        self.assertEqual(sun_info(datetime(2026, 12, 21).date(), 78.2, 15.6).polar, "night")   # Svalbard


class SettingsTest(unittest.TestCase):
    def test_roundtrip_and_type_guard(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "settings.json"
            s = Settings(path)
            s["volume"] = 0.25
            s["use_24h"] = False
            s.save()
            path.write_text(path.read_text(encoding="utf-8").replace('"fps": 60', '"fps": "fast"'),
                            encoding="utf-8")
            again = Settings(path)
            self.assertEqual(again["volume"], 0.25)
            self.assertFalse(again["use_24h"])
            self.assertEqual(again["fps"], 60)              # wrong type falls back to default

    def test_smooth_sweep_is_default_and_v1_files_migrate(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "settings.json"
            self.assertEqual(Settings(path)["sweep"], "smooth")
            path.write_text('{"sweep": "mechanical", "fps": 30}', encoding="utf-8")   # v1: no version
            migrated = Settings(path)
            self.assertEqual(migrated["sweep"], "smooth")
            self.assertEqual(migrated["fps"], 30)
            migrated["sweep"] = "mechanical"                # an explicit choice made after the upgrade…
            migrated.save()
            self.assertEqual(Settings(path)["sweep"], "mechanical")   # …is kept


if __name__ == "__main__":
    unittest.main()
