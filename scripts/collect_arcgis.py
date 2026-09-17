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
    req = url + "?" + urllib.parse.urlencode(params)
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
