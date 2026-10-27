// node web/tests.js — проверка чистой логики
const assert = require("assert");
global.navigator = { userAgent: "node" };
global.localStorage = { getItem: () => null, setItem() {} };
const A = require("./app.js");
const S = { discounts: { circlek: 5 }, useCard: true, onlyExact: false };
const mk = (id, brand, city, lat, lon, o) => ({ id, brand, city, lat, lon, offers: { 95: o } });
const o = (price, kind, extra = {}) => ({ price, kind, source_date: "2026-10-26", checked_at: "2026-10-27T08:00:00Z", changed_at: null, ...extra });
const st = [
  mk("a", "circlek", "Rīga", 56.95, 24.10, o(1.954, "here")),
  mk("b", "virsi", "Rīga", 56.96, 24.11, o(1.889, "here")),
  mk("c", "virsi", "Rīga", 56.90, 24.20, o(1.889, "min")),
  mk("d", "virsi", "Rīga", 56.91, 24.21, o(1.889, "min")),
  mk("e", "virsi", "Jūrmala", 56.97, 23.78, o(1.889, "min")),
];
let r = A.sortByPrice(A.collect(st, "95", S, { city: "Rīga" }));
assert.equal(r.length, 3, "min-станции схлопнуты в группу");
assert.equal(r[0].st.id, "b", "here раньше min при равной цене");
assert.equal(r[2].st.id, "a");
assert.equal(r.find((x) => x.o.kind === "min").n, 2);
// скидка карты меняет порядок
const S2 = { discounts: { circlek: 15 }, useCard: true, onlyExact: false };
r = A.sortByPrice(A.collect(st, "95", S2, { city: "Rīga" }));
assert.equal(r[0].st.id, "a");
assert.ok(Math.abs(r[0].eff - 1.804) < 1e-9);
// только точные
r = A.collect(st, "95", { ...S, onlyExact: true }, { city: "Rīga" });
assert.equal(r.length, 2);
// радиус
const pos = { lat: 56.95, lon: 24.10 };
r = A.collect(st, "95", S, { pos, radius: 5 });
assert.deepEqual(r.map((x) => x.st.id).sort(), ["a", "b"]);
assert.ok(A.haversineKm(56.9496, 24.1052, 56.5047, 21.0108) > 185);
// свежие: changed_at важнее даты сети, не больше 3 на сеть
const fr = [1, 2, 3, 4, 5].map((i) => mk("v" + i, "virsi", "Rīga", 0, 0, o(1.9 + i / 100, "here", { changed_at: `2026-10-27T0${i}:00:00Z` })));
fr.push(mk("w", "circlek", "Rīga", 0, 0, o(2, "here", { changed_at: "2026-10-26T01:00:00Z" })));
r = A.sortFresh(A.collect(fr, "95", S, {}));
assert.deepEqual(r.map((x) => x.st.id), ["v5", "v4", "v3", "w"]);
assert.ok(A.mapUrl({ lat: 1, lon: 2 }, "apple").startsWith("https://maps.apple.com/?daddr=1,2"));
assert.equal(A.fmtPrice(1.954), "1,954");
console.log("JS tests OK");
