"""City catalogue for the world clock and the astronomy location picker."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@dataclass(frozen=True)
class City:
    name: str
    name_jp: str
    tz: str
    lat: float
    lon: float

    @property
    def label(self) -> str:
        return f"{self.name}  ·  {self.name_jp}  ({self.tz})"


CITIES: list[City] = [
    City("UTC", "協定世界時", "UTC", 51.4779, -0.0015),
    City("TOKYO", "東京", "Asia/Tokyo", 35.6812, 139.7671),
    City("OSAKA", "大阪", "Asia/Tokyo", 34.6937, 135.5023),
    City("NAGOYA", "名古屋", "Asia/Tokyo", 35.1815, 136.9066),
    City("SAPPORO", "札幌", "Asia/Tokyo", 43.0618, 141.3545),
    City("FUKUOKA", "福岡", "Asia/Tokyo", 33.5902, 130.4017),
    City("NAHA", "那覇", "Asia/Tokyo", 26.2124, 127.6809),
    City("SEOUL", "ソウル", "Asia/Seoul", 37.5665, 126.9780),
    City("BEIJING", "北京", "Asia/Shanghai", 39.9042, 116.4074),
    City("SHANGHAI", "上海", "Asia/Shanghai", 31.2304, 121.4737),
    City("HONG KONG", "香港", "Asia/Hong_Kong", 22.3193, 114.1694),
    City("TAIPEI", "台北", "Asia/Taipei", 25.0330, 121.5654),
    City("MANILA", "マニラ", "Asia/Manila", 14.5995, 120.9842),
    City("HANOI", "ハノイ", "Asia/Ho_Chi_Minh", 21.0278, 105.8342),
    City("BANGKOK", "バンコク", "Asia/Bangkok", 13.7563, 100.5018),
    City("SINGAPORE", "シンガポール", "Asia/Singapore", 1.3521, 103.8198),
    City("KUALA LUMPUR", "クアラルンプール", "Asia/Kuala_Lumpur", 3.1390, 101.6869),
    City("JAKARTA", "ジャカルタ", "Asia/Jakarta", -6.2088, 106.8456),
    City("NEW DELHI", "ニューデリー", "Asia/Kolkata", 28.6139, 77.2090),
    City("MUMBAI", "ムンバイ", "Asia/Kolkata", 19.0760, 72.8777),
    City("KATHMANDU", "カトマンズ", "Asia/Kathmandu", 27.7172, 85.3240),
    City("DUBAI", "ドバイ", "Asia/Dubai", 25.2048, 55.2708),
    City("RIYADH", "リヤド", "Asia/Riyadh", 24.7136, 46.6753),
    City("TEHRAN", "テヘラン", "Asia/Tehran", 35.6892, 51.3890),
    City("ISTANBUL", "イスタンブール", "Europe/Istanbul", 41.0082, 28.9784),
    City("MOSCOW", "モスクワ", "Europe/Moscow", 55.7558, 37.6173),
    City("CAIRO", "カイロ", "Africa/Cairo", 30.0444, 31.2357),
    City("NAIROBI", "ナイロビ", "Africa/Nairobi", -1.2921, 36.8219),
    City("JOHANNESBURG", "ヨハネスブルグ", "Africa/Johannesburg", -26.2041, 28.0473),
    City("LAGOS", "ラゴス", "Africa/Lagos", 6.5244, 3.3792),
    City("ATHENS", "アテネ", "Europe/Athens", 37.9838, 23.7275),
    City("HELSINKI", "ヘルシンキ", "Europe/Helsinki", 60.1699, 24.9384),
    City("STOCKHOLM", "ストックホルム", "Europe/Stockholm", 59.3293, 18.0686),
    City("BERLIN", "ベルリン", "Europe/Berlin", 52.5200, 13.4050),
    City("ZURICH", "チューリッヒ", "Europe/Zurich", 47.3769, 8.5417),
    City("GENEVA", "ジュネーブ", "Europe/Zurich", 46.2044, 6.1432),
    City("ROME", "ローマ", "Europe/Rome", 41.9028, 12.4964),
    City("PARIS", "パリ", "Europe/Paris", 48.8566, 2.3522),
    City("AMSTERDAM", "アムステルダム", "Europe/Amsterdam", 52.3676, 4.9041),
    City("MADRID", "マドリード", "Europe/Madrid", 40.4168, -3.7038),
    City("LONDON", "ロンドン", "Europe/London", 51.5074, -0.1278),
    City("LISBON", "リスボン", "Europe/Lisbon", 38.7223, -9.1393),
    City("REYKJAVIK", "レイキャビク", "Atlantic/Reykjavik", 64.1466, -21.9426),
    City("NEW YORK", "ニューヨーク", "America/New_York", 40.7128, -74.0060),
    City("TORONTO", "トロント", "America/Toronto", 43.6532, -79.3832),
    City("CHICAGO", "シカゴ", "America/Chicago", 41.8781, -87.6298),
    City("DENVER", "デンバー", "America/Denver", 39.7392, -104.9903),
    City("LOS ANGELES", "ロサンゼルス", "America/Los_Angeles", 34.0522, -118.2437),
    City("SAN FRANCISCO", "サンフランシスコ", "America/Los_Angeles", 37.7749, -122.4194),
    City("SEATTLE", "シアトル", "America/Los_Angeles", 47.6062, -122.3321),
    City("VANCOUVER", "バンクーバー", "America/Vancouver", 49.2827, -123.1207),
    City("ANCHORAGE", "アンカレッジ", "America/Anchorage", 61.2181, -149.9003),
    City("HONOLULU", "ホノルル", "Pacific/Honolulu", 21.3069, -157.8583),
    City("MEXICO CITY", "メキシコシティ", "America/Mexico_City", 19.4326, -99.1332),
    City("BOGOTA", "ボゴタ", "America/Bogota", 4.7110, -74.0721),
    City("LIMA", "リマ", "America/Lima", -12.0464, -77.0428),
    City("SAO PAULO", "サンパウロ", "America/Sao_Paulo", -23.5505, -46.6333),
    City("BUENOS AIRES", "ブエノスアイレス", "America/Argentina/Buenos_Aires", -34.6037, -58.3816),
    City("SYDNEY", "シドニー", "Australia/Sydney", -33.8688, 151.2093),
    City("MELBOURNE", "メルボルン", "Australia/Melbourne", -37.8136, 144.9631),
    City("BRISBANE", "ブリスベン", "Australia/Brisbane", -27.4698, 153.0251),
    City("PERTH", "パース", "Australia/Perth", -31.9505, 115.8605),
    City("AUCKLAND", "オークランド", "Pacific/Auckland", -36.8485, 174.7633),
]


@lru_cache(maxsize=None)
def zone(tz_name: str) -> ZoneInfo | None:
    try:
        return ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError, OSError):   # unknown, malformed or a directory
        return None
