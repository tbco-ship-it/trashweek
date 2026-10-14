"""Numbers and tables for the /guide/ pages.

Everything here is computed at build time from data the city pages already use
(data/holidays.json via the processed `cities`, data/bulk_leaf.json, data/normalized/*.json),
so a guide can never say something the city pages don't. A claim that needs a human reading of
free text (bulk fee kind, leaf bag rule) lives in data/guide_classes.json, pinned to the
sha256 of bulk_leaf.json: change the source file and the build stops until the classes are re-read.
"""
import datetime as dt
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# the three holidays that matter for a November-January guide (2026-01-01 has already passed)
HOLIDAY_COLS = [("2026-11-26", "Thanksgiving Day"), ("2026-12-25", "Christmas Day"), ("2027-01-01", "New Year's Day")]

MODEL_LABEL = {
    "next_day": "One-day slide",
    "thursday_only": "Thursday routes slide",
    "skip": "Pickup skipped, no slide",
    "nomakeup": "No pickup, no make-up day",
    "overrides": "Moved to a make-up day",
    "earlier": "Moved earlier",
    "normal": "Runs as usual",
    "check": "See the city notice",
    "pending": "Not posted yet",
    "unverified": "Not verified",
    "unlisted": "Not on the city's holiday list",
}

# worked examples are picked from these when they are verified with the matching policy, else the first city that is
EXAMPLE_PREFS = {"next_day": ["seattle", "philadelphia", "worcester"], "skip": ["miami-dade", "baton-rouge"],
                 "overrides": ["lexington", "oklahoma-city", "waco"], "no_change": ["roseville"]}

EOW_RE = re.compile(r"recycling[^.;]*every other week|every other week \(week A or B\)|alternate weeks", re.I)
TWICE_NOTE_RE = re.compile(r"twice[- ]weekly|twice a week", re.I)

FEE_LABEL = {
    "included": "Free or included in the service fee",
    "allowance_then_fee": "Free allowance, then a fee",
    "amount": "Fee with a dollar amount",
    "fee_no_amount": "Fee mentioned, no amount given",
}
BAG_LABEL = {
    "paper_no_plastic": "Paper bags named, plastic not accepted",
    "paper": "Paper, compostable or biodegradable bags named",
    "no_plastic": "Plastic bags not accepted",
    "plastic": "Plastic bags named",
    "bags_unspecified": "Bags allowed, material not specified",
    "other": "Other container, bundle or loose-leaf rule",
}
PERIOD_LABEL = {
    "program": "Fall or seasonal leaf program",
    "season_window": "Yard-waste season with start and end dates",
    "regular": "Regular weekly or alternating-week service",
    "appointment": "By appointment",
}
# Detroit's captured fee line reads as a fragment; the display wording is fixed and carries no dollar amount
DISPLAY_OVERRIDES = {("detroit", "fee"): ("Information on how to arrange for paid collection",
                                          "Paid collection — arrange through the city's bulk collection page")}


def _date_long(iso):
    d = dt.date.fromisoformat(iso)
    return f"{d.strftime('%a')}, {d.strftime('%b')} {d.day}, {d.year}"


def _present(v):
    return bool(v) and v != "not_found"


def _names(cities, n=None):
    """'A, B and C' from city dicts (at most n, then 'and N more')."""
    names = [f"{c['city']} ({c['state']})" for c in cities]
    extra = 0
    if n is not None and len(names) > n:
        extra, names = len(names) - n, names[:n]
    if extra:
        return ", ".join(names) + f" and {extra} more"
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1] if names else ""


def _ld(faq):
    return [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]


def _n(n, many, one):
    """'19 slide' / '1 slides': the verb agrees with the count."""
    return f"{n} {one if n == 1 else many}"


def _by_slug(cities):
    return {c["slug"]: c for c in cities}


# ---------------------------------------------------------------- holiday rules guide

def _cell(c, iso):
    rows = {r["iso"]: r for r in c["hol_rows"]}
    r = rows.get(iso)
    pol = c["holidays"]["policy"]
    if r is None:
        return {"kind": "unlisted", "detail": ""}
    if r.get("pending"):
        return {"kind": "pending", "detail": r["shift"]}
    if r.get("unverified"):
        return {"kind": "unverified", "detail": r["shift"]}
    rule = (c["holidays"].get("date_rules") or {}).get(iso) or pol
    if r.get("no_change") or rule == "no_change":
        kind = "normal"
    elif r.get("skip"):
        kind = "nomakeup"
    elif rule == "skip":
        kind = "skip"
    elif rule == "overrides":
        kind = "check" if not dict(c["holidays"]["overrides"]).get(iso) else ("earlier" if r.get("earlier") else "overrides")
    elif rule in ("next_day", "thursday_only"):
        kind = rule
    else:
        kind = "unverified"
    if r["shift"].startswith("Two holidays"):
        kind = "check"   # two weekday holidays in one week: the one-line slide rule does not say where pickups land
    return {"kind": kind, "detail": r["shift"]}


def holiday_guide(cities):
    verified = [c for c in cities if c["holidays"]["policy"] != "unknown" and c["holidays"].get("verified", True)]
    rows = []
    for c in sorted(verified, key=lambda c: c["city"]):
        cells = [_cell(c, iso) for iso, _ in HOLIDAY_COLS]
        for cell in cells:
            cell["label"] = MODEL_LABEL[cell["kind"]]
        rows.append({"c": c, "cells": cells})

    by_pol = {p: [c for c in verified if c["holidays"]["policy"] == p] for p in ("next_day", "skip", "overrides", "no_change")}
    earlier = [c for c in by_pol["overrides"] if any(r.get("earlier") for r in c["hol_rows"])]
    later = [c for c in by_pol["overrides"]
             if any(b > a for a, b in c["holidays"]["overrides"])]
    # a city can run as usual on some holidays only (date-level rows); a whole-policy no_change city runs as usual on all
    normal = []
    for c in verified:
        if c["holidays"]["policy"] == "no_change":
            normal.append({"c": c, "all": True, "n": 0})
            continue
        n = sum(1 for r in c["hol_rows"] if r.get("no_change") and r["iso"].startswith("2026"))
        if n:
            normal.append({"c": c, "all": False, "n": n})

    def example(policy):
        pool = by_pol[policy]
        if not pool:
            return None
        pick = next((c for slug in EXAMPLE_PREFS[policy] for c in pool if c["slug"] == slug), None) or pool[0]
        for iso, _ in HOLIDAY_COLS:   # first of the three dates on which this city actually shows a rule
            cell = _cell(pick, iso)
            if cell["kind"] not in ("unlisted", "pending", "unverified"):
                return {"c": pick, "cell": cell, "date": _date_long(iso)}
        return {"c": pick, "cell": None, "date": None}

    checked = max((c["holidays"]["checked"] for c in verified if c["holidays"].get("checked")), default=None)
    n_v, n_u = len(verified), len(cities) - len(verified)
    faq = [
        ("Does trash pickup run on Thanksgiving, Christmas and New Year's Day?",
         f"It depends on the city. Among the {n_v} cities whose holiday notice TrashWeek has read and verified, {_n(len(by_pol['next_day']), 'slide', 'slides')} the rest of the week by one day, "
         f"{_n(len(by_pol['skip']), 'skip', 'skips')} that pickup without sliding the week, {_n(len(by_pol['overrides']), 'publish', 'publishes')} specific make-up days and "
         f"{_n(len(by_pol['no_change']), 'collect', 'collects')} as usual on holidays. "
         "Open your city's holiday page for its exact Thanksgiving, Christmas and New Year's Day rule."),
        ("What is a one-day slide?",
         "When a holiday falls on a weekday, every route from the holiday to the end of that week runs one day later: a Thursday holiday moves Thursday routes to Friday and Friday routes to Saturday. "
         "Routes earlier in the week are not affected."),
        ("What if my city is not on the verified list?",
         f"{n_u} of the {len(cities)} cities on TrashWeek are not fully verified yet: their pages shift only the dates that are confirmed and otherwise show the federal holiday calendar. "
         "For those cities, the city's own notice decides."),
    ]
    return {
        "cols": [{"iso": iso, "name": name, "long": _date_long(iso)} for iso, name in HOLIDAY_COLS],
        "rows": rows, "n_verified": n_v, "n_cities": len(cities), "n_unverified": n_u,
        "by_pol": by_pol, "earlier": earlier, "later": later, "normal": normal,
        "examples": {p: example(p) for p in by_pol}, "checked": checked,
        "model_label": MODEL_LABEL, "faq": faq, "faq_ld": _ld(faq),
    }


# ---------------------------------------------------------------- bulk and leaf guide

def load_bulk_leaf():
    raw = (ROOT / "data/bulk_leaf.json").read_bytes()
    classes = json.loads((ROOT / "data/guide_classes.json").read_text())
    if classes["bulk_leaf_sha256"] != hashlib.sha256(raw).hexdigest():
        raise SystemExit("data/bulk_leaf.json changed: re-read the fee / bag / period classes in data/guide_classes.json and update its bulk_leaf_sha256")
    return json.loads(raw), classes


def bulk_leaf_guide(cities, records, classes):
    cmap = _by_slug(cities)
    rows = []
    for r in records:
        slug = r["slug"]
        if slug not in cmap:
            raise SystemExit(f"bulk_leaf.json has {slug!r}, which is not a city on the site")
        b, ly = r["bulk"], r["leaf_yard"]
        fee, limits = (b.get("fee"), b.get("limits"))
        ov = DISPLAY_OVERRIDES.get((slug, "fee"))
        if ov and fee == ov[0]:
            fee = ov[1]
        row = {
            "c": cmap[slug],
            "fee": fee if _present(fee) else "", "limits": limits if _present(limits) else "",
            "period": ly.get("period") if _present(ly.get("period")) else "",
            "bags": ly.get("bag_rules") if _present(ly.get("bag_rules")) else "",
            "fee_cls": classes["fee"].get(slug), "bag_cls": classes["bag"].get(slug), "period_cls": classes["period"].get(slug),
            "bulk_src": b.get("src_url") or "", "leaf_src": ly.get("src_url") or "",
        }
        # a class without text (or text without a class) means the pinned classes drifted from the data
        if bool(row["fee_cls"]) and not (row["fee"] or row["limits"]) or (row["fee"] and not row["fee_cls"]):
            raise SystemExit(f"guide_classes.json: fee class mismatch for {slug}")
        if bool(row["bags"]) != bool(row["bag_cls"]) or bool(row["period"]) != bool(row["period_cls"]):
            raise SystemExit(f"guide_classes.json: bag/period class mismatch for {slug}")
        rows.append(row)
    rows.sort(key=lambda x: x["c"]["city"])
    bulk_rows = [x for x in rows if x["fee"] or x["limits"]]
    leaf_rows = [x for x in rows if x["period"] or x["bags"]]

    def group(key, labels, src=rows):
        return [{"key": k, "label": lab, "cities": [x["c"] for x in src if x[key] == k]} for k, lab in labels.items()]

    captured = sorted({m.group(1) for r in records for sec in (r["bulk"], r["leaf_yard"])
                       for fs in (sec.get("field_source") or {}).values()
                       for m in [re.search(r"_(\d{8})/", fs.get("file", ""))] if m})
    cap = [f"{d[:4]}-{d[4:6]}-{d[6:]}" for d in captured]
    special = {s: next((x for x in rows if x["c"]["slug"] == s), None) for s in ("worcester", "detroit", "new-haven")}
    fg = {g["key"]: g["cities"] for g in group("fee_cls", FEE_LABEL)}
    bg = {g["key"]: g["cities"] for g in group("bag_cls", BAG_LABEL)}
    pg = {g["key"]: g["cities"] for g in group("period_cls", PERIOD_LABEL)}
    n_fee = sum(1 for x in rows if x["fee_cls"])
    faq = [
        ("Is bulky-item pickup free?",
         f"It depends on the city. Of the {n_fee} cities whose notice says what bulky pickup costs, {len(fg['included'])} say it is free or included in the service fee, "
         f"{len(fg['allowance_then_fee'])} give a free allowance and charge after it, {len(fg['amount'])} state a dollar amount and {len(fg['fee_no_amount'])} mention a fee without an amount. "
         f"Free or included, for example: {_names(fg['included'], 5)}."),
        ("Do leaves have to go in paper bags?",
         f"Where a city names a bag type: {len(bg['paper_no_plastic'])} name paper bags and say plastic is not accepted, {len(bg['paper'])} name paper, compostable or biodegradable bags, "
         f"{len(bg['no_plastic'])} say plastic bags are not accepted without naming an alternative and {len(bg['plastic'])} name plastic bags. "
         f"{len(bg['bags_unspecified'])} allow bags without specifying the material and {len(bg['other'])} give another container or bundle rule. Check your city's row in the table."),
        ("When does fall leaf collection start?",
         f"It differs by city: {len(pg['program'])} publish a fall or seasonal leaf program with its own timing, {len(pg['season_window'])} give a yard-waste season with start and end dates, "
         f"{len(pg['regular'])} describe regular weekly or alternating-week yard-waste service and {len(pg['appointment'])} collects by appointment. The table quotes each city's own wording."),
    ]
    return {
        "faq": faq, "faq_ld": _ld(faq),
        "n_cities": len(records), "bulk_rows": bulk_rows, "leaf_rows": leaf_rows,
        "n_fee_line": sum(1 for x in rows if x["fee_cls"]), "n_limits": sum(1 for x in rows if x["limits"]),
        "n_period": sum(1 for x in rows if x["period"]), "n_bags": sum(1 for x in rows if x["bags"]),
        "fee_groups": group("fee_cls", FEE_LABEL), "bag_groups": group("bag_cls", BAG_LABEL), "period_groups": group("period_cls", PERIOD_LABEL),
        "captured": cap[0] if len(cap) == 1 else (f"{cap[0]} to {cap[-1]}" if cap else None), "special": special,
    }


# ---------------------------------------------------------------- A/B-week recycling and trash-frequency guide

HOL_SHORT = {"next_day": "One-day slide", "skip": "Pickup skipped", "overrides": "Published make-up days", "no_change": "Runs as usual", "unknown": "Not verified"}


def recycling_guide(cities):
    eow = []
    for c in sorted(cities, key=lambda c: c["city"]):
        note = c.get("notes") or ""
        if not EOW_RE.search(note):
            continue
        ab = sum(1 for z in c["zones"] if z["schedule"].get("recycling_week"))
        eow.append({"c": c, "note": note, "ab_zones": ab, "hol": HOL_SHORT[c["holidays"]["policy"]]})
    weekly_now = [c for c in cities if "every-other-week" in (c.get("notes") or "") and "no longer applies" in (c.get("notes") or "")]
    ab_cities = [x for x in eow if x["ab_zones"]]

    zoned = [c for c in cities if c["zones"]]
    freq = []
    for c in sorted(zoned, key=lambda c: c["city"]):
        n = len(c["zones"])
        two = sum(1 for z in c["zones"] if len(z["schedule"]["trash"]) >= 2)
        if two:
            freq.append({"c": c, "n": n, "two": two, "pct": round(100 * two / n), "max_days": max(len(z["schedule"]["trash"]) for z in c["zones"])})
    once_only = [c for c in zoned if not any(len(z["schedule"]["trash"]) >= 2 for z in c["zones"])]
    mostly_twice = [x for x in freq if x["pct"] >= 50]
    some_twice = [x for x in freq if x["pct"] < 50]
    lookup_twice = [c for c in cities if not c["zones"] and TWICE_NOTE_RE.search(c.get("notes") or "")]
    drop2 = [c for c in cities if c["holidays"].get("drop2")]
    faq = [
        ("Why is my recycling picked up every other week?",
         f"Many cities run recycling on alternating weeks: {len(eow)} of the {len(cities)} cities on TrashWeek describe recycling as every other week. "
         "Your city's collection calendar tells you which week is yours, and a neighbor one street over can be on the other week."),
        ("Is trash ever collected twice a week?",
         f"Yes. In TrashWeek's route data, {len(mostly_twice)} cities have trash on two or more days in at least half of their collection zones"
         + (f" ({_names([x['c'] for x in mostly_twice], 6)})" if mostly_twice else "") + f", and {len(some_twice)} more have it in some zones only."),
    ]
    if drop2:
        faq.append(("What happens to a twice-weekly trash route in a holiday week?",
                    f"{_names(drop2)}: TrashWeek's record of the city's holiday rule drops the second weekly trash pickup in a week that contains a city holiday, and the first pickup slides one day."))
    return {
        "faq": faq, "faq_ld": _ld(faq),
        "eow": eow, "ab_cities": ab_cities, "weekly_now": weekly_now, "n_cities": len(cities),
        "freq": freq, "n_zoned": len(zoned), "once_only": once_only, "mostly_twice": mostly_twice, "some_twice": some_twice,
        "lookup_twice": lookup_twice, "drop2": drop2,
        "most_zones": sorted(zoned, key=lambda c: -len(c["zones"]))[:3],
    }


def hub(cities, holiday, bulk, recycling):
    """Cards for /guide/: every number comes from the three contexts above."""
    return [
        {"path": "guide/holiday-pickup-rules/", "title": "How holiday trash pickup delays work",
         "text": f"The four rules cities use, and what each of the {holiday['n_verified']} cities with a verified notice does on Thanksgiving, Christmas and New Year's Day.",
         "stat": f"{holiday['n_verified']} verified cities"},
        {"path": "guide/bulk-trash-leaf-collection/", "title": "Bulk trash and fall leaf collection rules by city",
         "text": f"What {bulk['n_cities']} city notices say about bulky-item fees and limits, leaf-season dates and which bags are accepted.",
         "stat": f"{len(bulk['bulk_rows'])} bulk rules · {len(bulk['leaf_rows'])} leaf rules"},
        {"path": "guide/every-other-week-recycling/", "title": "Every-other-week recycling and twice-weekly trash",
         "text": f"Why your week A/B and pickup days differ from the next street, which cities recycle every other week, and where trash comes twice a week.",
         "stat": f"{len(recycling['eow'])} every-other-week cities"},
    ]


def hub_faq(cities, holiday, bulk, recycling):
    """The /guide/ hub's FAQ: three answers that point at the guides, with every number taken from the same contexts as the cards."""
    faq = [
        ("What are the TrashWeek guides based on?",
         f"They use the same route data and city notices as the {len(cities)} TrashWeek city pages. Holiday rules come from each hauler's own holiday notice, "
         f"bulk and leaf rules are quotes from the city page named in each row, and zone counts come from the city's published collection-route data."),
        ("Will a guide tell me whether my city moves pickup on a holiday?",
         f"The holiday guide compares what each of the {holiday['n_verified']} cities with a verified notice does on Thanksgiving, Christmas and New Year's Day. "
         f"For a city without a verified notice, its page says the holiday rule is not confirmed instead of guessing a date."),
        ("Where can I find bulky-item and leaf rules, or recycling weeks?",
         f"The bulk and leaf guide quotes {len(bulk['bulk_rows'])} bulky-item rules and {len(bulk['leaf_rows'])} leaf or yard-waste rules, and the recycling guide lists "
         f"{len(recycling['eow'])} cities that recycle every other week. Each city name links to its own page."),
    ]
    return {"faq": faq, "faq_ld": _ld(faq)}
