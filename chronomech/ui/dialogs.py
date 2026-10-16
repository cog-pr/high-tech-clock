"""Frameless, themed dialogs: alarm editor, city picker, timer input, settings, help."""
from __future__ import annotations

from datetime import datetime, timedelta

from PySide6.QtCore import QPointF, QRectF, Qt, QTime
from PySide6.QtGui import QColor, QFontMetricsF, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QCompleter,
    QDialog,
    QDoubleSpinBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSlider,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from .. import theme as T
from ..core.alarms import Alarm
from ..core.cities import CITIES, City, zone
from ..core.settings import Settings
from .widgets import MechButton, ToggleSwitch


def field_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet(f"color: {T.TEXT_DIM}; font-family: 'Bahnschrift', 'Yu Gothic UI'; "
                        f"font-size: 11px; letter-spacing: 1.5px;")
    return label


class MechDialog(QDialog):
    HEADER = 46

    def __init__(self, title: str, subtitle: str, parent: QWidget | None = None, width: int = 440) -> None:
        super().__init__(parent, Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setModal(True)
        self.setMinimumWidth(width)
        self._title, self._subtitle = title, subtitle
        root = QVBoxLayout(self)
        root.setContentsMargins(22, self.HEADER + 10, 22, 18)
        root.setSpacing(12)
        self.body = QVBoxLayout()
        self.body.setSpacing(10)
        root.addLayout(self.body)
        root.addSpacing(4)
        self.buttons = QHBoxLayout()
        self.buttons.setSpacing(8)
        self.buttons.addStretch(1)
        root.addLayout(self.buttons)
        self._f_title = T.font(15, "semibold", spacing=3)
        self._f_sub = T.font(11, "regular")

    def add_button(self, text: str, slot, *, accent: bool = False, left: bool = False) -> MechButton:
        b = MechButton(text, accent=accent, height=30, min_width=96)
        b.clicked.connect(slot)
        if left:
            self.buttons.insertWidget(0, b)
        else:
            self.buttons.addWidget(b)
        return b

    def mousePressEvent(self, event) -> None:
        if event.position().y() < self.HEADER and self.windowHandle():
            self.windowHandle().startSystemMove()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.fillRect(self.rect(), QColor("#08060c"))
        frame = T.chamfer_path(r.adjusted(3, 3, -3, -3), 14)
        g = QLinearGradient(0, 0, 0, r.height())
        g.setColorAt(0.0, QColor("#141020"))
        g.setColorAt(1.0, QColor("#0b0911"))
        p.fillPath(frame, g)
        p.strokePath(frame, QPen(T.qc(T.VIOLET, 50), 4))
        p.strokePath(frame, QPen(T.qc(T.VIOLET_LO), 1))
        p.setPen(QPen(T.qc(T.LINE), 1))
        p.drawLine(QPointF(20, self.HEADER), QPointF(r.right() - 20, self.HEADER))
        p.setPen(QPen(T.qc(T.VIOLET), 2))
        p.drawLine(QPointF(20, self.HEADER), QPointF(64, self.HEADER))
        p.setFont(self._f_title)
        p.setPen(QColor(T.TEXT))
        p.drawText(QPointF(24, self.HEADER - 15), self._title)
        p.setFont(self._f_sub)
        p.setPen(T.qc(T.TEXT_DIM))
        p.drawText(QPointF(30 + QFontMetricsF(self._f_title).horizontalAdvance(self._title), self.HEADER - 15),
                   self._subtitle)


class AlarmDialog(MechDialog):
    def __init__(self, alarm: Alarm | None, use_24h: bool, parent: QWidget | None = None) -> None:
        super().__init__("ALARM", "アラームの設定" if alarm is None else "アラームの編集", parent, 460)
        self.deleted = False
        self._alarm = alarm
        if alarm is None:
            soon = datetime.now() + timedelta(hours=1)
            hour, minute, days, label = soon.hour, 0, list(range(7)), ""
        else:
            hour, minute, days, label = alarm.hour, alarm.minute, alarm.days, alarm.label

        self.body.addWidget(field_label("TIME  /  時刻"))
        self.time_edit = QTimeEdit(QTime(hour, minute))
        self.time_edit.setDisplayFormat("HH:mm" if use_24h else "hh:mm AP")
        self.time_edit.setStyleSheet("font-size: 34px; padding: 6px 12px;")
        self.time_edit.setMinimumHeight(60)
        self.body.addWidget(self.time_edit)

        self.body.addWidget(field_label("LABEL  /  ラベル"))
        self.label_edit = QLineEdit(label)
        self.label_edit.setPlaceholderText("例: 起床 / Meeting")
        self.label_edit.setMaxLength(40)
        self.body.addWidget(self.label_edit)

        self.body.addWidget(field_label("REPEAT  /  繰り返し"))
        days_row = QHBoxLayout()
        days_row.setSpacing(4)
        self._day_buttons: dict[int, MechButton] = {}
        for wd, text in zip([6, 0, 1, 2, 3, 4, 5], ["SU", "MO", "TU", "WE", "TH", "FR", "SA"]):
            b = MechButton(text, checkable=True, height=28, font_px=10.5)
            b.setChecked(wd in days)
            self._day_buttons[wd] = b
            days_row.addWidget(b)
        self.body.addLayout(days_row)
        presets = QHBoxLayout()
        presets.setSpacing(4)
        for text, sel in (("EVERY DAY", range(7)), ("WEEKDAYS", range(5)), ("WEEKENDS", (5, 6)), ("ONCE", ())):
            b = MechButton(text, height=24, font_px=9.5)
            b.clicked.connect(lambda _=False, s=tuple(sel): self._set_days(s))
            presets.addWidget(b)
        self.body.addLayout(presets)

        if alarm is not None:
            self.add_button("DELETE", self._delete, left=True)
        self.add_button("CANCEL", self.reject)
        self.add_button("SAVE", self.accept, accent=True)
        self.label_edit.returnPressed.connect(self.accept)

    def _set_days(self, sel) -> None:
        for wd, b in self._day_buttons.items():
            b.setChecked(wd in sel)

    def _delete(self) -> None:
        self.deleted = True
        self.accept()

    def result_alarm(self) -> Alarm:
        t = self.time_edit.time()
        days = sorted(wd for wd, b in self._day_buttons.items() if b.isChecked())
        alarm = Alarm(hour=t.hour(), minute=t.minute(), label=self.label_edit.text().strip(), days=days)
        if self._alarm is not None:
            alarm.id = self._alarm.id
        return alarm


class CityDialog(MechDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("ADD CITY", "都市を追加", parent, 480)
        self.body.addWidget(field_label("CITY / TIME ZONE  ·  都市名またはタイムゾーン"))
        self.combo = QComboBox()
        self.combo.setEditable(True)
        self.combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.combo.addItems([c.label for c in CITIES])
        self.combo.setCurrentIndex(-1)
        self.combo.lineEdit().setPlaceholderText("TOKYO / 東京 / Europe/Berlin …")
        completer = QCompleter([c.label for c in CITIES], self)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.combo.setCompleter(completer)
        self.body.addWidget(self.combo)
        self.body.addWidget(field_label("DISPLAY NAME  ·  表示名 (任意)"))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("空欄なら都市名を使用")
        self.name_edit.setMaxLength(24)
        self.body.addWidget(self.name_edit)
        self.error = QLabel("")
        self.error.setStyleSheet(f"color: {T.ALERT}; font-size: 11px;")
        self.body.addWidget(self.error)
        self.add_button("CANCEL", self.reject)
        self.add_button("ADD", self._try_accept, accent=True)
        self.entry: dict | None = None

    @staticmethod
    def _match(text: str) -> tuple[str, str] | None:
        t = text.strip()
        if not t:
            return None
        low = t.lower()
        for c in CITIES:
            if low in (c.label.lower(), c.name.lower(), c.name_jp, c.tz.lower()):
                return c.name, c.tz
        if zone(t) is not None:
            return t.split("/")[-1].replace("_", " ").upper(), t
        hits = [c for c in CITIES if low in c.label.lower()]
        return (hits[0].name, hits[0].tz) if len(hits) == 1 else None

    def _try_accept(self) -> None:
        found = self._match(self.combo.currentText())
        if found is None:
            self.error.setText("見つかりません — 一覧から選ぶか IANA 名 (例: Asia/Tokyo) を入力してください")
            return
        name, tz = found
        self.entry = {"name": (self.name_edit.text().strip() or name).upper(), "tz": tz}
        self.accept()


class TimerSetDialog(MechDialog):
    def __init__(self, seconds: float, parent: QWidget | None = None) -> None:
        super().__init__("TIMER", "時間を入力", parent, 360)
        s = int(seconds)
        self.edit = QTimeEdit(QTime(min(23, s // 3600), (s // 60) % 60, s % 60))
        self.edit.setDisplayFormat("HH:mm:ss")
        self.edit.setStyleSheet("font-size: 34px; padding: 6px 12px;")
        self.edit.setMinimumHeight(60)
        self.body.addWidget(field_label("DURATION  /  HH:MM:SS"))
        self.body.addWidget(self.edit)
        self.add_button("CANCEL", self.reject)
        self.add_button("SET", self.accept, accent=True)

    def seconds(self) -> int:
        t = self.edit.time()
        return t.hour() * 3600 + t.minute() * 60 + t.second()


class _Choice(QWidget):
    """Row of mutually exclusive MechButtons."""

    def __init__(self, options: list[tuple[str, object]], current: object) -> None:
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self._buttons: list[tuple[MechButton, object]] = []
        for text, value in options:
            b = MechButton(text, checkable=True, height=26, font_px=10.5)
            b.setChecked(value == current)
            b.clicked.connect(lambda _=False, v=value: self.set_value(v))
            lay.addWidget(b)
            self._buttons.append((b, value))
        self._value = current

    def set_value(self, value: object) -> None:
        self._value = value
        for b, v in self._buttons:
            b.setChecked(v == value)

    def value(self) -> object:
        return self._value


class SettingsDialog(MechDialog):
    def __init__(self, settings: Settings, parent: QWidget | None = None) -> None:
        super().__init__("SETTINGS", "設定", parent, 520)
        self._s = settings
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(12)
        row = 0

        def add(label: str, widget: QWidget) -> None:
            nonlocal row
            grid.addWidget(field_label(label), row, 0, Qt.AlignmentFlag.AlignVCenter)
            grid.addWidget(widget, row, 1)
            row += 1

        self.fmt = _Choice([("24H", True), ("12H", False)], settings["use_24h"])
        add("TIME FORMAT  /  表示形式", self.fmt)
        self.sweep = _Choice([("SMOOTH", "smooth"), ("MECHANICAL", "mechanical"), ("QUARTZ", "quartz")],
                             settings["sweep"])
        self.sweep.setToolTip("SMOOTH: 描画フレームごとになめらかに運針\n"
                              "MECHANICAL: 6振動/秒で刻む機械式運針\nQUARTZ: 1秒ステップ")
        add("SWEEP  /  運針", self.sweep)
        self.fps = _Choice([("30 FPS", 30), ("60 FPS", 60)], settings["fps"] if settings["fps"] in (30, 60) else 60)
        self.fps.setToolTip("30 FPS で CPU 使用率を抑えられます")
        add("FRAME RATE  /  描画", self.fps)
        sound_row = QWidget()
        sl = QHBoxLayout(sound_row)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(12)
        self.tick = ToggleSwitch(settings["tick_sound"])
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(round(float(settings["volume"]) * 100))
        sl.addWidget(self.tick)
        sl.addWidget(field_label("TICK"))
        sl.addSpacing(10)
        sl.addWidget(field_label("VOL"))
        sl.addWidget(self.volume, 1)
        add("SOUND  /  サウンド", sound_row)
        self.on_top = ToggleSwitch(settings["always_on_top"])
        add("ALWAYS ON TOP  /  最前面", self.on_top)

        loc = settings["location"]
        self.loc_combo = QComboBox()
        self.loc_combo.addItem("CUSTOM  ·  カスタム")
        for c in CITIES:
            if c.tz != "UTC":
                self.loc_combo.addItem(f"{c.name}  ·  {c.name_jp}", c)
        self.loc_combo.setCurrentIndex(0)
        for i in range(1, self.loc_combo.count()):
            c: City = self.loc_combo.itemData(i)
            if c.name == loc.get("name") and abs(c.lat - float(loc.get("lat", 0))) < 0.01:
                self.loc_combo.setCurrentIndex(i)
                break
        add("LOCATION  /  観測地", self.loc_combo)
        coords = QWidget()
        cl = QHBoxLayout(coords)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(8)
        self.lat = QDoubleSpinBox()
        self.lat.setRange(-90, 90)
        self.lat.setDecimals(4)
        self.lat.setValue(float(loc.get("lat", 0)))
        self.lon = QDoubleSpinBox()
        self.lon.setRange(-180, 180)
        self.lon.setDecimals(4)
        self.lon.setValue(float(loc.get("lon", 0)))
        self.loc_name = QLineEdit(str(loc.get("name", "")))
        self.loc_name.setMaxLength(18)
        cl.addWidget(field_label("LAT"))
        cl.addWidget(self.lat, 1)
        cl.addWidget(field_label("LON"))
        cl.addWidget(self.lon, 1)
        add("", coords)
        add("NAME  /  名称", self.loc_name)
        self.loc_combo.currentIndexChanged.connect(self._city_picked)
        self.body.addLayout(grid)
        self.add_button("CANCEL", self.reject)
        self.add_button("APPLY", self.accept, accent=True)

    def _city_picked(self, index: int) -> None:
        c = self.loc_combo.itemData(index)
        if isinstance(c, City):
            self.lat.setValue(c.lat)
            self.lon.setValue(c.lon)
            self.loc_name.setText(c.name)

    def apply(self) -> None:
        s = self._s
        s["use_24h"] = bool(self.fmt.value())
        s["sweep"] = str(self.sweep.value())
        s["fps"] = int(self.fps.value())
        s["tick_sound"] = self.tick.isChecked()
        s["volume"] = self.volume.value() / 100
        s["always_on_top"] = self.on_top.isChecked()
        s["location"] = {"name": (self.loc_name.text().strip() or "CUSTOM").upper(),
                         "lat": round(self.lat.value(), 4), "lon": round(self.lon.value(), 4)}
        s.save()


SHORTCUTS = [
    ("Space", "クロノグラフ スタート / ストップ"),
    ("L", "ラップ"),
    ("R", "クロノグラフ リセット (停止中)"),
    ("T", "タイマー スタート / 一時停止"),
    ("F", "フォーカスモード (時計のみ表示)"),
    ("F11", "フルスクリーン"),
    ("P", "常に手前に表示"),
    ("M", "刻み音 オン / オフ"),
    ("Ctrl + ,", "設定"),
    ("Esc", "フルスクリーン / フォーカス解除"),
    ("Ctrl + Q", "終了"),
    ("ホイール", "タイマー: ±1分 (Shift ±10秒) · カレンダー: 月移動"),
    ("右クリック", "世界時計 / アラームの編集・削除"),
]


class HelpDialog(MechDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("CONTROLS", "操作一覧", parent, 480)
        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(7)
        for i, (key, desc) in enumerate(SHORTCUTS):
            k = QLabel(key)
            k.setStyleSheet(f"color: {T.VIOLET_HI}; font-family: 'Cascadia Mono', 'Consolas'; font-size: 12px;"
                            f"border: 1px solid {T.LINE_HI}; padding: 2px 8px; background: #0f0c17;")
            d = QLabel(desc)
            d.setStyleSheet(f"color: {T.TEXT}; font-size: 12px; font-family: 'Yu Gothic UI', 'Bahnschrift';")
            grid.addWidget(k, i, 0, Qt.AlignmentFlag.AlignLeft)
            grid.addWidget(d, i, 1)
        self.body.addLayout(grid)
        self.add_button("CLOSE", self.accept, accent=True)
