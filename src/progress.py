# /// script
# requires-python = ">=3.11"
# dependencies = ["h3==4.5.0", "shapely==2.2.0", "pillow==12.3.0"]
# ///
"""The progress map of the whole city: every res-9 H3 cell of 부천시 by state -> data/compare/bucheon-progress.png (git-excluded).

Usage (repo root):
  uv run src/progress.py           # reads only: regions/*/region.toml, data/map.db, data/build/<cell>/manifest.json
                                   # the city and gu boundaries come from OSM once (data/osm/bucheon-boundary.json, cached)

States: built (chunk files made, manifest.json; the cycle puts them in Studio), judged (street view judged, not built yet),
collected (buildings stored), in a region (listed, nothing stored), not started. The inset enlarges the worked area.
"""
from __future__ import annotations

import json
import math
import sqlite3
import sys
import tomllib
from pathlib import Path

import h3
from PIL import Image, ImageDraw, ImageFont
from shapely.geometry import LineString, MultiPolygon, Point
from shapely.ops import linemerge, polygonize, unary_union

ROOT = Path(__file__).resolve().parent.parent
BOUNDARY = ROOT / "data/osm/bucheon-boundary.json"
OUT = ROOT / "data/compare/bucheon-progress.png"
QUERY = ('[out:json][timeout:90];area["name"="부천시"]["boundary"="administrative"]["admin_level"="6"]->.a;'
         '(relation["boundary"="administrative"]["name"="부천시"]["admin_level"="6"];relation(area.a)["boundary"="administrative"]["admin_level"="7"];);out geom;')
STATES = (("built", "완성(Studio)", (214, 64, 52)), ("judged", "판단 끝·생성 전", (240, 150, 50)),
          ("collected", "수집만", (245, 205, 80)), ("listed", "구역에만 등록", (170, 170, 200)))
GU = {"원미구": (214, 228, 246), "소사구": (228, 240, 214), "오정구": (246, 232, 214)}
FONT = "/System/Library/Fonts/AppleSDGothicNeo.ttc"


def boundaries() -> dict[str, object]:
    if not BOUNDARY.exists():
        sys.path.insert(0, str(ROOT / "src"))
        import common
        BOUNDARY.parent.mkdir(parents=True, exist_ok=True)
        BOUNDARY.write_text(json.dumps(common.http_get_json("https://overpass-api.de/api/interpreter", {"data": QUERY}), ensure_ascii=False))
    out = {}
    for rel in json.loads(BOUNDARY.read_text(encoding="utf-8"))["elements"]:
        lines = [LineString([(p["lon"], p["lat"]) for p in m["geometry"]]) for m in rel["members"]
                 if m.get("type") == "way" and m.get("role") in ("outer", "") and m.get("geometry")]
        out[rel["tags"]["name"]] = unary_union(list(polygonize(linemerge(unary_union(lines)))))
    return out


def parts(geom):
    return geom.geoms if isinstance(geom, MultiPolygon) else [geom]


def cell_states() -> tuple[dict[str, str], int]:
    listed = set()
    for toml in sorted((ROOT / "regions").glob("*/region.toml")):
        listed |= set(tomllib.loads(toml.read_text(encoding="utf-8")).get("cells", []))
    con = sqlite3.connect(ROOT / "data/map.db")
    collected = {r[0] for r in con.execute("select distinct cell_id from buildings")}
    judged = {r[0] for r in con.execute("select distinct b.cell_id from buildings b join estimates e using(building_id)")}
    state, total = {}, 0
    for c in listed | collected:
        m = ROOT / "data/build" / c / "manifest.json"
        if m.exists():
            state[c] = "built"
            total += json.loads(m.read_text(encoding="utf-8"))["counts"]["items"]
        else:
            state[c] = "judged" if c in judged else "collected" if c in collected else "listed"
    return state, total


def main() -> int:
    b = boundaries()
    city, gus = b["부천시"], {k: v for k, v in b.items() if k != "부천시"}
    cells: set[str] = set()
    for p in parts(city):
        cells |= set(h3.polygon_to_cells(h3.LatLngPoly([(y, x) for x, y in p.exterior.coords]), 9))
    state, total_parts = cell_states()
    gu_of = {c: k for c in cells for k, v in gus.items() if v.contains(Point(*h3.cell_to_latlng(c)[::-1]))}
    f_big, f, f_s = (ImageFont.truetype(FONT, s) for s in (46, 30, 22))

    minx, miny, maxx, maxy = city.bounds
    W, INSET = 1800, 760
    kx = math.cos(math.radians((miny + maxy) / 2))
    sc = (W - INSET - 120) / ((maxx - minx) * kx)
    H = max(int((maxy - miny) * sc) + 230, INSET + 520)
    img = Image.new("RGB", (W, H), (246, 244, 238))
    dr = ImageDraw.Draw(img)

    def draw_map(dr, P, line_w, show_ids=False):
        for c in sorted(cells | set(state)):
            pts = [P(lon, lat) for lat, lon in h3.cell_to_boundary(c)]
            fill = next((col for k, _, col in STATES if state.get(c) == k), GU.get(gu_of.get(c), (232, 232, 232)))
            dr.polygon(pts, fill=fill, outline=(185, 185, 185))
            if show_ids and c in state:
                x, y = P(*h3.cell_to_latlng(c)[::-1])
                dr.text((x, y), c[7:11], font=f_s, fill=(255, 255, 255) if state[c] == "built" else (60, 60, 60), anchor="mm")
        for g in gus.values():
            for p in parts(g):
                dr.line([P(x, y) for x, y in p.exterior.coords], fill=(90, 90, 110), width=line_w)
        for p in parts(city):
            dr.line([P(x, y) for x, y in p.exterior.coords], fill=(30, 30, 40), width=line_w + 2)

    P = lambda lon, lat: (40 + (lon - minx) * kx * sc, 150 + (maxy - lat) * sc)
    draw_map(dr, P, 3)
    for k, v in gus.items():
        c = v.representative_point()
        n, d = sum(1 for x in cells if gu_of.get(x) == k), sum(1 for x in cells if gu_of.get(x) == k and state.get(x) == "built")
        dr.text(P(c.x, c.y), f"{k}\n{d} / {n}칸", font=f, fill=(40, 40, 60), anchor="mm", align="center")

    # inset: the worked area
    work = [h3.cell_to_latlng(c) for c in state]
    la0, la1 = min(p[0] for p in work), max(p[0] for p in work)
    lo0, lo1 = min(p[1] for p in work), max(p[1] for p in work)
    pad = 0.006
    isc = (INSET - 40) / max((lo1 - lo0 + 2 * pad) * kx, (la1 - la0 + 2 * pad))
    ox, oy = W - INSET - 20, 150
    Q = lambda lon, lat: (20 + (lon - lo0 + pad) * kx * isc, 20 + (la1 + pad - lat) * isc)
    inset = Image.new("RGB", (INSET, INSET), (250, 249, 245))  # drawn apart and pasted, so nothing spills over the city map
    draw_map(ImageDraw.Draw(inset), Q, 2, show_ids=True)
    img.paste(inset, (ox, oy))
    dr.rectangle((ox, oy, ox + INSET, oy + INSET), outline=(120, 120, 130), width=2)
    # the inset's frame on the big map
    a, bb = P(lo0 - pad, la1 + pad), P(lo1 + pad, la0 - pad)
    dr.rectangle((a[0], a[1], bb[0], bb[1]), outline=(30, 30, 40), width=2)

    n_state = {k: sum(1 for c in cells if state.get(c) == k) for k, _, _ in STATES}
    built = n_state["built"]
    dr.text((40, 30), f"부천 진행 현황  {built} / {len(cells)}칸 완성 ({100 * built / len(cells):.1f}%)", font=f_big, fill=(30, 30, 40))
    dr.text((40, 92), f"H3 해상도 9, 한 칸 약 0.072 km²  ·  Studio 부품 약 {total_parts:,}개  ·  칸당 평균 {total_parts // max(built, 1):,}", font=f_s, fill=(70, 70, 80))
    y = oy + INSET + 30
    for k, label, col in STATES:
        dr.rectangle((ox, y, ox + 34, y + 26), fill=col)
        dr.text((ox + 46, y + 13), f"{label} {n_state[k]}칸", font=f, fill=(40, 40, 50), anchor="lm")
        y += 44
    dr.rectangle((ox, y, ox + 34, y + 26), fill=(214, 228, 246))
    dr.text((ox + 46, y + 13), f"미착수 {len(cells) - sum(n_state.values())}칸 (색은 구)", font=f, fill=(40, 40, 50), anchor="lm")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT)
    print(f"{built}/{len(cells)} built, {n_state} -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
