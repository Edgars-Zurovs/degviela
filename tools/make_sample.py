"""Демо-данные, чтобы приложение открывалось до первого запуска сборщика.
Координаты и цены ВЫМЫШЛЕННЫЕ (кроме одной реальной точки) — файл помечен sample=true."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

now = datetime.now(timezone.utc).replace(microsecond=0)
iso = lambda h: (now - timedelta(hours=h)).isoformat()
day = lambda d: (now - timedelta(days=d)).date().isoformat()


def off(price, kind, src_days, changed_h=None):
    return {"price": price, "kind": kind, "source_date": day(src_days), "checked_at": iso(0.3),
            "changed_at": iso(changed_h) if changed_h is not None else None}


S = [
    ("s1", "circlek", "Krasta iela 93", "Rīga", 56.929389, 24.153103, {"95": off(1.954, "here", 1, 5), "D": off(2.134, "min", 1), "98": off(2.054, "min", 1)}),
    ("s2", "circlek", "Brīvības gatve 265", "Rīga", 56.9780, 24.1950, {"95": off(1.954, "min", 1), "D": off(2.134, "here", 1)}),
    ("s3", "virsi", "Brīvības gatve 297", "Rīga", 56.9830, 24.2010, {"95": off(1.889, "here", 1, 20), "D": off(2.087, "here", 1, 20), "98": off(1.959, "here", 1)}),
    ("s4", "virsi", "Maskavas iela 240", "Rīga", 56.9040, 24.2000, {"95": off(1.889, "min", 1), "D": off(2.087, "min", 1)}),
    ("s5", "virsi", "Uzvaras iela 1", "Jūrmala", 56.9720, 23.7800, {"95": off(1.889, "min", 3)}),
    ("s6", "circlek", "Rūpniecības iela 1", "Liepāja", 56.5100, 21.0200, {"LPG": off(1.065, "uniform", 1)}),
]
data = {
    "meta": {
        "generated_at": iso(0.3), "sample": True, "fuels": ["95", "98", "D", "DP", "LPG", "CNG", "XTL"],
        "sources": {
            "circlek": {"name": "Circle K", "status": "ok", "fetched_at": iso(0.3), "source_date": day(1), "scope": "Рига"},
            "virsi": {"name": "Virši", "status": "ok", "fetched_at": iso(0.3), "source_date": day(1), "scope": "Рига и окрестности"},
            "neste": {"name": "Neste", "status": "unavailable", "error": "нет официальной страницы цен"},
            "viada": {"name": "Viada", "status": "unavailable", "error": "robots.txt запрещает чтение"},
        },
        "unmatched": {}, "warning": None,
    },
    "stations": [{"id": i, "brand": b, "name": b, "lat": la, "lon": lo, "address": a, "city": c, "offers": o}
                 for i, b, a, c, la, lo, o in S],
}
out = Path(__file__).resolve().parent.parent / "web" / "data"
out.mkdir(parents=True, exist_ok=True)
(out / "offers.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")
print("sample ok")
