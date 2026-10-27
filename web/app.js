"use strict";
/* Топливо LV — клиентская часть. Данные: data/offers.json (обновляет сборщик). */

const FUEL_NAMES = { "95": "95", "98": "98", D: "Дизель", DP: "Дизель+", LPG: "Газ", CNG: "CNG", XTL: "XTL" };
const NETS = { circlek: "Circle K", virsi: "Virši", neste: "Neste", viada: "Viada", kool: "KOOL", astarte: "Astarte", straujupite: "Straujupīte", gotika: "Gotika", other: "Другая сеть" };
const CITY_RU = {
  "Rīga": "Рига", "Jūrmala": "Юрмала", "Jelgava": "Елгава", "Daugavpils": "Даугавпилс", "Liepāja": "Лиепая",
  "Ventspils": "Вентспилс", "Valmiera": "Валмиера", "Rēzekne": "Резекне", "Jēkabpils": "Екабпилс", "Ogre": "Огре",
  "Sigulda": "Сигулда", "Salaspils": "Саласпилс", "Tukums": "Тукумс", "Cēsis": "Цесис", "Kuldīga": "Кулдига",
  "Saldus": "Салдус", "Talsi": "Талси", "Bauska": "Бауска", "Dobele": "Добеле", "Madona": "Мадона",
  "Limbaži": "Лимбажи", "Gulbene": "Гулбене", "Smiltene": "Смилтене", "Aizkraukle": "Айзкраукле",
  "Alūksne": "Алуксне", "Balvi": "Балви", "Krāslava": "Краслава", "Ludza": "Лудза", "Olaine": "Олайне",
  "Mārupe": "Марупе", "Ķekava": "Кекава", "Ādaži": "Адажи", "Saulkrasti": "Саулкрасты", "Cita vieta": "Другие места",
};
const STALE_PRICE_HOURS = 48;   // цена по данным сети старше — предупреждаем
const STALE_DATA_HOURS = 36;    // наш сборщик давно не обновлял данные
const MAX_PER_NETWORK_FRESH = 3;
const SHOW_FIRST = 8;

const $ = (s) => document.querySelector(s);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const cityRu = (c) => CITY_RU[c] || c;
const netName = (b) => NETS[b] || b;

/* ---------- чистая логика (проверяется тестами) ---------- */

function haversineKm(a, b, c, d) {
  const R = 6371.0088, rad = (x) => (x * Math.PI) / 180;
  const dp = rad(c - a), dl = rad(d - b);
  const h = Math.sin(dp / 2) ** 2 + Math.cos(rad(a)) * Math.cos(rad(c)) * Math.sin(dl / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}

function hoursSince(iso, now = Date.now()) {
  if (!iso) return null;
  const t = Date.parse(iso.length <= 10 ? iso + "T00:00:00" : iso);
  return Number.isNaN(t) ? null : (now - t) / 36e5;
}

function effPrice(st, o, settings) {
  const disc = settings.useCard ? (settings.discounts[st.brand] || 0) / 100 : 0;
  return o.price - disc;
}

const certainty = (o) => (o.kind === "ref" ? 2 : o.kind === "min" ? 1 : 0);

/* Список предложений для вида топлива -> группы (одинаковые «минимум по сети» схлопываются). */
function collect(stations, fuel, settings, { city = null, pos = null, radius = null } = {}) {
  const items = [];
  for (const st of stations) {
    const o = st.offers && st.offers[fuel];
    if (!o) continue;
    if (settings.onlyExact && (o.kind === "min" || o.kind === "ref")) continue;
    if (city && st.city !== city) continue;
    let dist = null;
    if (pos) dist = haversineKm(pos.lat, pos.lon, st.lat, st.lon);
    if (radius != null && (dist == null || dist > radius)) continue;
    items.push({ st, o, dist, eff: effPrice(st, o, settings) });
  }
  const groups = new Map();
  const out = [];
  for (const it of items) {
    if (it.o.kind === "here") { it.n = 1; out.push(it); continue; }
    const k = `${it.st.brand}|${it.o.kind}|${it.o.price}`;
    const g = groups.get(k);
    if (!g) { it.n = 1; groups.set(k, it); out.push(it); }
    else {
      g.n += 1;
      if (it.dist != null && (g.dist == null || it.dist < g.dist)) { g.st = it.st; g.dist = it.dist; }
    }
  }
  return out;
}

function sortByPrice(list) {
  return list.slice().sort((a, b) => a.eff - b.eff || certainty(a.o) - certainty(b.o) || (a.dist ?? 1e9) - (b.dist ?? 1e9));
}

function freshKey(it) { return it.o.changed_at || it.o.source_date || ""; }

function sortFresh(list) {
  const sorted = list.slice().sort((a, b) => {
    const ka = Date.parse(freshKey(a)) || 0, kb = Date.parse(freshKey(b)) || 0;
    return kb - ka || a.eff - b.eff;
  });
  const per = {}, res = [];
  for (const it of sorted) {
    per[it.st.brand] = (per[it.st.brand] || 0) + 1;
    if (per[it.st.brand] <= MAX_PER_NETWORK_FRESH) res.push(it);
  }
  return res;
}

function ago(iso, now = Date.now()) {
  const h = hoursSince(iso, now);
  if (h == null) return "";
  if (h < 1) return `${Math.max(1, Math.round(h * 60))} мин назад`;
  if (h < 24) return `${Math.round(h)} ч назад`;
  return `${Math.round(h / 24)} дн назад`;
}

function fmtDate(iso) {
  if (!iso) return "";
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  return m ? `${m[3]}.${m[2]}` : "";
}
const fmtPrice = (p) => p.toFixed(3).replace(".", ",");

function mapUrl(st, app) {
  if (app === "apple") return `https://maps.apple.com/?daddr=${st.lat},${st.lon}&dirflg=d`;
  return `https://www.google.com/maps/dir/?api=1&destination=${st.lat},${st.lon}&travelmode=driving`;
}

if (typeof module !== "undefined") {
  module.exports = { haversineKm, collect, sortByPrice, sortFresh, effPrice, ago, mapUrl, hoursSince, fmtPrice };
}

/* ---------- состояние и хранилище ---------- */

const isIOS = typeof navigator !== "undefined" && /iPad|iPhone|iPod/.test(navigator.userAgent || "");
const DEFAULTS = { fuel: "95", city: "Rīga", tab: "city", radius: 10, discounts: {}, useCard: true, onlyExact: false, mapApp: isIOS ? "apple" : "google" };
const store = {
  get() { try { return JSON.parse(localStorage.getItem("fuel-settings") || "{}"); } catch { return {}; } },
  set(v) { try { localStorage.setItem("fuel-settings", JSON.stringify(v)); } catch { /* приватный режим */ } },
};
const S = Object.assign({}, DEFAULTS, store.get());
S.discounts = Object.assign({}, S.discounts);
const save = () => store.set(S);

const app = { data: null, loadedAt: 0, offline: false, loadError: null, pos: null, geo: "idle", showAll: false };

/* ---------- загрузка данных ---------- */

async function load(force) {
  if (!force && Date.now() - app.loadedAt < 60000) return;
  const btn = $("#refreshBtn");
  btn.classList.add("spin");
  try {
    const r = await fetch("data/offers.json", { cache: "no-store" });
    if (!r.ok) throw new Error("HTTP " + r.status);
    app.data = await r.json();
    app.offline = false; app.loadError = null; app.loadedAt = Date.now();
  } catch (e) {
    app.offline = true;
    app.loadError = String(e.message || e);
    if (!app.data) {
      try { const c = await caches.match("data/offers.json"); if (c) app.data = await c.json(); } catch { /* нет кэша */ }
    }
  } finally {
    btn.classList.remove("spin");
    render();
  }
}

/* ---------- геолокация ---------- */

function askGeo() {
  if (!("geolocation" in navigator)) { app.geo = "unavailable"; render(); return; }
  app.geo = "asking"; render();
  navigator.geolocation.getCurrentPosition(
    (p) => { app.pos = { lat: p.coords.latitude, lon: p.coords.longitude }; app.geo = "ok"; render(); },
    (e) => { app.geo = e.code === 1 ? "denied" : "failed"; render(); },
    { enableHighAccuracy: false, timeout: 15000, maximumAge: 60000 }
  );
}

/* ---------- отрисовка ---------- */

function banners() {
  const out = [];
  const d = app.data;
  if (!d) return "";
  const m = d.meta || {};
  if (m.sample) out.push(`<div class="banner warn"><b>Демо-данные.</b> Это пример, цены ненастоящие. Настоящие появятся после первого запуска сборщика.</div>`);
  if (app.offline) out.push(`<div class="banner bad"><b>Нет связи.</b> Показаны сохранённые данные${m.generated_at ? ` (собраны ${esc(ago(m.generated_at))})` : ""}.</div>`);
  const h = hoursSince(m.generated_at);
  if (!m.sample && h != null && h > STALE_DATA_HOURS) out.push(`<div class="banner warn"><b>Данные давно не обновлялись</b> — ${esc(ago(m.generated_at))}. Проверьте запуск сборщика.</div>`);
  const src = m.sources || {};
  for (const [k, s] of Object.entries(src)) {
    if (s.status === "error") out.push(`<div class="banner warn"><b>${esc(s.name)}:</b> не удалось обновить цены (${esc(s.error || "ошибка")}). Показаны прошлые${s.fetched_at ? ` — ${esc(ago(s.fetched_at))}` : ""}.</div>`);
  }
  const missing = Object.values(src).filter((s) => s.status === "unavailable").map((s) => s.name);
  if (missing.length) out.push(`<div class="banner info">Нет данных по сетям: ${esc(missing.join(", "))}. Их цены в списке не учитываются.</div>`);
  return out.join("");
}

function badges(it) {
  const o = it.o, b = [];
  if (o.kind === "here") b.push(`<span class="badge ok">Цена по данным сети для этой станции</span>`);
  if (o.kind === "uniform") b.push(`<span class="badge ok">Единая цена сети${it.n > 1 ? ` · ${it.n} ст.` : ""}</span>`);
  if (o.kind === "ref") b.push(`<span class="badge warn">Ориентир: минимальная цена сети, в этом городе сеть цен не публикует${it.n > 1 ? ` · ${it.n} ст.` : ""}</span>`);
  if (o.kind === "min") b.push(`<span class="badge warn">Минимум по сети, здесь может быть выше${it.n > 1 ? ` · ${it.n} ст.` : ""}</span>`);
  const h = hoursSince(o.source_date);
  if (h != null && h > STALE_PRICE_HOURS) b.push(`<span class="badge bad">Цена устарела: от ${esc(fmtDate(o.source_date))}</span>`);
  return `<div class="badges">${b.join("")}</div>`;
}

function ageLine(it) {
  const o = it.o, p = [];
  if (o.changed_at) p.push(`Цена изменилась ${esc(ago(o.changed_at))}`);
  else if (o.source_date) p.push(`Цена от ${esc(fmtDate(o.source_date))} по данным сети`);
  if (o.checked_at) p.push(`проверено ${esc(ago(o.checked_at))}`);
  return `<div class="age">${p.join(" · ")}</div>`;
}

function card(it, best) {
  const st = it.st, o = it.o;
  const disc = S.useCard ? S.discounts[st.brand] || 0 : 0;
  const addr = [st.address, cityRu(st.city)].filter(Boolean).join(", ");
  const dist = it.dist != null ? `<div class="dist">${it.dist < 10 ? it.dist.toFixed(1) : Math.round(it.dist)} км</div>` : "";
  const cardLine = disc > 0
    ? `<div class="card-price">с картой <b>${fmtPrice(it.eff)}</b> €</div>`
    : "";
  return `<article class="card${best ? " best" : ""}">
    <div class="row">
      <div><div class="net">${esc(netName(st.brand))}</div><div class="addr">${esc(addr || st.name)}</div>${dist}</div>
      <div><div class="price">${fmtPrice(o.price)}<small>€/л</small></div>${cardLine}</div>
    </div>
    ${badges(it)}${ageLine(it)}
    <button class="go" type="button" data-go="${esc(st.id)}" aria-label="Маршрут до ${esc(netName(st.brand))} ${esc(addr)}">Поехать</button>
  </article>`;
}

function emptyHtml(title, text, extra = "") {
  return `<div class="empty"><h3>${esc(title)}</h3><p>${esc(text)}</p>${extra}</div>`;
}

function list(items, noun) {
  if (!items.length) return "";
  const shown = app.showAll ? items : items.slice(0, SHOW_FIRST);
  let html = shown.map((it, i) => card(it, i === 0)).join("");
  if (!app.showAll && items.length > SHOW_FIRST) html += `<button class="more" type="button" id="moreBtn">Показать все (${items.length})</button>`;
  return html;
}

function geoBlock() {
  const g = app.geo;
  if (g === "idle") return emptyHtml("Нужна ваша геопозиция", "Приложение найдёт самые выгодные заправки рядом. Место не отправляется никуда — расстояние считается на телефоне.", `<button class="primary" type="button" id="geoBtn">Включить геолокацию</button>`);
  if (g === "asking") return emptyHtml("Определяю место…", "Разрешите доступ к геопозиции в окне браузера.");
  if (g === "denied") return emptyHtml("Геолокация выключена", isIOS
    ? "iPhone: Настройки → Конфиденциальность → Службы геолокации → включите, затем для Safari (или для иконки приложения) выберите «При использовании». После этого нажмите кнопку."
    : "Android: нажмите на значок замка рядом с адресом → Разрешения → Местоположение → Разрешить. Также включите геолокацию в быстрых настройках телефона. Потом нажмите кнопку.", `<button class="primary" type="button" id="geoBtn">Проверить снова</button>`);
  if (g === "unavailable") return emptyHtml("Геолокация недоступна", "Этот браузер не поддерживает определение места. Откройте приложение в Chrome или Safari.");
  return emptyHtml("Не удалось определить место", "Включите геолокацию в телефоне и попробуйте ещё раз.", `<button class="primary" type="button" id="geoBtn">Повторить</button>`);
}

function render() {
  $("#cityName").textContent = cityRu(S.city);
  $("#fuels").innerHTML = ((app.data && app.data.meta.fuels) || Object.keys(FUEL_NAMES))
    .map((f) => `<button type="button" data-fuel="${esc(f)}" aria-pressed="${f === S.fuel}">${esc(FUEL_NAMES[f] || f)}</button>`).join("");
  document.querySelectorAll("#tabs button").forEach((b) => { if (b.dataset.tab === S.tab) b.setAttribute("aria-current", "page"); else b.removeAttribute("aria-current"); });
  $("#cityBtn").hidden = S.tab !== "city";
  const pt = $("#pageTitle");
  pt.hidden = S.tab === "city";
  pt.textContent = S.tab === "near" ? "Рядом со мной" : "Свежие цены";
  $("#banners").innerHTML = banners();
  const c = $("#content");
  if (!app.data) { c.innerHTML = emptyHtml(app.loadError ? "Не удалось загрузить цены" : "Загружаю цены…", app.loadError ? "Проверьте интернет и нажмите ⟳ сверху." : ""); return; }
  const stations = app.data.stations;
  const fname = FUEL_NAMES[S.fuel] || S.fuel;
  let html = "";
  if (S.tab === "city") {
    const items = sortByPrice(collect(stations, S.fuel, S, { city: S.city }));
    html = items.length
      ? `<p class="section-note">Самые выгодные: ${esc(fname)}, ${esc(cityRu(S.city))}</p>${list(items)}`
      : emptyHtml("Нет цен для этого города", `Для «${fname}» в городе ${cityRu(S.city)} данных нет. Выберите другой город или вид топлива — города без цен в списке серые.`, `<button class="primary" type="button" id="cityBtn2">Выбрать город</button>`);
  } else if (S.tab === "near") {
    if (app.geo !== "ok") html = geoBlock();
    else {
      const items = sortByPrice(collect(stations, S.fuel, S, { pos: app.pos, radius: S.radius }));
      html = `<p class="section-note">${esc(fname)} в радиусе ${S.radius} км · <button type="button" id="radiusBtn" style="text-decoration:underline;min-height:44px">изменить ⚙</button></p>` +
        (items.length ? list(items) : emptyHtml("В радиусе нет цен", `Для «${fname}» в ${S.radius} км данных нет. Увеличьте радиус в настройках.`));
    }
  } else {
    const pos = app.geo === "ok" ? app.pos : null;
    const items = sortFresh(collect(stations, S.fuel, S, { pos }));
    html = `<p class="section-note">Цена обновилась совсем недавно (${esc(fname)}). Точный момент смены известен только если мы сами её заметили — иначе показана дата сети.</p>` +
      (items.length ? list(items) : emptyHtml("Нет данных", `Для «${fname}» цен пока нет.`));
  }
  c.innerHTML = html;
}

/* ---------- окна ---------- */

function openCities() {
  const d = app.data;
  const counts = {};
  if (d) for (const st of d.stations) if (st.offers && st.offers[S.fuel]) counts[st.city] = (counts[st.city] || 0) + 1;
  const all = new Set(Object.keys(counts));
  if (d) for (const st of d.stations) all.add(st.city);
  const names = [...all].sort((a, b) => (counts[b] ? 1 : 0) - (counts[a] ? 1 : 0) || cityRu(a).localeCompare(cityRu(b), "ru"));
  $("#cityList").innerHTML = names.map((c) =>
    `<button type="button" class="city-item${counts[c] ? "" : " none"}" data-city="${esc(c)}" aria-current="${c === S.city}"><span>${esc(cityRu(c))}</span><small>${counts[c] ? `цен: ${counts[c]}` : "нет цен"}</small></button>`).join("");
  $("#citySheet").showModal();
}

function openSettings() {
  const nets = ["circlek", "virsi"];
  $("#settingsBody").innerHTML = `
    <div class="set-group"><h3>Радиус поиска: <span id="rv">${S.radius}</span> км</h3>
      <input type="range" id="radius" min="1" max="50" value="${S.radius}" aria-label="Радиус, км"></div>
    <div class="set-group"><h3>Скидка карты лояльности</h3>
      <p>Сколько центов с литра даёт ваша карта. Цена с картой = цена на табло − скидка.</p>
      ${nets.map((n) => `<div class="set-line"><label for="d-${n}">${esc(netName(n))}, цент/л</label><input type="number" id="d-${n}" data-disc="${n}" min="0" max="20" step="0.5" inputmode="decimal" value="${S.discounts[n] || 0}"></div>`).join("")}
      <div class="set-line"><label for="useCard">Сравнивать по цене с картой</label><input type="checkbox" id="useCard" ${S.useCard ? "checked" : ""}></div></div>
    <div class="set-group"><h3>Точность</h3>
      <div class="set-line"><label for="onlyExact">Только цены, привязанные к станции</label><input type="checkbox" id="onlyExact" ${S.onlyExact ? "checked" : ""}></div>
      <p>Сети публикуют минимум по городу, а не цену каждой станции. Без этого флажка такие цены показываются с пометкой.</p></div>
    <div class="set-group"><h3>Карты для маршрута</h3>
      <div class="set-line"><label for="mapApp">Открывать в</label><select id="mapApp"><option value="google"${S.mapApp === "google" ? " selected" : ""}>Google Maps</option><option value="apple"${S.mapApp === "apple" ? " selected" : ""}>Apple Maps</option></select></div></div>`;
  $("#settingsSheet").showModal();
}

/* ---------- события ---------- */

function bindEvents() {
document.addEventListener("click", (e) => {
  const t = e.target.closest("button");
  if (!t) return;
  if (t.dataset.fuel) { S.fuel = t.dataset.fuel; app.showAll = false; save(); render(); }
  else if (t.dataset.tab) { S.tab = t.dataset.tab; app.showAll = false; save(); if (S.tab === "near" && app.geo === "idle") askGeo(); render(); scrollTo(0, 0); }
  else if (t.dataset.go) {
    const st = app.data.stations.find((s) => s.id === t.dataset.go);
    if (st) window.open(mapUrl(st, S.mapApp), "_blank", "noopener");
  }
  else if (t.dataset.city) { S.city = t.dataset.city; save(); $("#citySheet").close(); render(); }
  else if (t.id === "cityBtn" || t.id === "cityBtn2") openCities();
  else if (t.id === "gearBtn" || t.id === "radiusBtn") openSettings();
  else if (t.id === "refreshBtn") load(true);
  else if (t.id === "moreBtn") { app.showAll = true; render(); }
  else if (t.id === "geoBtn") askGeo();
});

document.addEventListener("input", (e) => {
  const el = e.target;
  if (el.id === "radius") { S.radius = +el.value; $("#rv").textContent = el.value; }
  else if (el.dataset && el.dataset.disc) { S.discounts[el.dataset.disc] = Math.max(0, Math.min(20, parseFloat(el.value.replace(",", ".")) || 0)); }
  else if (el.id === "useCard") S.useCard = el.checked;
  else if (el.id === "onlyExact") S.onlyExact = el.checked;
  else if (el.id === "mapApp") S.mapApp = el.value;
  else return;
  save(); render();
});

document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") load(false); });

}

if (typeof document !== "undefined" && document.getElementById("main")) {
  bindEvents();
  render();
  load(true);
  if (S.tab === "near") askGeo();
  if ("serviceWorker" in navigator && location.protocol !== "file:") navigator.serviceWorker.register("sw.js").catch(() => {});
}
