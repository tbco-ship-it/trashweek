#!/usr/bin/env python3
"""Generate the static TrashWeek site into dist/ from data/normalized/*.json."""
import argparse
import datetime as dt
import hashlib
import json
import re
import shutil
from collections import Counter, defaultdict
from pathlib import Path
from xml.sax.saxutils import escape

from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
SITE = "TrashWeek"
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
LONG = {"Mon": "Monday", "Tue": "Tuesday", "Wed": "Wednesday", "Thu": "Thursday", "Fri": "Friday", "Sat": "Saturday", "Sun": "Sunday"}
KIND_LABEL = {"trash": "Trash", "recycling": "Recycling", "yard": "Yard waste", "bulk": "Bulk items"}
KIND_COLOR = {"trash": "#3182f6", "recycling": "#00b06f", "yard": "#8b5cf6", "bulk": "#ff7a00"}
# 2026 US federal holidays that most municipal haulers observe (city-specific rules linked from each hub)
HOLIDAYS_2026 = [("2026-01-01", "New Year's Day"), ("2026-01-19", "Martin Luther King Jr. Day"), ("2026-02-16", "Presidents' Day"),
                 ("2026-05-25", "Memorial Day"), ("2026-06-19", "Juneteenth"), ("2026-07-03", "Independence Day (observed)"), ("2026-07-04", "Independence Day"),
                 ("2026-09-07", "Labor Day"), ("2026-10-12", "Columbus Day"), ("2026-11-11", "Veterans Day"), ("2026-11-26", "Thanksgiving Day"),
                 ("2026-12-25", "Christmas Day"), ("2027-01-01", "New Year's Day")]


def shift_text(iso, policy, overrides):
    """What a holiday does to that week's routes, in the words a resident needs: 'Thursday routes run Friday, Friday routes run Saturday'."""
    d = dt.date.fromisoformat(iso)
    wd = d.weekday()
    if policy == "overrides":
        to = dict(overrides).get(iso)
        if to:
            t = dt.date.fromisoformat(to)
            return f"{LONG[DAYS[wd]]} pickup moves to {LONG[DAYS[t.weekday()]]} {t.strftime('%b')} {t.day}"
        return f"No pickup on {LONG[DAYS[wd]]}; see the official notice for the make-up day"
    if wd >= 5:
        return f"Falls on a {LONG[DAYS[wd]]} — weekday routes are not affected"
    if policy == "skip":
        return f"{LONG[DAYS[wd]]} pickup is skipped; the next pickup is on your regular day"
    if policy == "next_day":
        moves = [f"{LONG[DAYS[i]]} routes run {LONG[DAYS[i + 1]]}" for i in range(wd, 5)]
        return ", ".join(moves)
    return "Not verified for this city — check the official notice"


def days_text(days):
    return " & ".join(LONG[d] for d in days) if days else "—"



def write_sitemaps(urls, origin, base, lastmod=None, limit=5000):
    """One sitemap index plus a file per section, so Search Console reports coverage per section
    instead of one opaque pile. urls is a list of (shard, path)."""
    shards = defaultdict(list)
    for shard, u in urls:
        shards[shard].append(u)
    for k in [k for k, v in shards.items() if len(v) < 10 and k != "core"]:
        shards["core"] += shards.pop(k)
    out = DIST / "sitemaps"
    out.mkdir(parents=True, exist_ok=True)
    names = []
    for shard in sorted(shards):
        rows = shards[shard]
        parts = [rows[i:i + limit] for i in range(0, len(rows), limit)] or [[]]
        for n, part in enumerate(parts, 1):
            fn = f"{shard}.xml" if len(parts) == 1 else f"{shard}-{n}.xml"
            lm = f"<lastmod>{lastmod}</lastmod>" if lastmod else ""
            body = "\n".join(f"<url><loc>{escape(origin + base + u)}</loc>{lm}</url>" for u in part)
            (out / fn).write_text('<?xml version="1.0" encoding="UTF-8"?>\n'
                                  '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                                  + body + "\n</urlset>")
            names.append(fn)
    idx = "".join(f"<sitemap><loc>{origin}{base}sitemaps/{n}</loc></sitemap>" for n in names)
    (DIST / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n'
                                      '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                                      + idx + "</sitemapindex>")
    return names


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="/")
    ap.add_argument("--origin", default="https://trashweek.com")
    ap.add_argument("--cname", default="trashweek.com")
    ap.add_argument("--adsense-pub", default="pub-8425563704095379")
    args = ap.parse_args()
    base = args.base if args.base.endswith("/") else args.base + "/"
    origin = args.origin.rstrip("/")
    today = dt.date.today()

    reg_aliases = {k: v.get("aliases", []) for k, v in json.loads((ROOT / "data/registry.json").read_text()).items()}
    hol_all = json.loads((ROOT / "data/holidays.json").read_text()) if (ROOT / "data/holidays.json").exists() else {}
    cities = []
    for f in sorted((ROOT / "data/normalized").glob("*.json")):
        c = json.loads(f.read_text())
        h = hol_all.get(c["slug"], {})
        c["aliases"] = reg_aliases.get(c["slug"], [])
        # policy: next_day (rest of the week slides one day) · skip (that pickup is missed, next regular day) · overrides (explicit original→actual dates) · unknown (not verified: no shifting)
        c["holidays"] = {"observed": h.get("observed") or [], "rule": h.get("rule") or "", "source": h.get("source") or c.get("holiday_url"), "checked": h.get("checked"),
                         "policy": h.get("policy") or ("next_day" if h.get("observed") else "unknown"), "overrides": h.get("overrides") or []}
        c["hol"] = {"policy": c["holidays"]["policy"], "dates": [d for d, _ in c["holidays"]["observed"]], "overrides": c["holidays"]["overrides"]}
        pol = c["holidays"]["policy"]
        rows = c["holidays"]["observed"] if c["holidays"]["observed"] else HOLIDAYS_2026
        c["hol_rows"] = [{"iso": d, "name": n, "wd": LONG[DAYS[dt.date.fromisoformat(d).weekday()]], "shift": shift_text(d, pol, c["holidays"]["overrides"]),
                          "weekend": dt.date.fromisoformat(d).weekday() >= 5} for d, n in rows]
        c["hol_next"] = next((r for r in c["hol_rows"] if r["iso"] >= today.isoformat()), None)
        c["hol_this_week"] = next((r for r in c["hol_rows"] if today - dt.timedelta(days=today.weekday()) <= dt.date.fromisoformat(r["iso"]) <= today + dt.timedelta(days=6 - today.weekday())), None)
        c["kinds"] = [k for k in ("trash", "recycling", "yard", "bulk") if any(z["schedule"].get(k) for z in c["zones"])]
        c["day_counts"] = Counter(d for z in c["zones"] for d in z["schedule"]["trash"])
        for z in c["zones"]:
            z["slug"] = re.sub(r"[^a-z0-9]+", "-", z["zone"].lower()).strip("-")
        # zone ids that differ only in case/punctuation (GRAY vs gray) must not share a URL
        seen_slugs = {}
        for z in c["zones"]:
            n = seen_slugs.get(z["slug"], 0) + 1
            seen_slugs[z["slug"]] = n
            if n > 1:
                z["slug"] = f"{z['slug']}-{n}"
        c["zones"].sort(key=lambda z: (DAYS.index(z["schedule"]["trash"][0]) if z["schedule"]["trash"] else 9, z["zone"]))
        cities.append(c)
    cities.sort(key=lambda c: c["city"])

    h = hashlib.md5()
    for f in sorted((ROOT / "static").glob("*")):
        h.update(f.read_bytes())
    v = h.hexdigest()[:8]
    env = Environment(loader=FileSystemLoader(ROOT / "templates"), autoescape=select_autoescape(["html"]))
    env.filters["days_text"] = days_text
    env.globals.update(site=SITE, base=base, origin=origin, today=today.isoformat(), v=v, adsense_pub=args.adsense_pub,
                       DAYS=DAYS, LONG=LONG, KIND_LABEL=KIND_LABEL, KIND_COLOR=KIND_COLOR, HOLIDAYS=HOLIDAYS_2026, cities=cities,
                       n_zones=sum(len(c["zones"]) for c in cities))

    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir()
    shutil.copytree(ROOT / "static", DIST / "static")
    (DIST / "static/geo").mkdir()
    # per-city geometry for the in-browser address lookup (loaded on demand)
    for c in cities:
        if not c["zones"]:
            continue
        geo = {"slug": c["slug"], "holidays": [d for d, _ in c["holidays"]["observed"]], "hol": c["hol"], "zones": [{"z": z["zone"], "u": z["slug"], "s": z["schedule"], "r": z["rings"]} for z in c["zones"]]}
        (DIST / "static/geo" / f"{c['slug']}.json").write_text(json.dumps(geo, separators=(",", ":")))
    (DIST / "static/cities.json").write_text(json.dumps([{"slug": c["slug"], "city": c["city"], "state": c["state"], "n": len(c["zones"]), "kind": c.get("kind", "arcgis"), "area": c.get("area"), "service": c.get("service"), "aliases": c.get("aliases", [])} for c in cities], separators=(",", ":")))

    # ReCollect areas used by the site must be allow-listed in the deployed Worker (deployed by hand): fail loudly if the file drifts
    worker = (ROOT / "worker/recollect-proxy.mjs").read_text()
    missing = [c["area"] for c in cities if c.get("kind") == "recollect" and f'"{c["area"]}"' not in worker]
    if missing:
        raise SystemExit(f"worker/recollect-proxy.mjs AREAS is missing: {missing}")

    urls = []

    def write(path, template, sm=None, **ctx):
        out = DIST / path
        out.mkdir(parents=True, exist_ok=True)
        (out / "index.html").write_text(env.get_template(template).render(path=path, **ctx))
        urls.append((sm or path.split("/")[0] or "core", path))

    write("", "index.html")
    for page in ("about", "methodology", "privacy", "contact"):
        write(f"{page}/", f"{page}.html")
    write("holidays/", "holidays.html")
    write("coverage/", "coverage.html")
    for c in cities:
        write(f"{c['slug']}/", "city.html", c=c)
        write(f"{c['slug']}/holidays/", "city_holidays.html", c=c)
        for z in c["zones"]:
            write(f"{c['slug']}/zone/{z['slug']}/", "zone.html", c=c, z=z)

    write_sitemaps(urls, origin, base, today.isoformat())
    (DIST / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {origin}{base}sitemap.xml\n")
    (DIST / "404.html").write_text(env.get_template("404.html").render(path="404"))
    (DIST / ".nojekyll").write_text("")
    key = (ROOT / "static/indexnow-key.txt").read_text().strip()
    (DIST / f"{key}.txt").write_text(key + "\n")
    if args.adsense_pub:
        (DIST / "ads.txt").write_text(f"google.com, {args.adsense_pub}, DIRECT, f08c47fec0942fa0\n")
    if args.cname:
        (DIST / "CNAME").write_text(args.cname + "\n")
    print(f"built {len(urls)} pages ({len(cities)} cities, {sum(len(c['zones']) for c in cities)} zones) -> {DIST}")


if __name__ == "__main__":
    main()
