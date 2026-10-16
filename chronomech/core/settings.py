"""Persistent user settings stored as JSON in the platform config directory."""
from __future__ import annotations

import copy
import json
import os
import sys
from pathlib import Path
from typing import Any

DEFAULTS: dict[str, Any] = {
    "use_24h": True,
    "tick_sound": False,
    "volume": 0.6,
    "fps": 60,
    "sweep": "mechanical",          # mechanical | smooth | quartz
    "always_on_top": False,
    "focus_mode": False,
    "world_clocks": [
        {"name": "UTC", "tz": "UTC"},
        {"name": "NEW YORK", "tz": "America/New_York"},
        {"name": "LONDON", "tz": "Europe/London"},
        {"name": "PARIS", "tz": "Europe/Paris"},
        {"name": "SINGAPORE", "tz": "Asia/Singapore"},
        {"name": "SYDNEY", "tz": "Australia/Sydney"},
    ],
    "alarms": [],
    "location": {"name": "TOKYO", "lat": 35.6812, "lon": 139.7671},
    "timer_seconds": 300,
    "geometry": None,
}


def config_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "ChronoMech"


def _compatible(default: Any, value: Any) -> bool:
    if default is None:
        return True
    if isinstance(default, bool) or isinstance(value, bool):
        return isinstance(default, bool) and isinstance(value, bool)
    if isinstance(default, (int, float)):
        return isinstance(value, (int, float))
    return isinstance(value, type(default))


class Settings:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or config_dir() / "settings.json"
        self.data: dict[str, Any] = copy.deepcopy(DEFAULTS)
        self._load()

    def _load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if not isinstance(raw, dict):
            return
        for key, value in raw.items():
            if key in DEFAULTS and _compatible(DEFAULTS[key], value):
                self.data[key] = value

    def __getitem__(self, key: str) -> Any:
        return self.data[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError:
            pass
