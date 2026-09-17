#!/usr/bin/env python3
"""Generate the static TrashWeek site into dist/ from data/normalized/*.json."""
import argparse
import datetime as dt
import hashlib
import json
import re
import shutil
from collections import Counter
from pathlib import Path

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


def days_text(days):
    return " & ".join(LONG[d] for d in days) if days else "—"


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

    cities = []
    for f in sorted((ROOT / "data/normalized").glob("*.json")):
        c = json.loads(f.read_text())
        c["kinds"] = [k for k in ("trash", "recycling", "yard", "bulk") if any(z["schedule"].get(k) for z in c["zones"])]
        c["day_counts"] = Counter(d for z in c["zones"] for d in z["schedule"]["trash"])
        for z in c["zones"]:
            z["slug"] = re.sub(r"[^a-z0-9]+", "-", z["zone"].lower()).strip("-")
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
        geo = {"slug": c["slug"], "zones": [{"z": z["zone"], "u": z["slug"], "s": z["schedule"], "r": z["rings"]} for z in c["zones"]]}
        (DIST / "static/geo" / f"{c['slug']}.json").write_text(json.dumps(geo, separators=(",", ":")))
    (DIST / "static/cities.json").write_text(json.dumps([{"slug": c["slug"], "city": c["city"], "state": c["state"], "n": len(c["zones"])} for c in cities], separators=(",", ":")))

    urls = []

    def write(path, template, **ctx):
        out = DIST / path
        out.mkdir(parents=True, exist_ok=True)
        (out / "index.html").write_text(env.get_template(template).render(path=path, **ctx))
        urls.append(path)

    write("", "index.html")
    for page in ("about", "methodology", "privacy", "contact"):
        write(f"{page}/", f"{page}.html")
    write("holidays/", "holidays.html")
    for c in cities:
        write(f"{c['slug']}/", "city.html", c=c)
        write(f"{c['slug']}/holidays/", "city_holidays.html", c=c)
        for z in c["zones"]:
            write(f"{c['slug']}/zone/{z['slug']}/", "zone.html", c=c, z=z)

    sm = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in urls:
        sm.append(f"<url><loc>{origin}{base}{u}</loc><lastmod>{today.isoformat()}</lastmod></url>")
    sm.append("</urlset>")
    (DIST / "sitemap.xml").write_text("\n".join(sm))
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
