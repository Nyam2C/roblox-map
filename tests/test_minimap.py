"""U6 minimap data (src/minimap.py): rectangle geometry, bounds, the Luau text and the installer text."""
from __future__ import annotations

import math

import pytest
from hypothesis import given, strategies as st

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
    for name, _, _ in M.LABELS:
        assert f'"{name}"' in text
    assert text.count("\t{") >= len(M.AREAS) + len(M.LABELS)


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
