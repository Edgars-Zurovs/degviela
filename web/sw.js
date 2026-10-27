const SHELL = "fuel-shell-v1";
const FILES = ["./", "index.html", "styles.css", "app.js", "manifest.webmanifest", "icons/icon-192.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(SHELL).then((c) => c.addAll(FILES)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== SHELL && k !== "fuel-data").map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) return;
  if (url.pathname.endsWith("/data/offers.json")) {
    // данные: сначала сеть, при отсутствии связи — последняя копия
    e.respondWith(fetch(e.request).then((r) => {
      const copy = r.clone();
      caches.open("fuel-data").then((c) => c.put("data/offers.json", copy));
      return r;
    }).catch(() => caches.match("data/offers.json")));
    return;
  }
  // оболочка: из кэша, но обновляем в фоне, чтобы правки доезжали
  e.respondWith(caches.match(e.request).then((hit) => {
    const net = fetch(e.request).then((r) => { caches.open(SHELL).then((c) => c.put(e.request, r.clone())); return r; }).catch(() => hit);
    return hit || net;
  }));
});
