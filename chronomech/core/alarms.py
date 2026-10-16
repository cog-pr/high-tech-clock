"""Alarm list, scheduling and snooze handling (naive local wall-clock time)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, time as dtime, timedelta

from PySide6.QtCore import QObject, Signal

from .settings import Settings

EVERY_DAY = list(range(7))   # Python weekday(): 0 = Monday … 6 = Sunday


@dataclass
class Alarm:
    hour: int
    minute: int
    label: str = ""
    days: list[int] = field(default_factory=lambda: list(EVERY_DAY))  # empty → one-shot
    enabled: bool = True
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])

    def next_occurrence(self, now: datetime) -> datetime | None:
        if not self.enabled:
            return None
        for offset in range(8):
            day = (now + timedelta(days=offset)).date()
            candidate = datetime.combine(day, dtime(self.hour, self.minute))
            if candidate <= now:
                continue
            if self.days and candidate.weekday() not in self.days:
                continue
            return candidate
        return None

    def to_dict(self) -> dict:
        return {"id": self.id, "hour": self.hour, "minute": self.minute, "label": self.label,
                "days": sorted(set(self.days)), "enabled": self.enabled}

    @classmethod
    def from_dict(cls, d: dict) -> "Alarm | None":
        try:
            return cls(hour=int(d["hour"]) % 24, minute=int(d["minute"]) % 60,
                       label=str(d.get("label", ""))[:40],
                       days=[int(x) % 7 for x in d.get("days", EVERY_DAY)],
                       enabled=bool(d.get("enabled", True)),
                       id=str(d.get("id") or uuid.uuid4().hex[:10]))
        except (KeyError, TypeError, ValueError):
            return None


class AlarmManager(QObject):
    changed = Signal()
    triggered = Signal(object)          # Alarm

    def __init__(self, settings: Settings, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self.alarms: list[Alarm] = [a for a in map(Alarm.from_dict, settings.get("alarms", [])) if a]
        self._fired: set[tuple[str, str]] = set()
        self._snoozes: list[tuple[datetime, Alarm]] = []
        self._sort()

    # ── editing ──
    def _sort(self) -> None:
        self.alarms.sort(key=lambda a: (a.hour, a.minute))

    def _commit(self) -> None:
        self._sort()
        self._settings["alarms"] = [a.to_dict() for a in self.alarms]
        self._settings.save()
        self.changed.emit()

    def add(self, alarm: Alarm) -> None:
        self.alarms.append(alarm)
        self._commit()

    def update(self, alarm: Alarm) -> None:
        for i, a in enumerate(self.alarms):
            if a.id == alarm.id:
                self.alarms[i] = alarm
                break
        else:
            self.alarms.append(alarm)
        self._commit()

    def remove(self, alarm_id: str) -> None:
        self.alarms = [a for a in self.alarms if a.id != alarm_id]
        self._snoozes = [(t, a) for t, a in self._snoozes if a.id != alarm_id]
        self._commit()

    def set_enabled(self, alarm_id: str, enabled: bool) -> None:
        for a in self.alarms:
            if a.id == alarm_id:
                a.enabled = enabled
        self._commit()

    # ── scheduling ──
    def snooze(self, alarm: Alarm, minutes: int = 5) -> None:
        self._snoozes.append((datetime.now() + timedelta(minutes=minutes), alarm))
        self.changed.emit()

    def check(self, now: datetime) -> None:
        """Called once per second by the time engine."""
        stamp = now.strftime("%Y%m%d%H%M")
        for alarm in list(self.alarms):
            if not alarm.enabled or (alarm.hour, alarm.minute) != (now.hour, now.minute):
                continue
            if alarm.days and now.weekday() not in alarm.days:
                continue
            key = (alarm.id, stamp)
            if key in self._fired:
                continue
            self._fired.add(key)
            if not alarm.days:                 # one-shot alarms disarm themselves
                alarm.enabled = False
                self._commit()
            self.triggered.emit(alarm)
        due = [(t, a) for t, a in self._snoozes if now >= t]
        if due:
            self._snoozes = [(t, a) for t, a in self._snoozes if now < t]
            for _, alarm in due:
                self.triggered.emit(alarm)
            self.changed.emit()
        if len(self._fired) > 256:
            self._fired = {k for k in self._fired if k[1] == stamp}

    def next_alarm(self, now: datetime) -> tuple[Alarm, datetime] | None:
        best: tuple[Alarm, datetime] | None = None
        for alarm in self.alarms:
            when = alarm.next_occurrence(now)
            if when and (best is None or when < best[1]):
                best = (alarm, when)
        for when, alarm in self._snoozes:
            if best is None or when < best[1]:
                best = (alarm, when)
        return best
