"""Список заправок Латвии из OpenStreetMap (Overpass API)."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from .geo import assign_city

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
QUERY = (
    '[out:json][timeout:120];'
    'area["ISO3166-1"="LV"][admin_level=2]->.lv;'
    '(node["amenity"="fuel"](area.lv);way["amenity"="fuel"](area.lv););'
    'out center tags;'
)

BRANDS = [
    ("circlek", re.compile(r"circle\s*k|statoil", re.I)),
    ("virsi", re.compile(r"vir[šs]i", re.I)),
    ("neste", re.compile(r"\bneste\b", re.I)),
    ("viada", re.compile(r"\bviada\b", re.I)),
    ("kool", re.compile(r"\bkool\b", re.I)),
    ("astarte", re.compile(r"astarte", re.I)),
    ("straujupite", re.compile(r"straujup[iī]te", re.I)),
    ("gotika", re.compile(r"gotika", re.I)),
    ("intergaz", re.compile(r"inters?ga[sz]", re.I)),
    ("propane", re.compile(r"prop[āa]nas+g[āa]ze|pros?g[āa]ze", re.I)),
]
CACHE_MAX_AGE_S = 7 * 24 * 3600


def detect_brand(tags: dict) -> str:
    blob = " ".join(tags.get(k, "") for k in ("brand", "name", "operator", "network"))
    for key, rx in BRANDS:
        if rx.search(blob):
            return key
    return "other"


def parse_overpass(data: dict, city_overrides: dict | None = None) -> list[dict]:
    city_overrides = city_overrides or {}
    stations = []
    for el in data.get("elements", []):
        tags = el.get("tags", {})
        lat = el.get("lat", (el.get("center") or {}).get("lat"))
        lon = el.get("lon", (el.get("center") or {}).get("lon"))
        if lat is None or lon is None:
            continue
        sid = f"{el['type'][0]}{el['id']}"
        street = tags.get("addr:street", "")
        house = tags.get("addr:housenumber", "")
        address = f"{street} {house}".strip() if street and house else (street or "")
        brand = detect_brand(tags)
        stations.append({
            "id": sid,
            "brand": brand,
            "name": tags.get("name") or tags.get("brand") or "Degvielas stacija",
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "address": address,
            "city": assign_city(tags, lat, lon, city_overrides.get(sid)),
            "lpg": tags.get("fuel:lpg") == "yes",
            "cng": tags.get("fuel:cng") == "yes",
        })
    return stations


def fetch_stations(session, cache_path: Path, city_overrides: dict | None = None,
                   force: bool = False) -> tuple[list[dict], str | None]:
    """Возвращает (станции, предупреждение). При сбое берёт старый кэш."""
    if cache_path.exists() and not force:
        age = time.time() - cache_path.stat().st_mtime
        if age < CACHE_MAX_AGE_S:
            return json.loads(cache_path.read_text("utf-8")), None
    last_err = "неизвестная ошибка"
    for url in OVERPASS_ENDPOINTS:
        try:
            r = session.post(url, data={"data": QUERY}, timeout=150)
            r.raise_for_status()
            stations = parse_overpass(r.json(), city_overrides)
            if len(stations) < 50:
                raise ValueError(f"подозрительно мало заправок: {len(stations)}")
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(stations, ensure_ascii=False), "utf-8")
            return stations, None
        except Exception as exc:  # noqa: BLE001
            last_err = f"{url}: {exc}"
    if cache_path.exists():
        return json.loads(cache_path.read_text("utf-8")), f"Overpass недоступен, использован старый кэш ({last_err})"
    return [], f"Overpass недоступен и кэша нет ({last_err})"
