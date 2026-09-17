// trashweek-api: read-only proxy for ReCollect's public widget API (which sends no CORS headers).
// GET /recollect/suggest?area=FortWorth&q=10000+Leeway
// GET /recollect/events?area=FortWorth&place=<id>&service=314&after=YYYY-MM-DD&before=YYYY-MM-DD
const AREAS = new Set(["PhoenixAZ", "CityofJacksonvilleFL", "FortWorth", "MemphisTN", "Austin", "recology-1051"]);
const ORIGINS = new Set(["https://trashweek.com", "https://www.trashweek.com", "https://tbco-ship-it.github.io"]);
const cors = (req) => { const o = req.headers.get("Origin") || ""; return { "Access-Control-Allow-Origin": ORIGINS.has(o) ? o : "https://trashweek.com", "Vary": "Origin", "Access-Control-Allow-Methods": "GET", "Cache-Control": "public, max-age=600" }; };
export default {
  async fetch(req, env, ctx) {
    const url = new URL(req.url);
    const h = cors(req);
    if (req.method === "OPTIONS") return new Response(null, { headers: h });
    const area = url.searchParams.get("area") || "";
    if (!AREAS.has(area)) return new Response(JSON.stringify({ error: "unknown area" }), { status: 400, headers: { ...h, "content-type": "application/json" } });
    let upstream;
    if (url.pathname === "/recollect/suggest") {
      const q = (url.searchParams.get("q") || "").slice(0, 120);
      if (q.length < 3) return new Response("[]", { headers: { ...h, "content-type": "application/json" } });
      upstream = `https://api.recollect.net/api/areas/${encodeURIComponent(area)}/services/waste/address-suggest?q=${encodeURIComponent(q)}&locale=en-US`;
    } else if (url.pathname === "/recollect/events") {
      const place = url.searchParams.get("place") || "", service = url.searchParams.get("service") || "";
      const after = url.searchParams.get("after") || "", before = url.searchParams.get("before") || "";
      if (!/^[0-9A-F-]{36}$/i.test(place) || !/^\d{1,6}$/.test(service) || !/^\d{4}-\d{2}-\d{2}$/.test(after) || !/^\d{4}-\d{2}-\d{2}$/.test(before)) return new Response(JSON.stringify({ error: "bad params" }), { status: 400, headers: { ...h, "content-type": "application/json" } });
      upstream = `https://api.recollect.net/api/places/${place}/services/${service}/events?nomerge=1&hide=reminder_only&after=${after}&before=${before}&locale=en-US`;
    } else {
      return new Response("not found", { status: 404, headers: h });
    }
    const cache = caches.default; const ck = new Request(upstream, { method: "GET" });
    let res = await cache.match(ck);
    if (!res) {
      res = await fetch(upstream, { headers: { "User-Agent": "Mozilla/5.0 (compatible; TrashWeek/1.0; +https://trashweek.com)", "Accept": "application/json" } });
      res = new Response(res.body, res); res.headers.set("Cache-Control", "public, max-age=600");
      ctx.waitUntil(cache.put(ck, res.clone()));
    }
    const out = new Response(res.body, res);
    for (const [k, v] of Object.entries(h)) out.headers.set(k, v);
    out.headers.set("content-type", "application/json; charset=utf-8");
    return out;
  }
};
