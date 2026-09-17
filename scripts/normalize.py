#!/usr/bin/env python3
"""data/raw/<city>.json → data/normalized/<city>.json: one record per collection zone with weekday lists and a WGS84 polygon."""
import datetime as dt
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REG = json.loads((ROOT / "data/registry.json").read_text())
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
DAY_RE = re.compile(r"\b(mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun)[a-z]*\b", re.I)


def parse_days(val):
    """'Monday/Thursday', 'MON', 'Tuesday Friday', 'M/TH' → ['Mon','Thu']. Unknown → []."""
    if val is None:
        return []
    s = re.sub(r"[^A-Za-z]+", " ", str(val)).strip()  # FRI_VRN_SON, Tuesday/Friday, MON-A → tokens
    found = [m.group(1)[:3].title() for m in DAY_RE.finditer(s)]
    if not found and re.fullmatch(r"[MTWFS]{1,2}(/[MTWFS]{1,2})*", s.upper()):
        code = {"M": "Mon", "T": "Tue", "W": "Wed", "TH": "Thu", "F": "Fri", "S": "Sat"}
        found = [code.get(p.upper(), "") for p in s.split("/")]
    out = []
    for d in found:
        d = {"Tues": "Tue", "Thur": "Thu"}.get(d, d)
        if d in DAYS and d not in out:
            out.append(d)
    return out


def main():
    today = dt.date.today().isoformat()
    for slug, cfg in REG.items():
        raw_p = ROOT / "data/raw" / f"{slug}.json"
        if not raw_p.exists():
            continue
        raw = json.loads(raw_p.read_text())
        zones = []
        skipped = 0
        for f in raw["features"]:
            a = f["attributes"]
            rings = (f.get("geometry") or {}).get("rings")
            if not rings:
                skipped += 1
                continue
            sched = {}
            for kind, field in cfg["fields"].items():
                v = a.get(field)
                if kind.endswith("_url") or kind.endswith("_week"):
                    sched[kind] = v
                else:
                    sched[kind] = parse_days(v)
            if not sched.get("trash"):
                skipped += 1
                continue
            oid = next((a[k] for k in a if k.upper().startswith("OBJECTID") or k.upper() in ("FID", "ID")), None)
            zid = str(a.get(cfg["zone"]) or "").strip()
            if not zid or zid == "None":
                zid = str(oid) if oid is not None else "/".join(sched["trash"])
            zones.append({"zone": zid, "schedule": sched, "raw": {k: a.get(k) for k in cfg["fields"].values() if k in a},
                          "rings": rings})
        # merge zones that share id + schedule (many layers split one route into several polygons)
        merged = {}
        for z in zones:
            key = (z["zone"], json.dumps(z["schedule"], sort_keys=True))
            if key in merged:
                merged[key]["rings"] += z["rings"]
            else:
                merged[key] = z
        recs = list(merged.values())
        # disambiguate duplicate zone ids with different schedules
        seen = Counter(r["zone"] for r in recs)
        for r in recs:
            if seen[r["zone"]] > 1:
                r["zone"] = f"{r['zone']} ({'/'.join(r['schedule']['trash'])})"
        out = {"slug": slug, "city": cfg["city"], "state": cfg["state"], "provider": cfg["provider"], "notes": cfg.get("notes", ""),
               "holiday_url": cfg.get("holiday_url"), "source_url": cfg.get("source_url"), "data_url": cfg["url"], "fetched": raw["fetched"],
               "normalized": today, "zones": recs}
        (ROOT / "data/normalized" / f"{slug}.json").write_text(json.dumps(out, separators=(",", ":")))
        days = Counter(d for r in recs for d in r["schedule"]["trash"])
        print(f"{slug}: {len(recs)} zones (from {len(raw['features'])} features, skipped {skipped}) trash days {dict(days)}")


if __name__ == "__main__":
    main()
