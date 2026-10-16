"""Offline astronomy: moon phase (Meeus, ch. 48) and sunrise/sunset (NOAA)."""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

SYNODIC_MONTH = 29.530588853

_PHASES_EN = [
    (11.25, "NEW MOON"), (78.75, "WAXING CRESCENT"), (101.25, "FIRST QUARTER"),
    (168.75, "WAXING GIBBOUS"), (191.25, "FULL MOON"), (258.75, "WANING GIBBOUS"),
    (281.25, "LAST QUARTER"), (348.75, "WANING CRESCENT"), (360.0, "NEW MOON"),
]

# Traditional Japanese names keyed by lunar day (moon age + 1, rounded down).
_NAMES_JP = {
    1: "新月", 2: "既朔", 3: "三日月", 7: "上弦の月", 8: "上弦の月", 13: "十三夜",
    14: "小望月", 15: "満月", 16: "十六夜", 17: "立待月", 18: "居待月", 19: "寝待月",
    20: "更待月", 22: "下弦の月", 23: "下弦の月", 26: "有明月", 30: "晦日月",
}


@dataclass(frozen=True)
class MoonInfo:
    elongation: float     # 0 = new, 180 = full (degrees)
    illumination: float   # 0..1
    age: float            # days since new moon
    waxing: bool
    name: str
    name_jp: str
    days_to_full: float
    days_to_new: float


@dataclass(frozen=True)
class SunInfo:
    sunrise: datetime | None
    sunset: datetime | None
    noon: datetime
    polar: str | None     # "day" (midnight sun), "night" (polar night) or None


def julian_day(moment: datetime) -> float:
    if moment.tzinfo is None:
        moment = moment.astimezone()
    return moment.timestamp() / 86400.0 + 2440587.5


def moon_info(moment: datetime) -> MoonInfo:
    t = (julian_day(moment) - 2451545.0) / 36525.0
    d = 297.8501921 + 445267.1114034 * t - 0.0018819 * t * t + t ** 3 / 545868 - t ** 4 / 113065000
    m = 357.5291092 + 35999.0502909 * t - 0.0001536 * t * t + t ** 3 / 24490000
    mp = 134.9633964 + 477198.8675055 * t + 0.0087414 * t * t + t ** 3 / 69699 - t ** 4 / 14712000
    d, m, mp = (math.radians(x % 360.0) for x in (d, m, mp))
    phase_angle = (180.0 - math.degrees(d)
                   - 6.289 * math.sin(mp) + 2.100 * math.sin(m)
                   - 1.274 * math.sin(2 * d - mp) - 0.658 * math.sin(2 * d)
                   - 0.214 * math.sin(2 * mp) - 0.110 * math.sin(d))
    illumination = (1.0 + math.cos(math.radians(phase_angle))) / 2.0
    elongation = (180.0 - phase_angle) % 360.0
    age = elongation / 360.0 * SYNODIC_MONTH
    name = next(label for limit, label in _PHASES_EN if elongation < limit)
    lunar_day = int(age) + 1
    return MoonInfo(
        elongation=elongation,
        illumination=illumination,
        age=age,
        waxing=elongation < 180.0,
        name=name,
        name_jp=_NAMES_JP.get(lunar_day, ""),
        days_to_full=((180.0 - elongation) % 360.0) / 360.0 * SYNODIC_MONTH,
        days_to_new=((360.0 - elongation) % 360.0) / 360.0 * SYNODIC_MONTH,
    )


def sun_info(day: date, lat: float, lon: float) -> SunInfo:
    """Sunrise / sunset in the machine's local time zone for `day` at (lat, lon)."""
    year_days = 366 if (day.year % 4 == 0 and (day.year % 100 != 0 or day.year % 400 == 0)) else 365
    gamma = 2.0 * math.pi / year_days * (day.timetuple().tm_yday - 1)
    eqtime = 229.18 * (0.000075 + 0.001868 * math.cos(gamma) - 0.032077 * math.sin(gamma)
                       - 0.014615 * math.cos(2 * gamma) - 0.040849 * math.sin(2 * gamma))
    decl = (0.006918 - 0.399912 * math.cos(gamma) + 0.070257 * math.sin(gamma)
            - 0.006758 * math.cos(2 * gamma) + 0.000907 * math.sin(2 * gamma)
            - 0.002697 * math.cos(3 * gamma) + 0.00148 * math.sin(3 * gamma))
    lat_r = math.radians(max(-89.9, min(89.9, lat)))
    base = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)

    def at(minutes_utc: float) -> datetime:
        return (base + timedelta(minutes=minutes_utc)).astimezone().replace(tzinfo=None)

    noon = at(720.0 - 4.0 * lon - eqtime)
    cos_ha = (math.cos(math.radians(90.833)) / (math.cos(lat_r) * math.cos(decl))
              - math.tan(lat_r) * math.tan(decl))
    if cos_ha > 1.0:
        return SunInfo(None, None, noon, "night")
    if cos_ha < -1.0:
        return SunInfo(None, None, noon, "day")
    ha = math.degrees(math.acos(cos_ha))
    return SunInfo(sunrise=at(720.0 - 4.0 * (lon + ha) - eqtime),
                   sunset=at(720.0 - 4.0 * (lon - ha) - eqtime),
                   noon=noon, polar=None)
