"""Разбор официальных страниц цен Circle K и Virši.

Парсеры работают по видимому тексту страницы, а не по HTML-разметке: так они
переживают смену вёрстки. Если страница изменится настолько, что цены не
находятся, парсер вернёт пустой результат, а сборщик сохранит прошлые данные
и пометит источник как не обновившийся.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

PRICE_MIN, PRICE_MAX = 0.3, 5.0

ADDRESS_CHUNK_RE = re.compile(r"^[^\d]+\s\d+\s?[A-Za-z]?$")


@dataclass
class ParseResult:
    fuels: dict = field(default_factory=dict)  # ключ топлива -> {price, uniform, addresses}
    source_date: str | None = None  # дата, которую называет сама сеть (ISO)
    warnings: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.fuels)


def html_to_text(html: str) -> str:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "template"]):
        tag.decompose()
    text = soup.get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text)


def _to_price(raw: str) -> float | None:
    try:
        value = float(raw.replace(",", "."))
    except ValueError:
        return None
    return round(value, 3) if PRICE_MIN <= value <= PRICE_MAX else None


def _date_after(pattern: str, text: str) -> str | None:
    m = re.search(pattern + r"\s*(\d{1,2})\.(\d{1,2})\.(\d{4})", text)
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat()
    except ValueError:
        return None


def parse_addresses(chunk: str) -> list[str]:
    """Из 'Brīvības gatve 265, Brīvības gatve 203, Rīga, LV-1006' -> два адреса."""
    result = []
    for part in chunk.split(","):
        part = part.strip(" .;-")
        if part and ADDRESS_CHUNK_RE.match(part):
            result.append(part)
    return result


# --- Circle K -------------------------------------------------------------

# (подпись на сайте, ключ топлива)
CK_LABELS = [
    ("miles+ XTL", "XTL"),
    ("98miles+", "98"),
    ("Dmiles+", "DP"),
    ("Dmiles", "D"),
    ("95miles", "95"),
    ("Autogāze", "LPG"),
]
_CK_ALT = "|".join(re.escape(l) for l, _ in sorted(CK_LABELS, key=lambda x: -len(x[0])))
_CK_ITEM = re.compile(
    rf"(?P<label>{_CK_ALT})\s+(?P<price>\d[.,]\d{{2,3}})\s*EUR\s*(?P<rest>.*?)"
    rf"(?=(?:{_CK_ALT})\s+\d[.,]\d{{2,3}}\s*EUR|$)",
    re.S,
)


def parse_circlek(html_or_text: str) -> ParseResult:
    text = html_to_text(html_or_text)
    text = re.sub(r"\b(95|98|D)\s+miles", r"\1miles", text)
    result = ParseResult()
    result.source_date = _date_after(r"Cenas\s+spēkā\s+no", text)
    if result.source_date is None:
        result.warnings.append("не найдена дата 'Cenas spēkā no'")

    start = text.find("Zemākās cenas")
    section = text[start:] if start >= 0 else text
    end = section.find("Degvielas cenu ietekmējošie")
    if end >= 0:
        section = section[:end]

    labels = dict(CK_LABELS)
    for m in _CK_ITEM.finditer(section):
        key = labels[m.group("label")]
        price = _to_price(m.group("price"))
        if price is None:
            result.warnings.append(f"цена вне допустимого диапазона: {m.group('label')}")
            continue
        rest = m.group("rest").strip()
        uniform = bool(re.search(r"visos\s+DUS|vienāda", rest, re.I))
        addresses = [] if uniform else parse_addresses(rest)
        if key not in result.fuels:
            result.fuels[key] = {"price": price, "uniform": uniform, "addresses": addresses}
    return result


# --- Virši ----------------------------------------------------------------

VIRSI_LABELS = {"DD": "D", "95E": "95", "98E": "98", "LPG": "LPG"}
_VIRSI_ALL = ["DD", "AD", "95E", "98E", "CBG", "LPG", "AdBLUE", "AdBlue"]
_VIRSI_ALT = "|".join(_VIRSI_ALL)
_VIRSI_ITEM = re.compile(
    rf"\b(?P<label>{_VIRSI_ALT})\s+(?P<price>\d[.,]\d{{2,3}})\b\s*(?P<rest>.*?)"
    rf"(?=\b(?:{_VIRSI_ALT})\s+\d[.,]\d{{2,3}}\b|Elektrouzlādes cenas|$)",
    re.S,
)


def parse_virsi(html_or_text: str) -> ParseResult:
    text = html_to_text(html_or_text)
    result = ParseResult()
    result.source_date = _date_after(r"atjaunotas", text)
    if result.source_date is None:
        result.warnings.append("не найдена дата 'atjaunotas'")

    first = _VIRSI_ITEM.search(text)
    if not first:
        return result
    section = text[first.start():]
    end = section.find("Elektrouzlādes cenas")
    if end >= 0:
        section = section[:end]

    for m in _VIRSI_ITEM.finditer(section):
        label = m.group("label")
        if label not in VIRSI_LABELS:
            continue  # агро-дизель, AdBlue и т.п. не нужны
        price = _to_price(m.group("price"))
        if price is None:
            result.warnings.append(f"цена вне допустимого диапазона: {label}")
            continue
        rest = m.group("rest").strip()
        uniform = bool(re.search(r"Visā\s+Viršu\s+tīklā", rest, re.I))
        addresses = [] if uniform else parse_addresses(rest)
        key = VIRSI_LABELS[label]
        if key not in result.fuels:
            result.fuels[key] = {"price": price, "uniform": uniform, "addresses": addresses}
    return result


# --- Viada ----------------------------------------------------------------

# Топливо определяется по имени картинки в первой колонке таблицы.
# Премиум-варианты (ectoplus), E85 и «обычный» D (продаётся на двух станциях
# рядом с Ecto D) не нужны.
VIADA_IMAGES = {
    "petrol_95ecto_new": "95",
    "petrol_98_new": "98",
    "petrol_d_ecto_new": "D",
    "GAZE": "LPG",
}


def parse_viada(html: str) -> ParseResult:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    result = ParseResult()
    m = re.search(r"spēkā\s+no\s*(\d{1,2})\s*\.\s*(\d{1,2})\s*\.\s*(\d{4})", soup.get_text(" ", strip=True))
    if m:
        try:
            result.source_date = date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat()
        except ValueError:
            pass
    if result.source_date is None:
        result.warnings.append("не найдена дата 'spēkā no'")

    for row in soup.find_all("tr"):
        cells = row.find_all("td")
        img = cells[0].find("img") if len(cells) >= 3 else None
        if img is None:
            continue
        name = (img.get("src") or "").rsplit("/", 1)[-1].rsplit(".", 1)[0]
        key = VIADA_IMAGES.get(name)
        pm = re.search(r"(\d[.,]\d{2,3})", cells[1].get_text(" ", strip=True))
        if key is None or pm is None or key in result.fuels:
            continue
        price = _to_price(pm.group(1))
        if price is None:
            result.warnings.append(f"цена вне допустимого диапазона: {name}")
            continue
        for span in cells[2].find_all("span", class_="dus-name"):
            span.decompose()
        addresses = parse_addresses(cells[2].get_text(" ", strip=True).replace(":", ","))
        result.fuels[key] = {"price": price, "uniform": False, "addresses": addresses}
    return result


# --- Cenometrs.lv: Straujupīte (своей страницы цен у сети нет) --------------

CENOMETRS_TYPES = {"95": "95", "98": "98", "diesel": "D", "pro": "DP", "gas": "LPG"}


def parse_cenometrs(html: str, source: str = "Straujupite") -> ParseResult:
    """Берёт из снимка цен на странице (window.__INITIAL_PRICES__) строки одной сети.

    Это минимальные цены сети, поэтому на остальных её станциях цена может быть выше.
    """
    import json

    result = ParseResult()
    m = re.search(r"__INITIAL_PRICES__\s*=\s*", html)
    if not m:
        return result
    try:
        rows, _ = json.JSONDecoder().raw_decode(html[m.end():])
    except ValueError:
        return result
    newest = None
    for row in rows if isinstance(rows, list) else []:
        key = CENOMETRS_TYPES.get(row.get("type"))
        if row.get("source") != source or key is None or key in result.fuels:
            continue
        price = _to_price(str(row.get("price", "")))
        if price is None:
            result.warnings.append(f"цена вне допустимого диапазона: {row.get('type')}")
            continue
        result.fuels[key] = {"price": price, "kind": "min", "uniform": False, "addresses": []}
        stamp = str(row.get("timestamp", ""))[:10]
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", stamp):
            newest = max(newest, stamp) if newest else stamp
    result.source_date = newest
    if result.fuels and newest is None:
        result.warnings.append("не найдена дата снимка")
    return result
