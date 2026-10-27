"""Сборщик цен: официальные страницы сетей + заправки из OSM -> data/offers.json."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib import robotparser
from urllib.parse import urlsplit

from . import parsers
from .geo import addresses_match
from .stations import fetch_stations

SOURCES = {
    "circlek": {
        "name": "Circle K",
        "url": "https://www.circlek.lv/degviela-miles/degvielas-cenas",
        "parser": parsers.parse_circlek,
        "regions": {"Rīga"},
    },
    "virsi": {
        "name": "Virši",
        "url": "https://www.virsi.lv/lv/privatpersonam/degviela/degvielas-un-elektrouzlades-cenas",
        "parser": parsers.parse_virsi,
        "regions": {"Rīga", "Jūrmala", "Mārupe", "Ķekava", "Salaspils", "Ādaži", "Stopiņi",
                    "Garkalne", "Carnikava", "Olaine", "Ropaži", "Baldone"},
    },
    "viada": {
        "name": "Viada",
        "url": "https://www.viada.lv/zemakas-degvielas-cenas/",
        "parser": parsers.parse_viada,
        "regions": {"Rīga", "Liepāja"},
    },
}

# У Straujupīte нет своей страницы цен: берём минимум сети из снимка на Cenometrs.lv.
SOURCES["straujupite"] = {
    "name": "Straujupīte", "url": "https://www.cenometrs.lv/", "via": "Cenometrs.lv",
    "parser": parsers.parse_cenometrs,
    "regions": None,  # минимум сети показываем на всех её станциях
}

UNAVAILABLE = {
    "neste": ("Neste", "сеть больше не публикует цены, а агрегаторы закрыты для автоматического чтения"),
    "kool": ("KOOL", "нет страницы цен, доступной для автоматического чтения"),
    "astarte": ("Astarte", "нет страницы цен, доступной для автоматического чтения"),
}

FUELS = ["95", "98", "D", "DP", "LPG", "XTL"]


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def make_session(contact: str):
    import requests

    s = requests.Session()
    s.headers["User-Agent"] = f"DegvielaLV-personal/1.0 (+{contact or 'no-contact'})"
    s.headers["Accept-Language"] = "lv,en;q=0.8"
    return s


def robots_allows(session, url: str) -> tuple[bool, str]:
    parts = urlsplit(url)
    robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
    try:
        r = session.get(robots_url, timeout=20)
    except Exception as exc:  # noqa: BLE001
        return False, f"robots.txt недоступен ({exc})"
    if 400 <= r.status_code < 500:
        return True, "robots.txt отсутствует"
    if r.status_code >= 500:
        return False, f"robots.txt: HTTP {r.status_code}"
    rp = robotparser.RobotFileParser()
    rp.parse(r.text.splitlines())
    ua = session.headers["User-Agent"]
    if rp.can_fetch(ua, url):
        return True, "ok"
    return False, "robots.txt запрещает чтение страницы"


def fetch_page(session, url: str) -> tuple[str | None, str | None]:
    """Загружает страницу один раз за запуск (несколько сетей могут читаться с одной страницы)."""
    cache = session.__dict__.setdefault("_pages", {})
    if url not in cache:
        allowed, why = robots_allows(session, url)
        if not allowed:
            cache[url] = (None, why)
        else:
            try:
                r = session.get(url, timeout=30)
                r.raise_for_status()
                cache[url] = (r.text, None)
            except Exception as exc:  # noqa: BLE001
                cache[url] = (None, f"ошибка загрузки: {exc}")
    return cache[url]


def fetch_source(session, key: str) -> tuple[parsers.ParseResult | None, str | None]:
    src = SOURCES[key]
    text, err = fetch_page(session, src["url"])
    if text is None:
        return None, err
    try:
        result = src["parser"](text)
    except Exception as exc:  # noqa: BLE001
        return None, f"ошибка разбора: {exc}"
    if not result.ok:
        return None, "цены на странице не найдены (возможно, сайт изменил вёрстку)"
    return result, None


# --- состояние и сопоставление -------------------------------------------

def load_json(path: Path, default):
    try:
        return json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return default


def update_source_state(state: dict, key: str, result, error: str | None, fetched_at: str) -> None:
    s = state.setdefault("sources", {}).setdefault(key, {})
    if result is None:
        s["status"] = "error"
        s["error"] = error
        s["last_attempt"] = fetched_at
        return
    s.update(status="ok", error=None, last_attempt=fetched_at, fetched_at=fetched_at,
             source_date=result.source_date, warnings=result.warnings,
             fuels=result.fuels)


def track_change(state: dict, track_key: str, price: float, fetched_at: str) -> str | None:
    """Возвращает момент последнего замеченного нами изменения (или None)."""
    prices = state.setdefault("prices", {})
    rec = prices.get(track_key)
    if rec is None:
        prices[track_key] = {"price": price, "changed_at": None, "first_seen": fetched_at}
        return None
    if abs(rec["price"] - price) > 1e-9:
        rec["price"] = price
        rec["changed_at"] = fetched_at
    return rec["changed_at"]


def build_offers(stations: list[dict], state: dict) -> tuple[list[dict], dict]:
    by_id = {s["id"]: s for s in stations}
    for s in stations:
        s["offers"] = {}
    unmatched: dict[str, list[str]] = {}

    for key, src in SOURCES.items():
        ss = state.get("sources", {}).get(key)
        if not ss or not ss.get("fuels"):
            continue
        fetched_at = ss["fetched_at"]
        brand_stations = [s for s in stations if s["brand"] == key]
        for fuel, info in ss["fuels"].items():
            if fuel not in FUELS:
                continue  # старые данные (например, CNG) из сохранённого состояния
            price = info["price"]

            def put(st, kind, scope):
                changed = track_change(state, f"{key}|{fuel}|{scope}", price, fetched_at)
                st["offers"][fuel] = {
                    "price": price, "kind": kind,
                    "source_date": ss.get("source_date"),
                    "checked_at": fetched_at,
                    "changed_at": changed,
                }

            kind = info.get("kind") or ("uniform" if info.get("uniform") else None)
            if kind:
                for st in brand_stations:
                    if fuel == "LPG" and not st["lpg"]:
                        continue
                    put(st, kind, "all")
                continue

            matched_ids = set()
            for addr in info.get("addresses", []):
                hit = [st for st in brand_stations if st["address"] and addresses_match(addr, st["address"])]
                if hit:
                    for st in hit:
                        matched_ids.add(st["id"])
                else:
                    unmatched.setdefault(key, []).append(f"{fuel}: {addr}")
            for sid in matched_ids:
                put(by_id[sid], "here", f"here:{sid}")
            for st in brand_stations:
                if st["id"] in matched_ids:
                    continue
                if fuel == "LPG" and not st["lpg"]:
                    continue
                if st["city"] in src["regions"]:
                    put(st, "min", "region")
                else:
                    put(st, "ref", "ref")  # сеть публикует цены только по своим регионам
    return stations, unmatched


def run(data_dir: Path, contact: str, force_stations: bool = False, out_dir: Path | None = None) -> int:
    data_dir.mkdir(parents=True, exist_ok=True)
    out_dir = out_dir or data_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    session = make_session(contact)
    state_path = data_dir / "state.json"
    state = load_json(state_path, {})
    fetched_at = now_iso()

    ok_count = 0
    for key in SOURCES:
        result, err = fetch_source(session, key)
        update_source_state(state, key, result, err, fetched_at)
        if result is not None:
            ok_count += 1
        print(f"{SOURCES[key]['name']}: {'OK' if result else 'ОШИБКА - ' + str(err)}")

    overrides = load_json(Path("city_overrides.json"), {})
    stations, st_warn = fetch_stations(session, data_dir / "stations_cache.json", overrides, force_stations)
    if st_warn:
        print("Заправки:", st_warn)
    if not stations:
        print("Нет списка заправок - данные не обновлены", file=sys.stderr)
        return 1

    stations, unmatched = build_offers(stations, state)
    # независимые газовые заправки остаются в списке и без цены (в приложении - в конце списка «Газ»)
    stations = [s for s in stations if s["offers"] or s["brand"] != "other" or s["lpg"]]

    sources_meta = {}
    for key, src in SOURCES.items():
        ss = state.get("sources", {}).get(key, {})
        sources_meta[key] = {
            "name": src["name"], "status": ss.get("status", "error"), "error": ss.get("error"),
            "fetched_at": ss.get("fetched_at"), "source_date": ss.get("source_date"),
            "scope": {"circlek": "Рига", "viada": "Рига и Лиепая"}.get(
                key, "вся Латвия" if src.get("via") else "Рига и окрестности"),
            "via": src.get("via"),
        }
    for key, (name, why) in UNAVAILABLE.items():
        sources_meta[key] = {"name": name, "status": "unavailable", "error": why}

    out = {
        "meta": {
            "generated_at": fetched_at,
            "sample": False,
            "fuels": FUELS,
            "sources": sources_meta,
            "unmatched": unmatched,
            "warning": st_warn,
        },
        "stations": [
            {k: v for k, v in s.items() if k != "cng"} for s in stations
        ],
    }
    (out_dir / "offers.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), "utf-8")
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=1), "utf-8")
    print(f"Записано заправок: {len(out['stations'])}")
    return 0 if ok_count else 1


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data")
    ap.add_argument("--out", default="web/data")
    ap.add_argument("--contact", default=os.environ.get("CONTACT", ""))
    ap.add_argument("--force-stations", action="store_true")
    args = ap.parse_args()
    sys.exit(run(Path(args.data), args.contact, args.force_stations, Path(args.out)))


if __name__ == "__main__":
    main()
