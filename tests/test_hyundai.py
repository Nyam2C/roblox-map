from __future__ import annotations

from shapely.geometry import Point

import hyundai as HY
import layout_details as LD
from test_facilities import FRAME, body


def test_a_store_block_has_its_mass_arched_windows_corner_glass_and_a_cornice():
    b = body()
    items = HY.Store(FRAME, b, {"entrance": "S"}, []).make()
    tails = [i.name.split("#", 1)[1].split("-")[0] for i in items]
    assert tails.count("m") == len(b.boxes)
    assert {"bs", "bc", "cg", "ag", "ae", "cr", "fz"} <= set(tails)
    assert all(i.owner == b.building_id for i in items)


def test_a_face_toward_the_other_block_is_left_bare_and_the_atrium_is_a_glass_drum():
    b = body()
    faces = HY.Store(FRAME, b, {}, []).open_faces()
    bi, side, _ = faces[0]
    f = LD.face_of(b.boxes[bi], side)
    e, n = LD._world(b.boxes[bi], f.c[0] + f.n[0] * 2.5, f.c[1] + f.n[1] * 2.5)
    other = Point(e, n).buffer(3.0)
    assert (bi, side) not in [(x, s) for x, s, _ in HY.Store(FRAME, b, {}, [other]).open_faces()]
    drum = HY.atrium(FRAME, "gis:9", Point(0, 0).buffer(10.0))
    assert any(i.shape == "Cylinder" and "#dr-" in i.name for i in drum) and any("#dm-" in i.name for i in drum) and any("#gw-" in i.name for i in drum)


def test_the_park_layout_builds_flat_layers_a_statue_and_hedge_curbs():
    import anjunggeun
    items = anjunggeun.build(FRAME, "anjunggeun_park")
    tails = {i.name.split("#", 1)[1].split("-")[0] for i in items}
    assert {"la", "pa", "pl", "sp", "sh", "cb"} <= tails and len(items) < 2000
    assert all(i.sy > 0 and i.sx > 0 and i.sz > 0 for i in items)


def test_the_market_arcade_has_roofs_ribs_stalls_and_named_gates():
    import market
    items = market.build(FRAME, "gangnam_market")
    tails = {i.name.split("#", 1)[1].split("-")[0] for i in items}
    assert {"rw", "rc", "rb", "gt", "fb", "gp", "gb"} <= tails and len(items) < 600
    assert any(i.kind == "sign" and i.text == "강남시장" for i in items)


def test_the_driving_range_has_net_walls_poles_a_top_net_and_turf():
    import golf
    items = golf.build(FRAME, "hyundai_golf")
    tails = {i.name.split("#", 1)[1].split("-")[0] for i in items}
    assert {"nt", "pl", "pa", "nr", "tf"} <= tails and len(items) < 600
    assert max(i.cy + i.sy / 2 for i in items) > 25 * FRAME.studs_per_m  # the net stands about 30 m


def test_the_terminal_has_a_rotunda_checker_panels_a_named_hall_bays_and_a_footbridge():
    import json
    import layout
    import sopoong
    from anjunggeun import to_latlon
    from shapely.geometry import MultiPoint
    data = json.loads(sopoong.LAYOUT.read_text(encoding="utf-8"))
    ox, oy = data["offset"]
    px = [data["rotunda"]["px"], *data["hall"]["px"], *data["skylight"]["px"], *data["arc"]["px"], [338, 300]]
    poly = MultiPoint([layout.to_meters(FRAME, *to_latlon(data["tile_x0"], data["tile_y0"], ox + x, oy + y)) for x, y in px]).convex_hull
    items = sopoong.build(FRAME, "gis:1", poly.buffer(6.0))
    tails = [i.name.split("#", 1)[1].split("-")[0] for i in items]
    assert {"rd", "rc", "rk", "ck", "ag", "hl", "sk", "aw", "bw", "dk", "py"} <= set(tails)
    assert [i.shape for i in items if "#rd-" in i.name] == ["Cylinder"]
    assert [i.text for i in items if i.kind == "sign"] == ["부천터미널"]
    assert tails.count("dk") == len(data["bridge"]["px"]) - 1 and tails.count("py") == len(data["bridge"]["pylons"])
    assert {i.group for i in items} == {"gis:1", "sopoong-bays", "sopoong-bridge"}


def test_the_factory_has_a_ring_a_core_corner_towers_cooling_towers_and_a_portico():
    import factory
    from shapely.geometry import box as rect
    items = factory.build(FRAME, "gis:2", rect(0.0, 0.0, 140.0, 120.0))
    tails = [i.name.split("#", 1)[1].split("-")[0] for i in items]
    assert {"m", "c", "t", "tf", "cf", "ct", "tk", "pc", "pk", "rs", "rg"} <= set(tails)
    assert tails.count("t") == 4 and tails.count("pc") == 2
    assert all(i.group == "gis:2" for i in items)


def test_savezone_finds_its_round_corner_and_its_walls_do_not_overhang_the_outline():
    """세이브존 (2026-10-16): the rotunda sits on the fitted rounded corner, and the clipped fill keeps the mass inside the outline
    (plaza.strips' full-depth bands overhung a wall along x and buried its details)."""
    import math
    import savezone
    from shapely.geometry import Point, Polygon
    arc = [(10 * math.cos(math.radians(a)) + 10, 10 * math.sin(math.radians(a)) + 10) for a in range(180, 271, 15)]
    poly = Polygon([(100.0, 0.0), (100.0, 45.0), (0.0, 45.0)] + arc[:-1] + [(10.0, 0.0)])
    cx, cy, r = savezone.corner_circle(poly)
    assert math.hypot(cx - 10, cy - 10) < 0.5 and abs(r - 10) < 0.5
    boxes = savezone.fill(poly, 1.0)
    corners = [Point(x + sx * w / 2, z + sz * d / 2) for x, z, w, d in boxes for sx in (-1, 1) for sz in (-1, 1)]
    assert all(poly.buffer(0.01).contains(p) for p in corners if p.distance(Point(cx, cy)) > r + 2)  # straight walls: no overhang
    items = savezone.build(FRAME, "gis:3", poly)
    tails = {i.name.split("#", 1)[1].split("-")[0] for i in items}
    assert {"m", "jv", "sl", "ds", "dy", "pt", "po", "rg", "rm", "rd", "fp", "bn"} <= tails
    assert all(i.group == "gis:3" for i in items)
