#!/usr/bin/env python3
"""Re-probe machine-readable rows of data/wip/city_survey_400.json: ArcGIS bbox + day-value distribution, ReCollect events in a live 21-day window.
Usage: audit_survey.py <start> <end>  (row slice)"""
import datetime as dt
import json
import sys
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

UA = {"User-Agent": "Mozilla/5.0 (TrashWeek collector)", "Accept": "application/json"}


def get(u, params=None):
    if params:
        u = u + "?" + urllib.parse.urlencode(params)
    return json.load(urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=60))


rows = json.loads((Path(__file__).resolve().parent.parent / "data/wip/city_survey_400.json").read_text())
a, b = int(sys.argv[1]), int(sys.argv[2])
today = dt.date.today()
after, before = today.isoformat(), (today + dt.timedelta(days=21)).isoformat()
for x in rows[a:b]:
    if x["kind"] == "arcgis":
        u = x["arcgis_url"]
        try:
            meta = get(u, {"f": "json"})
            q = get(u + "/query", {"where": "1=1", "outFields": "*", "returnGeometry": "true", "outSR": "4326", "f": "json", "resultRecordCount": "2000"})
            feats = q.get("features", [])
            df = x["day_field"]
            c = Counter(str(f["attributes"].get(df)) for f in feats)
            xs = [p[0] for f in feats for r in (f.get("geometry") or {}).get("rings", []) for p in r]
            ys = [p[1] for f in feats for r in (f.get("geometry") or {}).get("rings", []) for p in r]
            bbox = f"{min(xs):.2f},{min(ys):.2f}–{max(xs):.2f},{max(ys):.2f}" if xs else "NO RINGS"
            print(f"ARC {x['city']:18} {x['state']} {meta.get('geometryType', '?')[12:]:8} n={len(feats):5} bbox {bbox} {df}: {dict(c.most_common(7))}")
            print(f"    fields {[f['name'] for f in meta.get('fields', [])][:16]}")
        except Exception as e:
            print("ARC", x["city"], "ERR", str(e)[:90])
    elif x["kind"] == "recollect":
        area, svc = x["recollect_area"], x["recollect_service"]
        try:
            sug = get(f"https://api.recollect.net/api/areas/{area}/services/waste/address-suggest?q=100&locale=en-US")
            p = sug[0]
            ev = get(f"https://api.recollect.net/api/places/{p['place_id']}/services/{svc}/events?nomerge=1&hide=reminder_only&after={after}&before={before}&locale=en-US")
            evs = ev.get("events", [])
            print(f"RC  {x['city']:18} {x['state']} {area}/{svc} '{p['name'][:32]}' events {len(evs)} first {min((e['day'] for e in evs), default=None)} flags {sorted({f['name'] for e in evs for f in e.get('flags', [])})[:6]}")
        except Exception as e:
            print("RC ", x["city"], area, svc, "ERR", str(e)[:90])
