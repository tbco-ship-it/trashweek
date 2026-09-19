#!/usr/bin/env python3
"""Pull collection-day polygons from each city's public ArcGIS layer into data/raw/<city>.json (WGS84, simplified)."""
import datetime as dt
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REG = json.loads((ROOT / "data/registry.json").read_text())


def fetch(url, params, timeout=90):
    req = urllib.request.Request(url + "?" + urllib.parse.urlencode(params), headers={"User-Agent": "Mozilla/5.0 (TrashWeek collector; contact via github.com/tbco-ship-it/trashweek)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def collect(slug, cfg):
    url = cfg["url"]
    meta = fetch(url, {"f": "json"})
    page = int(meta.get("maxRecordCount") or 1000)
    feats, offset = [], 0
    while True:
        q = fetch(url + "/query", {"where": cfg.get("where", "1=1"), "outFields": "*", "outSR": "4326", "returnGeometry": "true",
                                   "maxAllowableOffset": "0.0003", "geometryPrecision": "5",
                                   "resultOffset": str(offset), "resultRecordCount": str(page), "f": "json"})
        got = q.get("features", [])
        feats += got
        if not q.get("exceededTransferLimit") or not got:
            break
        offset += len(got)
    # wrong-city layers happen (a 'Glendale' layer in Wisconsin, an 'Ontario' layer in Canada): refuse when the city centre is outside the bbox
    xs = [x for f in feats for r in (f.get("geometry") or {}).get("rings", []) for x, _ in r]
    ys = [y for f in feats for r in (f.get("geometry") or {}).get("rings", []) for _, y in r]
    if xs and cfg.get("center"):
        cx, cy = cfg["center"]
        if not (min(xs) - 0.05 <= cx <= max(xs) + 0.05 and min(ys) - 0.05 <= cy <= max(ys) + 0.05):
            raise RuntimeError(f"bbox {min(xs):.2f},{min(ys):.2f}–{max(xs):.2f},{max(ys):.2f} does not contain city centre {cx},{cy}")
    out = {"slug": slug, "fetched": dt.date.today().isoformat(), "url": url, "geometryType": meta.get("geometryType"),
           "fields": [f["name"] for f in meta.get("fields", [])], "features": feats}
    (ROOT / "data/raw" / f"{slug}.json").write_text(json.dumps(out, separators=(",", ":")))
    return len(feats)


if __name__ == "__main__":
    only = sys.argv[1:]
    for slug, cfg in REG.items():
        if only and slug not in only or cfg["kind"] != "arcgis":
            continue
        try:
            n = collect(slug, cfg)
            print(f"{slug}: {n} features")
        except Exception as e:
            print(f"{slug}: FAILED {e}", file=sys.stderr)
