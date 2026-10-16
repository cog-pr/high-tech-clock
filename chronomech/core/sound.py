"""Procedurally synthesised sounds (escapement tick, alarm chime) — no audio assets needed."""
from __future__ import annotations

import math
import random
import struct
import sys
import wave
from pathlib import Path

from PySide6.QtCore import QObject, QUrl

SAMPLE_RATE = 44100


def _write_wav(path: Path, samples: list[float]) -> None:
    peak = max(1e-9, max(abs(s) for s in samples))
    frames = b"".join(struct.pack("<h", int(max(-1.0, min(1.0, s / peak * 0.92)) * 32767))
                      for s in samples)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(frames)


def _tick_samples() -> list[float]:
    rnd = random.Random(7)
    out = []
    for i in range(int(SAMPLE_RATE * 0.045)):
        t = i / SAMPLE_RATE
        click = math.exp(-t * 900) * rnd.uniform(-1, 1) * 0.6
        ring = math.exp(-t * 140) * (math.sin(math.tau * 3150 * t) * 0.5 + math.sin(math.tau * 5230 * t) * 0.25)
        out.append(click + ring)
    return out


def _chime_samples() -> list[float]:
    """Three bell strikes (inharmonic partials) followed by a pause; loops cleanly."""
    length = int(SAMPLE_RATE * 1.9)
    out = [0.0] * length
    strikes = [(0.00, 1318.5), (0.22, 1567.98), (0.44, 2093.0)]
    partials = [(1.0, 1.0), (2.76, 0.45), (5.40, 0.22), (0.5, 0.25)]
    for start, freq in strikes:
        s0 = int(start * SAMPLE_RATE)
        for i in range(length - s0):
            t = i / SAMPLE_RATE
            env = math.exp(-t * 3.2) * min(1.0, t * 400)
            v = sum(a * math.exp(-t * 2.0 * k) * math.sin(math.tau * freq * k * t) for k, a in partials)
            out[s0 + i] += v * env
    fade = int(SAMPLE_RATE * 0.25)
    for i in range(fade):
        out[length - fade + i] *= 1.0 - i / fade
    return out


class SoundSystem(QObject):
    """QSoundEffect when QtMultimedia is usable, winsound / system beep otherwise."""

    def __init__(self, cache_dir: Path, volume: float = 0.6, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.tick_enabled = False
        self._volume = volume
        self._alarm_playing = False
        self._tick_path = cache_dir / "tick_v1.wav"
        self._chime_path = cache_dir / "chime_v1.wav"
        try:
            if not self._tick_path.exists():
                _write_wav(self._tick_path, _tick_samples())
            if not self._chime_path.exists():
                _write_wav(self._chime_path, _chime_samples())
            self._files_ok = True
        except OSError:
            self._files_ok = False
        self._tick = self._chime = None
        if self._files_ok:
            try:
                from PySide6.QtMultimedia import QSoundEffect
                self._tick = QSoundEffect(self)
                self._tick.setSource(QUrl.fromLocalFile(str(self._tick_path)))
                self._chime = QSoundEffect(self)
                self._chime.setSource(QUrl.fromLocalFile(str(self._chime_path)))
                self._chime.setLoopCount(int(getattr(QSoundEffect.Loop.Infinite, "value", -2)))
            except Exception:          # multimedia backend missing → fall back below
                self._tick = self._chime = None
        self.set_volume(volume)

    def set_volume(self, volume: float) -> None:
        self._volume = max(0.0, min(1.0, volume))
        if self._tick is not None:
            self._tick.setVolume(self._volume * 0.35)
        if self._chime is not None:
            self._chime.setVolume(self._volume)

    def tick(self) -> None:
        if self.tick_enabled and self._tick is not None and not self._alarm_playing:
            self._tick.play()

    def start_alarm(self) -> None:
        if self._alarm_playing:
            return
        self._alarm_playing = True
        if self._chime is not None:
            self._chime.play()
        elif sys.platform == "win32" and self._files_ok:
            import winsound
            winsound.PlaySound(str(self._chime_path),
                               winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_LOOP)
        else:
            from PySide6.QtWidgets import QApplication
            QApplication.beep()

    def stop_alarm(self) -> None:
        if not self._alarm_playing:
            return
        self._alarm_playing = False
        if self._chime is not None:
            self._chime.stop()
        elif sys.platform == "win32":
            import winsound
            winsound.PlaySound(None, 0)
