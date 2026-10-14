"""Ground heights on the plan (src/terrain.py)."""
import math

import pytest

import layout
import terrain as T


def ramp_ground():
    # 0 at x = 0, rising 1 stud per 10 studs east; flat north-south
    xs = [i * 8.0 for i in range(-20, 21)]
    zs = [j * 8.0 for j in range(-20, 21)]
    hs = tuple(x / 10.0 for z in zs for x in xs)
    return T.Ground(xs[0], zs[0], 8.0, len(xs), len(zs), hs)


def item(kind, name, x, z, sx, sy, sz, yaw=0.0, owner=None, y=None):
    return layout._item(kind, name, owner or name.split("#")[0], 0, (x, sy / 2 if y is None else y, z), (sx, sy, sz), yaw, owner=owner)


def test_bilinear_heights_and_a_window_for_studio():
    g = ramp_ground()
    assert g.h(40, 3) == pytest.approx(4.0) and g.h(44, -5) == pytest.approx(4.4) and g.h(10_000, 0) == pytest.approx(16.0)
    w = g.window(-16, 16, -8, 8)
    assert w["nx"] * w["nz"] == len(w["h"]) and w["h"][0] == pytest.approx(-1.6)


def test_a_building_rises_by_its_lowest_corner_and_takes_its_parts_along():
    g = ramp_ground()
    b = item("building", "gis:1", 40, 0, 20, 30, 10)
    f = item("facade", "gis:1#w0", 50, 0, 2, 2, 0.2, owner="gis:1", y=5)
    out = {i.name: i for i in T.lift([b, f], g)}
    assert out["gis:1"].cy == pytest.approx(15 + 3.0) and out["gis:1#w0"].cy == pytest.approx(5 + 3.0)  # lowest corner x=30


def test_a_road_piece_tilts_with_the_ground_and_a_tree_just_rises():
    g = ramp_ground()
    road = item("road", "way:1#0", 40, 0, 40, 0.2, 10)  # long along X (east), yaw 0
    road90 = item("road", "way:2#0", 40, 0, 40, 0.2, 10, yaw=90)  # long along north-south: flat that way
    tree = item("prop", "sat#1#tree", 40, 0, 5, 6, 1)
    out = {i.name: i for i in T.lift([road, road90, tree], g)}
    assert out["way:1#0"].tilt_z == pytest.approx(math.degrees(math.atan(0.1)), abs=1e-3) and out["way:1#0"].tilt_x == pytest.approx(0, abs=1e-3)
    assert out["way:2#0"].tilt_z == pytest.approx(0, abs=1e-3) and abs(out["way:2#0"].tilt_x) == pytest.approx(math.degrees(math.atan(0.1)), abs=1e-3)
    t = out["sat#1#tree"]  # a standing prop reaches POST_SINK into the ground, its top where it was
    assert t.cy - t.sy / 2 == pytest.approx(4.0 - T.POST_SINK) and t.cy + t.sy / 2 == pytest.approx(6 + 4.0) and t.tilt_x == 0


def test_the_slab_goes_down_and_no_heights_means_no_change():
    g = ramp_ground()
    slab = item("ground", "Ground", 0, 0, 100, 4, 100, y=-2)
    assert T.lift([slab], g)[0].cy == pytest.approx(-2 - T.SLAB_DROP)
    assert T.lift([slab], None)[0] == slab
