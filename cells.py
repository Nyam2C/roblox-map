# /// script
# dependencies = ["h3"]
# ///
"""Usage: uv run cells.py RES lat,lon lat,lon lat,lon [lat,lon ...]
Fills the polygon with H3 cells, saves each cell's OSM buildings to cells/<cell>.json."""
import json, sys, time, urllib.parse, urllib.request
from pathlib import Path
import h3

OVERPASS = "https://overpass-api.de/api/interpreter"


def buildings(cell):
    ring = " ".join(f"{la} {lo}" for la, lo in h3.cell_to_boundary(cell))
    q = f'[out:json][timeout:60];way["building"](poly:"{ring}");out geom tags;'
    req = urllib.request.Request(
        OVERPASS, urllib.parse.urlencode({"data": q}).encode(), {"User-Agent": "roblox-map/0"}
    )
    for wait in (10, 30, 60, None):  # public Overpass often answers 504/429 under load
        try:
            data = json.load(urllib.request.urlopen(req, timeout=90))
            break
        except urllib.error.HTTPError as e:
            if wait is None or e.code not in (429, 502, 504):
                raise
            time.sleep(wait)
    out = []
    for w in data["elements"]:
        pts = [[p["lat"], p["lon"]] for p in w["geometry"]]
        la = sum(p[0] for p in pts) / len(pts)
        lo = sum(p[1] for p in pts) / len(pts)
        # a building straddling two cells belongs to the one holding its centroid
        if h3.latlng_to_cell(la, lo, h3.get_resolution(cell)) == cell:
            out.append({"id": w["id"], "tags": w.get("tags", {}), "pts": pts})
    return out


if __name__ == "__main__":
    res = int(sys.argv[1])
    poly = [tuple(map(float, a.split(","))) for a in sys.argv[2:]]
    cells = sorted(h3.polygon_to_cells(h3.LatLngPoly(poly), res))
    assert cells, "polygon too small for this resolution, try a higher RES"
    Path("cells").mkdir(exist_ok=True)
    for c in cells:
        b = buildings(c)
        Path(f"cells/{c}.json").write_text(json.dumps(
            {"cell": c, "center": h3.cell_to_latlng(c), "boundary": h3.cell_to_boundary(c), "buildings": b},
            ensure_ascii=False))
        print(c, len(b), "buildings")
        time.sleep(1)  # be polite to the public Overpass server
