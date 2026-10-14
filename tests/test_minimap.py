"""U6 minimap data (src/minimap.py): rectangle geometry, bounds, the Luau text and the installer text."""
from __future__ import annotations

import math

import pytest
from hypothesis import given, strategies as st

import common
import layout
import minimap as M

finite = st.floats(-2000, 2000, allow_nan=False, allow_infinity=False)
size = st.floats(0.5, 400, allow_nan=False, allow_infinity=False)
yaw = st.floats(-720, 720, allow_nan=False, allow_infinity=False)


def item(kind, x, z, w, d, rot, name="a"):
    return layout._item(kind, name, "g", 0, (x, 1.0, z), (w, 2.0, d), rot % 360.0)


def area(r):  # shoelace
    pts = M.corners(r)
    return abs(sum(x1 * z2 - x2 * z1 for (x1, z1), (x2, z2) in zip(pts, pts[1:] + pts[:1]))) / 2


def test_an_unturned_rectangle_spans_width_in_x_and_depth_in_z_and_a_quarter_turn_swaps_them():
    xs = [p[0] for p in M.corners(M.rect_of(M.ROAD, 10, 20, 8, 2, 0))]
    zs = [p[1] for p in M.corners(M.rect_of(M.ROAD, 10, 20, 8, 2, 0))]
    assert (min(xs), max(xs), min(zs), max(zs)) == pytest.approx((6, 14, 19, 21))
    q = M.corners(M.rect_of(M.ROAD, 10, 20, 8, 2, 90))
    assert (min(p[0] for p in q), max(p[0] for p in q), min(p[1] for p in q), max(p[1] for p in q)) == pytest.approx((9, 11, 16, 24))


def test_a_yaw_of_45_degrees_turns_the_local_x_axis_toward_east_and_north_so_up_the_screen_is_negative_z():
    r = M.rect_of(M.BUILDING, 0, 0, 10, 2, 45)
    # the local +X end of the long side points to (cos 45, -sin 45) in (x, z): east and north (north is -z)
    far = max(M.corners(r), key=lambda p: p[0] - p[1])
    assert far[0] > 0 > far[1]


@given(finite, finite, size, size, yaw)
def test_corners_keep_the_area_and_stay_inside_the_bounds(x, z, w, d, rot):
    r = M.rect_of(M.BUILDING, x, z, w, d, rot)
    assert area(r) == pytest.approx(r[3] * r[4], rel=1e-6, abs=1e-6)
    x0, z0, x1, z1 = M.bounds_of([r])
    assert all(x0 < px < x1 and z0 < pz < z1 for px, pz in M.corners(r))


def test_only_roads_paths_and_buildings_become_rectangles_in_a_fixed_order():
    items = [item("building", 5, 5, 4, 4, 0, "b"), item("sidewalk", 0, 0, 9, 1, 0, "s"), item("road", 1, 1, 20, 6, 30, "r"),
             item("prop", 2, 2, 1, 1, 0, "p"), item("path", 3, 3, 10, 2, 10, "q")]
    got = M.rects_of_items(items)
    assert [r[0] for r in got] == [M.ROAD, M.PATH, M.BUILDING]
    assert got == M.rects_of_items(list(reversed(items)))


def test_an_empty_map_still_has_a_bounds_box_and_the_module_text_is_stable():
    assert M.bounds_of([]) == [0.0, 0.0, 1.0, 1.0]
    text = M.module_text([])
    assert text == M.module_text([]) and text.startswith("-- generated") and "return {" in text and "bounds = {" in text
    for name, *_ in M.HAND_LABELS:
        assert f'"{name}"' in text
    assert text.count("\n{") >= len(M.AREAS) and text.count("\t{") >= len(M.HAND_LABELS)  # rects are compact rows (2026-10-15)


@pytest.mark.parametrize("name, ok", [("청솔하이빌", True), ("광성아파트", True), ("1003동", True), ("중3동행정복지센터", True),
                                      ("춘의동 131-16 단독주택 (홍길동)", False), ("정순가", False), ("세븐일레븐", False),
                                      ("부흥건물(본관)", False), ("", False), (None, False)])
def test_only_building_and_facility_names_reach_the_map(name, ok):
    assert (M.map_name(name) is not None) == ok


FRAME = layout.Frame.from_cfg(common.DEFAULTS)


def bld(bid, name, east, north, area=100.0, floors=3):
    lat, lon = layout.from_studs(FRAME, east * FRAME.studs_per_m, -north * FRAME.studs_per_m)
    return {"building_id": bid, "name": name, "centroid": [lat, lon], "building_area": area, "floors_above": floors}


def test_one_label_per_complex_levels_by_kind_and_no_two_names_on_one_spot():
    rows = [bld("gis:1", "한신빌라", 0, 0), bld("gis:2", "한신빌라", 20, 0), bld("gis:3", "한신빌라", 300, 0),
            bld("gis:4", "심원고등학교", 0, 200, 2000, 5), bld("gis:5", "심원고등학교", 90, 200, 600, 5),
            bld("gis:6", "중3동 주민센터", 0, 400, 50, 2), bld("gis:7", "중3동행정복지센터", 5, 400, 300, 2),
            bld("gis:8", "광성아파트", 0, 600, 4000, 13), bld("gis:9", "1003동", 0, 800, 300, 13), bld("gis:10", "단독주택 (홍길동)", 0, 900)]
    got = M.building_labels(rows, FRAME)
    names = [l[0] for l in got]
    assert names.count("한신빌라") == 2 and names.count("심원고등학교") == 1
    assert "중3동행정복지센터" in names and "중3동 주민센터" not in names
    lv = {l[0]: (l[3], l[4]) for l in got}
    assert lv["심원고등학교"] == (1, M.FACILITY) and lv["광성아파트"] == (2, M.BUILDING_NAME) and lv["1003동"][0] == 3
    assert not any("홍길동" in n for n in names)
    assert got == M.building_labels(list(reversed(rows)), FRAME)


def test_road_names_by_class_along_the_road_and_never_upside_down():
    def road(name, hw, pts):
        return {"tags": {"name": name, "highway": hw}, "geometry": [list(layout.from_studs(FRAME, x, z)) for x, z in pts]}
    got = M.road_labels([road("길주로", "tertiary", [(0, 0), (500, 0)]), road("옥산로113번길", "service", [(0, 100), (-100, 0)]),
                         road("계남로", "residential", [(0, 300), (0, 600)])], FRAME)
    lv = {l[0]: l for l in got}
    assert lv["길주로"][3] == 1 and lv["옥산로113번길"][3] == 3 and lv["계남로"][3] == 2
    assert all(-90 <= l[5] <= 90 for l in got)
    assert abs(lv["길주로"][5]) < 1 and abs(abs(lv["계남로"][5]) - 90) < 1


@pytest.mark.parametrize("bad", ['a"b', "a\\b", "a]]b", "", "x" * 21, "a\nb", "a--b"])
def test_a_label_with_a_character_that_could_reach_code_is_refused(bad):
    with pytest.raises(ValueError):
        M.luau_label(bad)


def test_the_long_string_level_grows_until_the_text_cannot_close_it_early():
    assert M.long_string("abc") == "[==[\nabc]==]"
    tricky = "x ]==] y"
    assert M.long_string(tricky).startswith("[===[")
    assert M.long_string("ends with ]=").endswith("]===]")  # a text ending in "]=" must not merge with the closing bracket


def test_the_installer_holds_every_script_the_data_and_the_remote(tmp_path):
    for _, _, _, fn in M.SOURCES:
        (tmp_path / fn).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / fn).write_text(f"-- {fn}\nlocal x = 1\n", encoding="utf-8")
    text = M.install_text("return {}\n", tmp_path)
    for name, where, cls, fn in M.SOURCES:
        assert f'ensure(at("{where}"), "{cls}", "{name}")' in text and f"-- {fn}" in text
    assert all((M.STUDIO_DIR / fn).exists() for _, _, _, fn in M.SOURCES)  # the repository holds every source where SOURCES says
    assert '"ModuleScript", "MinimapData"' in text and '"RemoteEvent", "ScooterToggle"' in text and text.rstrip().endswith("return made")


# --- teleport by hexagon (2026-10-14) ---------------------------------------------------------------------------------------

def test_a_hex_has_six_corners_and_lands_on_the_sidewalk_nearest_the_cell_centre():
    import h3
    frame = layout.Frame.from_cfg(common.DEFAULTS)
    cell = "8930e0af13bffff"
    cx, cz = layout.to_studs(frame, *h3.cell_to_latlng(cell))
    items = [item("sidewalk", cx + 50, cz, 10, 3, 0, "far"), item("sidewalk", cx + 5, cz + 2, 10, 3, 0, "near"), item("road", cx, cz, 10, 8, 0, "r")]
    name, lx, lz, *corners = M.hex_of(cell, items, frame, "도당동 1")
    assert name == "도당동 1" and len(corners) == 12 and (lx, lz) == pytest.approx((cx + 5, cz + 2), abs=0.1)
    pts = list(zip(corners[::2], corners[1::2]))
    side = [(b[0] - a[0]) * (lz - a[1]) - (b[1] - a[1]) * (lx - a[0]) for a, b in zip(pts, pts[1:] + pts[:1])]
    assert all(v > 0 for v in side) or all(v < 0 for v in side)  # the landing is inside the cell
    assert M.hex_of(cell, [], frame, "x")[1:3] == (round(cx, 1), round(cz, 1))  # nothing to stand on: the centre


def test_hex_names_count_within_a_dong_and_reach_the_module_text():
    names = M.hex_names(["a", "b", "c", "d"], {"a": "도당동", "b": "중동", "c": "도당동", "d": ""})
    assert names == ["도당동 1", "중동 1", "도당동 2", "칸 1"]
    text = M.module_text([], [], [], [("중동 1", 1.0, 2.0, *range(12))])
    assert 'hexes = {\n\t{"중동 1", 1, 2, 0, 1, 2, 3' in text
    assert "HexTeleport" in M.install_text(text)


def test_the_installer_without_data_leaves_the_data_module_to_its_own_step(tmp_path):
    for _, _, _, fn in M.SOURCES:
        (tmp_path / fn).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / fn).write_text("local x = 1\n", encoding="utf-8")
    text = M.install_text("", tmp_path)
    assert "data.Source" not in text and '"RemoteEvent", "HexTeleport"' in text and '"RemoteEvent", "LandmarkTeleport"' in text
