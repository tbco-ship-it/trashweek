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

import guides_data

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
RANK10_SLUGS = {"philadelphia", "tucson", "milwaukee", "madison", "honolulu", "seattle", "roseville", "baton-rouge", "cambridge"}


def shift_text(iso, policy, overrides, observed=(), pending=(), skips=(), date_rule=None, unverified=()):
    """What a holiday does to that week's routes, in the words a resident needs: 'Thursday routes run Friday, Friday routes run Saturday'."""
    d = dt.date.fromisoformat(iso)
    wd = d.weekday()
    if date_rule == "no_change":
        return "Collection runs as usual"
    if date_rule == "tbd":
        return "Not confirmed — the city's schedule currently says TBD"
    if date_rule == "unverified" or iso in unverified:
        return "Not verified for this city — check the official notice"
    if date_rule == "thursday_only":
        return "Thursday routes run Friday; Friday routes stay on schedule"
    if date_rule == "skip":
        return f"No pickup on {LONG[DAYS[wd]]}; the city lists no make-up service"
    policy = date_rule if date_rule in ("next_day", "skip", "overrides", "no_change") else policy
    if policy == "no_change":
        return "Collection runs as usual"
    if policy == "overrides":
        if iso in skips:
            return f"No pickup on {LONG[DAYS[wd]]}; the city lists no make-up day"
        to = dict(overrides).get(iso)
        # knock-on moves the city lists for later days of the same week (Waco 11/11: Wed→Thu and Thu→Fri)
        later = [(a, b) for a, b in overrides if a != iso and dt.date.fromisoformat(a) > d and dt.date.fromisoformat(a).isocalendar()[:2] == d.isocalendar()[:2]]
        also = "".join(f", {LONG[DAYS[dt.date.fromisoformat(a).weekday()]]} pickup moves to {LONG[DAYS[dt.date.fromisoformat(b).weekday()]]} {dt.date.fromisoformat(b).strftime('%b')} {dt.date.fromisoformat(b).day}" for a, b in sorted(later))
        if to:
            t = dt.date.fromisoformat(to)
            return f"{LONG[DAYS[wd]]} pickup moves to {LONG[DAYS[t.weekday()]]} {t.strftime('%b')} {t.day}{also}"
        return f"No pickup on {LONG[DAYS[wd]]}; see the official notice for the make-up day"
    if wd >= 5:
        return f"Falls on a {LONG[DAYS[wd]]} — weekday routes are not affected"
    if policy == "skip":
        return f"{LONG[DAYS[wd]]} pickup is skipped; the next pickup is on your regular day"
    if policy == "next_day":
        # two weekday holidays in one week (Thanksgiving Thu+Fri): a one-line slide rule doesn't say where pickups land — same as app.js 'unconfirmed'
        week = [dt.date.fromisoformat(o) for o in observed]
        if any(o != d and o.isocalendar()[:2] == d.isocalendar()[:2] and o.weekday() < 5 for o in week):
            return "Two holidays this week — check the official notice for the make-up days"
        # A move onto an unresolved date is not confirmed; distinguish an unverified date from a not-yet-posted one.
        moves = []
        for i in range(wd, 5):
            affected = {(d + dt.timedelta(days=i - wd)).isoformat(), (d + dt.timedelta(days=i + 1 - wd)).isoformat()}
            if affected & set(unverified):
                moves.append(f"{LONG[DAYS[i]]} routes: not confirmed — handling on another holiday is unverified")
            elif affected & set(pending):
                moves.append(f"{LONG[DAYS[i]]} routes: not confirmed — a holiday the city hasn't posted yet")
            else:
                moves.append(f"{LONG[DAYS[i]]} routes run {LONG[DAYS[i + 1]]}")
        return ", ".join(moves)
    return "Not verified for this city — check the official notice"


def week_moves_earlier(iso, overrides):
    """True when every listed move for this holiday's week lands on an earlier date (Lexington: Thu/Fri → the Wednesday before); a mixed week stays 'Delayed'."""
    d = dt.date.fromisoformat(iso)
    moves = [(dt.date.fromisoformat(a), dt.date.fromisoformat(b)) for a, b in overrides]
    week = [(a, b) for a, b in moves if a >= d and a.isocalendar()[:2] == d.isocalendar()[:2]]
    return bool(week) and all(b < a for a, b in week)


def ordinal(n):
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def median(xs):
    xs = sorted(xs)
    return xs[len(xs) // 2] if len(xs) % 2 else (xs[len(xs) // 2 - 1] + xs[len(xs) // 2]) / 2


def compare_cities(cities):
    """City hub 'How X compares': numbers that differ per city, measured against every other city on the site."""
    zc = [c for c in cities if c["zones"]]
    by_n = sorted(zc, key=lambda c: -len(c["zones"]))
    twice_cities = [c for c in zc if sum(1 for z in c["zones"] if len(z["schedule"]["trash"]) >= 2) / len(c["zones"]) >= 0.5]
    verified = [c for c in cities if c["holidays"]["verified"]]
    med_h = median([len(c["holidays"]["change_obs26"]) for c in verified]) if verified else None
    for c in zc:
        n = len(c["zones"])
        top, top_n = c["day_counts"].most_common(1)[0]
        twice = sum(1 for z in c["zones"] if len(z["schedule"]["trash"]) >= 2)
        rec = sum(1 for z in c["zones"] if z["schedule"].get("recycling"))
        c["cmp"] = {
            "n": n, "rank": (f"{ordinal(by_n.index(c) + 1)} most" if by_n.index(c) < len(zc) / 2 else f"{ordinal(len(zc) - by_n.index(c))} fewest"), "of": len(zc), "med_n": median([len(x["zones"]) for x in zc]),
            "top": LONG[top], "top_pct": round(100 * top_n / n), "no_days": [LONG[d] for d in DAYS[:5] if not c["day_counts"][d]],
            "twice_pct": round(100 * twice / n), "twice_cities": len(twice_cities),
            "rec_pct": round(100 * rec / n), "ab_weeks": any(z["schedule"].get("recycling_week") for z in c["zones"]),
            "hol_n": len(c["holidays"]["change_obs26"]), "med_h": med_h, "n_verified": len(verified),
        }


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
    rank10_data = json.loads((ROOT / "data/rank10.json").read_text())
    rank10_cities = rank10_data["cities"]
    rank10_targets = rank10_data["targets"]
    bulk_leaf_rows = json.loads((ROOT / "data/bulk_leaf.json").read_text())
    bulk_leaf_by_slug = {}
    for row in bulk_leaf_rows:
        if row["slug"] in bulk_leaf_by_slug:
            raise SystemExit(f"data/bulk_leaf.json contains duplicate city slug {row['slug']!r}")
        bulk_leaf_by_slug[row["slug"]] = row
    if set(rank10_cities) != RANK10_SLUGS:
        raise SystemExit("data/rank10.json must list exactly the nine approved city slugs")
    expected_target_paths = {f"{slug}/" for slug in RANK10_SLUGS} | {"philadelphia/holidays/"}
    if {target["path"] for target in rank10_targets} != expected_target_paths or len(rank10_targets) != 10:
        raise SystemExit("data/rank10.json targets must use only the 10 existing target URLs")
    cities = []
    for f in sorted((ROOT / "data/normalized").glob("*.json")):
        c = json.loads(f.read_text())
        c["bulk_leaf"] = bulk_leaf_by_slug.get(c["slug"], {"bulk": {}, "leaf_yard": {}})
        h = hol_all.get(c["slug"], {})
        h = dict(h)
        verified_rows = h.get("verified_rows") or []
        if verified_rows:
            observed = [[row["date"], row["holiday"]] for row in verified_rows if row["status"] in ("change", "no_change")]
            pending = [[row["date"], row["holiday"]] for row in verified_rows if row["status"] == "tbd"]
            unverified = [[row["date"], row["holiday"]] for row in verified_rows if row["status"] == "unverified"]
            no_change_dates = [row["date"] for row in verified_rows if row["status"] == "no_change"]
            rule_for_change = h.get("confirmed_policy") or h.get("policy")
            date_rules = {}
            for row in verified_rows:
                status = row["status"]
                if status == "change":
                    row_rule = row.get("rule") or rule_for_change
                    if row_rule not in ("next_day", "skip", "overrides", "thursday_only"):
                        raise SystemExit(f"{c['slug']}: unsupported confirmed date policy {row_rule!r}")
                    date_rules[row["date"]] = row_rule
                elif status in ("no_change", "tbd", "unverified"):
                    date_rules[row["date"]] = status
            h.update({"observed": observed, "pending": pending, "unverified": unverified,
                      "no_change_dates": no_change_dates, "date_rules": date_rules})
        c["aliases"] = reg_aliases.get(c["slug"], [])
        # policy: next_day (rest of the week slides one day) · skip (that pickup is missed, next regular day) · overrides (explicit original→actual dates) · unknown (not verified: no shifting)
        policy = h.get("policy") or ("next_day" if h.get("observed") else "unknown")
        observed = h.get("observed") or []
        partial = h.get("coverage") == "partial" and bool(observed)
        no_change_dates = h.get("no_change_dates") or []
        date_rules = h.get("date_rules") or {}
        unverified = h.get("unverified") or []
        if partial:
            known_dates = {d for d, _ in observed} | {d for d, _ in h.get("pending") or []} | {d for d, _ in unverified}
            unverified.extend([row for row in HOLIDAYS_2026 if row[0].startswith("2026-") and row[0] not in known_dates])
            h["unverified"] = unverified
        c["holidays"] = {"observed": observed, "rule": h.get("rule") or "", "source": h.get("source") or c.get("holiday_url"), "checked": h.get("checked"),
                         "policy": policy, "verified": policy != "unknown" and not partial, "partial": partial,
                         "coverage": h.get("coverage") or ("unknown" if policy == "unknown" else "complete"),
                         "keep_title": bool(h.get("keep_title")),
                         "overrides": h.get("overrides") or [], "date_rules": date_rules,
                         "no_change_dates": no_change_dates, "unverified": unverified,
                         "pending": h.get("pending") or [],
                         "verified_rows": verified_rows,
                         "drop2": bool(h.get("no_second_in_holiday_week")),
                         "dates_source": h.get("dates_source") or "", "dates_note": h.get("dates_note") or ""}
        c["rank10"] = ({**rank10_cities[c["slug"]], "checked": rank10_data["checked"]}
                       if c["slug"] in rank10_cities else None)
        c["holidays"]["obs26"] = [o for o in observed if o[0].startswith("2026")]   # "N holidays in 2026" must not count Jan 2027 rows
        skip_dates = set(h.get("skips") or []) | {d for d, rule in date_rules.items() if rule == "skip"}
        c["holidays"]["skip_rows"] = [o for o in c["holidays"]["obs26"] if o[0] in skip_dates]   # observed days the city says have no make-up day
        if verified_rows:
            change_dates = {d for d, rule in date_rules.items() if rule in ("next_day", "skip", "overrides", "thursday_only")}
            c["holidays"]["change_obs26"] = [o for o in c["holidays"]["obs26"] if o[0] in change_dates]
        else:
            c["holidays"]["change_obs26"] = [o for o in c["holidays"]["obs26"] if o[0] not in set(no_change_dates)]
        c["holidays"]["unverified_dates"] = [d for d, _ in unverified]
        if c["slug"] == "philadelphia":
            c["holidays"]["obs26_weekdays"] = [o for o in c["holidays"]["obs26"] if dt.date.fromisoformat(o[0]).weekday() < 5]
            c["holidays"]["weekday_count26"] = len(c["holidays"]["obs26_weekdays"])
        c["hol"] = {"policy": c["holidays"]["policy"], "dates": [d for d, _ in observed if d not in no_change_dates], "overrides": c["holidays"]["overrides"], "drop2": bool(h.get("no_second_in_holiday_week")),
                    "pending": [d for d, _ in h.get("pending") or []], "skips": sorted(skip_dates)}
        if verified_rows:
            c["hol"].update({"rules": sorted(date_rules.items()), "noChanges": no_change_dates,
                             "unverified": [d for d, _ in unverified], "partial": partial})
        # New Year's 2027 falls inside the 120-day calendar window: a city that observed 1/1/2026 but hasn't posted 2027 gets it as pending, not a confirmed normal pickup
        obs_d = {d for d, _ in c["holidays"]["observed"]}
        if not partial and "2026-01-01" in obs_d and "2027-01-01" not in obs_d and "2027-01-01" not in c["hol"]["pending"]:
            h = {**h, "pending": (h.get("pending") or []) + [["2027-01-01", "New Year's Day"]]}
            c["hol"]["pending"].append("2027-01-01")
        pending_rows = h.get("pending") or []
        tbd_rows = [[row["date"], row["holiday"]] for row in verified_rows if row["status"] == "tbd"]
        tbd_dates = {d for d, _ in tbd_rows}
        c["holidays"]["pending"] = pending_rows
        c["holidays"]["tbd"] = tbd_rows
        c["holidays"]["unposted"] = [row for row in pending_rows if row[0] not in tbd_dates]
        pol = c["holidays"]["policy"]
        fold_reference = (not c["holidays"]["verified"] and not c["holidays"]["partial"]
                          and not c["holidays"]["verified_rows"])
        if fold_reference:
            rows = [tuple(row) for row in HOLIDAYS_2026]
            known_for_week = []
        elif partial:
            row_map = {d: n for d, n in HOLIDAYS_2026 if d.startswith("2026-")}
            row_map.update({d: n for d, n in observed})
            row_map.update({d: n for d, n in h.get("pending") or []})
            row_map.update({d: n for d, n in unverified})
            rows = sorted(row_map.items())
            known_for_week = [d for d, rule in date_rules.items() if rule in ("next_day", "skip", "overrides")]
        else:
            rows = [tuple(row) for row in (observed if observed else HOLIDAYS_2026)]
            explicit_tbd = [(row["date"], row["holiday"]) for row in verified_rows if row["status"] == "tbd"]
            row_dates = {d for d, _ in rows}
            rows = sorted(rows + [row for row in explicit_tbd if row[0] not in row_dates])
            known_for_week = [d for d, _ in observed if d not in no_change_dates]
        unverified_dates = {d for d, _ in unverified}
        c["hol_rows"] = [{"iso": d, "name": n, "wd": LONG[DAYS[dt.date.fromisoformat(d).weekday()]],
                          "shift": shift_text(d, pol, c["holidays"]["overrides"], known_for_week, c["hol"]["pending"], c["hol"]["skips"], date_rules.get(d), unverified_dates),
                          "weekend": dt.date.fromisoformat(d).weekday() >= 5, "skip": d in c["hol"]["skips"],
                          "no_change": date_rules.get(d) == "no_change", "unverified": d in unverified_dates,
                          "pending": date_rules.get(d) == "tbd",
                          "earlier": pol == "overrides" and week_moves_earlier(d, c["holidays"]["overrides"])} for d, n in rows]
        # pending: a holiday the city usually observes but has not posted for this year yet (Detroit 12/25) — shown, never applied as confirmed
        rendered_dates = {row["iso"] for row in c["hol_rows"]}
        pending_for_rows = [] if fold_reference else h.get("pending") or []
        c["hol_rows"] = sorted(c["hol_rows"] + [{"iso": d, "name": n, "wd": LONG[DAYS[dt.date.fromisoformat(d).weekday()]], "weekend": dt.date.fromisoformat(d).weekday() >= 5, "pending": True,
                                                  "shift": "Not posted by the city yet — check the official notice closer to the date"} for d, n in pending_for_rows if d not in rendered_dates], key=lambda r: r["iso"])
        if fold_reference and (len(c["hol_rows"]) != 13
                               or [(row["iso"], row["name"]) for row in c["hol_rows"]] != HOLIDAYS_2026):
            raise SystemExit(f"{c['slug']}: folded federal reference calendar must match the 13 federal dates")
        # no_change cities: the federal rows are shown for reference only — never a "next holiday that affects pickup" or "Delayed"
        week_start = today - dt.timedelta(days=today.weekday())
        week_end = week_start + dt.timedelta(days=6)
        c["hol_next"] = None if pol == "no_change" else next((r for r in c["hol_rows"] if r["iso"] >= today.isoformat() and not r.get("no_change")), None)
        c["hol_calendar_this_week"] = next((r for r in c["hol_rows"] if week_start <= dt.date.fromisoformat(r["iso"]) <= week_end), None)
        c["hol_this_week"] = None if pol == "no_change" else c["hol_calendar_this_week"]
        if c["rank10"] and c["rank10"].get("recycling_cycle") and today.year == 2026:
            cycle = c["rank10"]["recycling_cycle"]
            anchor = dt.date.fromisoformat(cycle["anchor_monday"])
            if week_start >= anchor:
                next_monday = week_start + dt.timedelta(days=7)
                if next_monday.year == anchor.year:
                    next_index = (next_monday - anchor).days // 7
                    next_label = cycle["anchor_label"] if next_index % 2 == 0 else ("A" if cycle["anchor_label"] == "B" else "B")
                    c["rank10"]["next_recycling_week"] = {"label": next_label, "date": f"{next_monday.strftime('%B')} {next_monday.day}, {next_monday.year}"}
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
    compare_cities(cities)

    h = hashlib.md5()
    for f in sorted((ROOT / "static").glob("*")):
        h.update(f.read_bytes())
    v = h.hexdigest()[:8]
    env = Environment(loader=FileSystemLoader(ROOT / "templates"), autoescape=select_autoescape(["html"]))
    env.filters["days_text"] = days_text
    env.globals.update(site=SITE, base=base, origin=origin, today=today.isoformat(), v=v, adsense_pub=args.adsense_pub,
                       DAYS=DAYS, LONG=LONG, KIND_LABEL=KIND_LABEL, KIND_COLOR=KIND_COLOR, HOLIDAYS=HOLIDAYS_2026, cities=cities,
                       n_zones=sum(len(c["zones"]) for c in cities), rank10_targets=rank10_targets)

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
    page_count = 0

    def write(path, template, sm=None, index=True, **ctx):
        nonlocal page_count
        out = DIST / path
        out.mkdir(parents=True, exist_ok=True)
        (out / "index.html").write_text(env.get_template(template).render(path=path, **ctx))
        page_count += 1
        if index:
            urls.append((sm or path.split("/")[0] or "core", path))

    write("", "index.html")
    for page in ("about", "methodology", "privacy", "terms", "contact"):
        write(f"{page}/", f"{page}.html")
    write("holidays/", "holidays.html")
    write("coverage/", "coverage.html")
    # guides: tables computed from the same processed city data as the city pages (see scripts/guides_data.py)
    g_hol = guides_data.holiday_guide(cities)
    g_bulk = guides_data.bulk_leaf_guide(cities, *guides_data.load_bulk_leaf())
    g_rec = guides_data.recycling_guide(cities)
    write("guide/", "guides.html", cards=guides_data.hub(cities, g_hol, g_bulk, g_rec), **guides_data.hub_faq(cities, g_hol, g_bulk, g_rec))
    write("guide/holiday-pickup-rules/", "guide_holiday_rules.html", g=g_hol)
    write("guide/bulk-trash-leaf-collection/", "guide_bulk_leaf.html", g=g_bulk)
    write("guide/every-other-week-recycling/", "guide_recycling_weeks.html", g=g_rec)
    for c in cities:
        write(f"{c['slug']}/", "city.html", c=c)
        write(f"{c['slug']}/holidays/", "city_holidays.html", c=c)
        for z in c["zones"]:
            write(f"{c['slug']}/zone/{z['slug']}/", "zone.html", index=False, c=c, z=z)

    # lastmod 없음: 빌드했다고 내용이 바뀐 것이 아니다. 구글은 lastmod 를 "consistently and
    # verifiably accurate" 할 때만 쓴다고 문서에 적어 두었고, 매 빌드마다 전 URL 에 오늘을 찍으면
    # 그 조건을 못 맞춘다. 정직하게 댈 날짜가 생기면 그때 URL 별로 넣는다.
    write_sitemaps(urls, origin, base)
    (DIST / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {origin}{base}sitemap.xml\n")
    (DIST / "404.html").write_text(env.get_template("404.html").render(path="404"))
    (DIST / ".nojekyll").write_text("")
    key = (ROOT / "static/indexnow-key.txt").read_text().strip()
    (DIST / f"{key}.txt").write_text(key + "\n")
    if args.adsense_pub:
        (DIST / "ads.txt").write_text(f"google.com, {args.adsense_pub}, DIRECT, f08c47fec0942fa0\n")
    if args.cname:
        (DIST / "CNAME").write_text(args.cname + "\n")
    print(f"built {page_count} pages ({len(cities)} cities, {sum(len(c['zones']) for c in cities)} zones; {len(urls)} sitemap URLs) -> {DIST}")


if __name__ == "__main__":
    main()
