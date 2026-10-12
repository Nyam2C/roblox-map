"""U3 projection: distance, bearing, relative direction, crop settings and the cube-map crop (P3-1, P3-2, P3-4, P3-5)."""
from __future__ import annotations

import math

import numpy as np
import pytest
from hypothesis import assume, given, strategies as st
from PIL import Image

import common
import projection as P
from generators import BASE, compass_degrees, convex_outlines, distances_m, extents_deg, heights_m, offset, position_pairs, positions

CFG = common.DEFAULTS


# --- P3-1 distance and bearing ----------------------------------------------------------

@given(position_pairs())
def test_distance_is_symmetric_and_non_negative(pair):
    a, b = pair
    assert P.distance_m(a, b) == P.distance_m(b, a) >= 0


@given(positions())
def test_distance_to_itself_is_zero(a):
    assert P.distance_m(a, a) == 0


@given(position_pairs())
def test_bearing_is_in_range_and_reverse_bearing_is_opposite(pair):
    a, b = pair
    assert 0 <= P.bearing_deg(a, b) < 360
    assume(P.distance_m(a, b) > 0.5)
    diff = (P.bearing_deg(a, b) - P.bearing_deg(b, a)) % 360
    assert diff == pytest.approx(180, abs=1e-6)


def test_bearing_points_the_way_a_compass_does():
    assert P.bearing_deg(BASE, offset(BASE, 0, 50)) == pytest.approx(0, abs=1e-6)
    assert P.bearing_deg(BASE, offset(BASE, 50, 0)) == pytest.approx(90, abs=0.01)
    assert P.bearing_deg(BASE, offset(BASE, 0, -50)) == pytest.approx(180, abs=1e-6)
    assert P.bearing_deg(BASE, offset(BASE, -50, 0)) == pytest.approx(270, abs=0.01)
    # generators.offset uses 111,320 m per degree like cells.py, the earth radius gives 111,195: 0.11% apart
    assert P.distance_m(BASE, offset(BASE, 30, 40)) == pytest.approx(50, rel=3e-3)


# --- P3-2 relative direction ---------------------------------------------------------------

@given(compass_degrees, compass_degrees)
def test_yaw_is_in_range_and_adds_back_to_the_bearing(bearing, heading):
    yaw = P.yaw_deg(bearing, heading)
    assert -180 <= yaw < 180
    gap = (yaw + heading - bearing) % 360
    assert min(gap, 360 - gap) < 1e-9


# --- P3-4 crop settings ------------------------------------------------------------------------

@given(extents_deg, distances_m, heights_m)
def test_crop_values_stay_in_range_and_cover_small_buildings(extent, distance, height):
    fov, pitch = P.crop_params(extent, distance, height, CFG)
    assert CFG["fov_min_deg"] <= fov <= CFG["fov_max_deg"]
    assert 0 <= pitch <= CFG["pitch_max_deg"]
    if extent <= 80:
        assert fov >= extent
    assert (fov, pitch) == P.crop_params(extent, distance, height, CFG)


@given(st.one_of(st.none(), st.floats(-5, 200)), st.one_of(st.none(), st.integers(-2, 60)))
def test_building_height_follows_the_priority_vworld_then_floors_then_default(height, floors):
    result = P.building_height_m(height, floors, CFG)
    if height and height > 0:
        assert result == height
    elif floors and floors > 0:
        assert result == floors * CFG["floor_height_m"]
    else:
        assert result == CFG["default_height_m"]


@given(convex_outlines(spread_m=200), positions(200))
def test_extent_arc_contains_every_vertex_and_is_symmetric_to_vertex_order(outline, pano):
    extent = P.building_extent_deg(outline, pano)
    assert 0 <= extent < 360
    bearings = [P.bearing_deg(pano, p) for p in outline]
    assert any(all((b - s) % 360 <= extent + 1e-9 for b in bearings) for s in bearings)
    assert extent == P.building_extent_deg(list(reversed(outline)), pano)


def test_extent_of_a_building_ahead_matches_its_width():
    # a 20 m wide facade 20 m due north spans 2*atan(10/20) = 53.13 degrees
    outline = [offset(BASE, -10, 20), offset(BASE, 10, 20), offset(BASE, 10, 40), offset(BASE, -10, 40)]
    assert P.building_extent_deg(outline, BASE) == pytest.approx(53.13, abs=0.2)
    assert P.building_extent_deg([BASE], BASE) == 0.0


# --- P3-5 cube-map crop ----------------------------------------------------------------------------

N = 256
COLORS = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0), (255, 0, 255), (0, 255, 255)]  # f r b l u d


def solid_faces() -> np.ndarray:
    return np.stack([np.full((N, N, 3), c, np.uint8) for c in COLORS])


def gradient_faces() -> np.ndarray:
    """Red grows with the image column, green with the image row, blue marks the face."""
    col = np.broadcast_to(np.linspace(0, 255, N)[None, :], (N, N))
    row = np.broadcast_to(np.linspace(0, 255, N)[:, None], (N, N))
    return np.stack([np.stack([col, row, np.full((N, N), 40 * i)], -1).astype(np.uint8) for i in range(6)])


def crop(faces, yaw, pitch, fov=20, size=(32, 24)):
    return np.asarray(P.render_crop(faces, yaw, pitch, fov, size))


@given(st.sampled_from([(0, 0), (90, 1), (180, 2), (-90, 3)]), st.floats(-25, 25), st.floats(-20, 20))
def test_side_directions_show_the_matching_face(face_yaw, dyaw, pitch):
    yaw, face = face_yaw
    out = crop(solid_faces(), yaw + dyaw, pitch)
    assert (out == np.array(COLORS[face], np.uint8)).all()


@given(st.floats(-180, 180), st.floats(70, 90))
def test_looking_up_and_down_shows_the_cap_faces(yaw, pitch):
    assert (crop(solid_faces(), yaw, pitch) == np.array(COLORS[4], np.uint8)).all()
    assert (crop(solid_faces(), yaw, -pitch) == np.array(COLORS[5], np.uint8)).all()


def _center(img: np.ndarray) -> np.ndarray:
    h, w, _ = img.shape
    return img[h // 2, w // 2].astype(int)


def test_turning_right_moves_toward_the_right_edge_of_the_front_face():
    r = _center(crop(gradient_faces(), 10, 0, fov=20, size=(64, 48)))
    assert r[0] == pytest.approx((math.tan(math.radians(10)) + 1) / 2 * 255, abs=8)
    assert r[1] == pytest.approx(127.5, abs=8)
    assert r[2] == 0


def test_up_face_orientation_matches_the_layout_notes():
    # pitch 60 facing front: image-up of the up face points backward, so the point lies below the face center
    c = _center(crop(gradient_faces(), 0, 60, fov=10, size=(64, 48)))
    assert c[2] == 160 and c[0] == pytest.approx(127.5, abs=8)
    assert c[1] == pytest.approx((1 + math.tan(math.radians(30))) / 2 * 255, abs=8)
    # yaw 90 shifts the point toward the image-right edge of the up face
    c = _center(crop(gradient_faces(), 90, 60, fov=10, size=(64, 48)))
    assert c[0] == pytest.approx((1 + math.tan(math.radians(30))) / 2 * 255, abs=8)


def test_down_face_orientation_matches_the_layout_notes():
    c = _center(crop(gradient_faces(), 0, -60, fov=10, size=(64, 48)))
    assert c[2] == 200 and c[0] == pytest.approx(127.5, abs=8)
    assert c[1] == pytest.approx((1 - math.tan(math.radians(30))) / 2 * 255, abs=8)


def test_split_faces_cuts_the_strip_in_face_order_and_rejects_other_shapes():
    strip = Image.new("RGB", (6 * 8, 8))
    for i, color in enumerate(COLORS):
        strip.paste(color, (i * 8, 0, (i + 1) * 8, 8))
    faces = P.split_faces(strip)
    assert faces.shape == (6, 8, 8, 3)
    assert all((faces[i] == COLORS[i]).all() for i in range(6))
    with pytest.raises(ValueError):
        P.split_faces(Image.new("RGB", (100, 10)))


def test_crop_has_the_requested_size():
    assert P.render_crop(solid_faces(), 0, 0, 80, (1024, 768)).size == (1024, 768)
