"""Расстояния, нормализация адресов и привязка заправок к городам."""
from __future__ import annotations

import math
import re
import unicodedata
from difflib import SequenceMatcher


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def fold(s: str) -> str:
    """Нижний регистр и без диакритики: 'Rīga' -> 'riga'."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower()


# --- адреса ---------------------------------------------------------------

_TYPE_CANON = {
    "iela": "iela", "ielas": "iela",
    "gatve": "gatve", "gatves": "gatve",
    "bulvaris": "bulv", "bulvari": "bulv", "bulv": "bulv",
    "prospekts": "pr", "prospekta": "pr", "pr": "pr", "prosp": "pr",
    "dambis": "dambis", "damba": "dambis",
    "soseja": "sos", "sosejas": "sos",
    "aleja": "aleja", "alejas": "aleja",
    "laukums": "laukums",
    "krastmala": "krastmala",
    "cels": "cels", "cela": "cels",
}
_NUM_RE = re.compile(r"^\d+[a-z]?$")


def parse_address(text: str) -> dict | None:
    """'Brīvības gatve 265' -> {'core': 'brivibas', 'type': 'gatve', 'number': '265'}.

    Возвращает None, если в строке нет номера дома.
    """
    tokens = re.findall(r"[a-z0-9]+", fold(text))
    if not tokens:
        return None
    number_idx = None
    for i in range(len(tokens) - 1, -1, -1):
        if _NUM_RE.match(tokens[i]):
            number_idx = i
            break
    if number_idx is None:
        return None
    street_tokens = tokens[:number_idx]
    atype = None
    core = []
    for t in street_tokens:
        if t in _TYPE_CANON and atype is None:
            atype = _TYPE_CANON[t]
        else:
            core.append(t)
    if not core:
        return None
    return {"core": " ".join(core), "type": atype, "number": tokens[number_idx]}


def addresses_match(a: str, b: str, threshold: float = 0.85) -> bool:
    pa, pb = parse_address(a), parse_address(b)
    if not pa or not pb:
        return False
    if pa["number"] != pb["number"]:
        return False
    if pa["type"] and pb["type"] and pa["type"] != pb["type"]:
        return False
    return SequenceMatcher(None, pa["core"], pb["core"]).ratio() >= threshold


# --- города ---------------------------------------------------------------

# Приблизительные центры (точность в несколько км достаточна для отнесения
# заправки к ближайшему городу, когда в OpenStreetMap нет адреса).
TOWNS: list[tuple[str, float, float]] = [
    ("Rīga", 56.9496, 24.1052),
    ("Rīga", 57.0250, 24.1300),  # Mīlgrāvis
    ("Rīga", 57.0520, 24.1550),  # Jaunciems
    ("Rīga", 56.9850, 24.0450),  # Bolderāja
    ("Rīga", 56.9930, 24.2850),  # Berģi
    ("Rīga", 56.9900, 24.2350),  # Jugla
    ("Rīga", 56.9300, 24.1900),  # Šķirotava
    ("Rīga", 56.8950, 24.2400),  # Rumbula
    ("Rīga", 56.9050, 24.0900),  # Ziepniekkalns
    ("Rīga", 56.9610, 24.0300),  # Imanta
    ("Rīga", 56.9250, 24.2000),  # Pļavnieki
    ("Jūrmala", 56.9680, 23.7704),
    ("Jelgava", 56.6511, 23.7214),
    ("Daugavpils", 55.8747, 26.5362),
    ("Liepāja", 56.5047, 21.0108),
    ("Ventspils", 57.3894, 21.5606),
    ("Valmiera", 57.5385, 25.4264),
    ("Rēzekne", 56.5099, 27.3331),
    ("Jēkabpils", 56.4990, 25.8571),
    ("Ogre", 56.8157, 24.6044),
    ("Sigulda", 57.1537, 24.8528),
    ("Salaspils", 56.8617, 24.3511),
    ("Tukums", 56.9673, 23.1553),
    ("Cēsis", 57.3119, 25.2748),
    ("Kuldīga", 56.9687, 21.9704),
    ("Saldus", 56.6648, 22.4879),
    ("Talsi", 57.2447, 22.5895),
    ("Bauska", 56.4077, 24.1948),
    ("Dobele", 56.6256, 23.2792),
    ("Madona", 56.8531, 26.2173),
    ("Limbaži", 57.5128, 24.7137),
    ("Gulbene", 57.1762, 26.7527),
    ("Smiltene", 57.4231, 25.9021),
    ("Aizkraukle", 56.6036, 25.2556),
    ("Alūksne", 57.4206, 27.0453),
    ("Balvi", 57.1313, 27.2634),
    ("Krāslava", 55.8950, 27.1668),
    ("Ludza", 56.5471, 27.7192),
    ("Olaine", 56.7870, 23.9387),
    ("Mārupe", 56.9059, 24.0460),
    ("Ķekava", 56.8266, 24.2334),
    ("Ādaži", 57.0747, 24.3258),
    ("Saulkrasti", 57.2625, 24.4150),
    ("Kandava", 57.0349, 22.7794),
    ("Lielvārde", 56.7200, 24.8100),
    ("Salacgrīva", 57.7539, 24.3554),
    ("Ape", 57.5395, 26.6963),
    ("Valka", 57.7750, 26.0170),
    ("Preiļi", 56.2930, 26.7240),
    ("Līvāni", 56.3540, 26.1750),
    ("Ķegums", 56.7400, 24.7200),
    ("Iecava", 56.5980, 24.2000),
    ("Grobiņa", 56.5380, 21.1670),
    ("Pāvilosta", 56.8890, 21.1930),
    ("Aizpute", 56.7200, 21.6000),
    ("Skrunda", 56.6720, 22.0170),
    ("Brocēni", 56.6770, 22.5690),
    ("Cesvaine", 56.9680, 26.3060),
    ("Rūjiena", 57.9000, 25.3300),
    ("Mazsalaca", 57.8650, 25.0540),
    ("Ainaži", 57.8640, 24.3580),
    ("Baldone", 56.7410, 24.3900),
    ("Stopiņi", 56.9300, 24.3000),
    ("Garkalne", 57.0600, 24.3800),
    ("Ropaži", 56.9600, 24.6300),
    ("Carnikava", 57.1250, 24.2800),
    ("Inčukalns", 57.0990, 24.6870),
]

_CANON_TOWN = {}
for _n, _, _ in TOWNS:
    _CANON_TOWN.setdefault(fold(_n), _n)

MAX_TOWN_KM = 20.0
OTHER_PLACE = "Cita vieta"


def canonical_city(name: str | None) -> str | None:
    if not name:
        return None
    cleaned = name.strip()
    key = fold(cleaned)
    return _CANON_TOWN.get(key, cleaned)


def nearest_town(lat: float, lon: float) -> str:
    best_name, best_d = OTHER_PLACE, MAX_TOWN_KM
    for name, tlat, tlon in TOWNS:
        d = haversine_km(lat, lon, tlat, tlon)
        if d < best_d:
            best_name, best_d = name, d
    return best_name


def assign_city(tags: dict, lat: float, lon: float, override: str | None = None) -> str:
    if override:
        return override
    for key in ("addr:city", "addr:town", "addr:village", "addr:place"):
        c = canonical_city(tags.get(key))
        if c:
            return c
    return nearest_town(lat, lon)
