"""School buildings get one picture per face (BR-2.7, BR-4.7): faces of an outline, lines of sight, choosing a
panorama for each face (P3-9), planning and replanning in a run (P3-10), the new database columns and the settings.
Naver is never called: the fake source of test_capture.py stands in."""
from __future__ import annotations

import math
import random
import sqlite3
from pathlib import Path

import h3
import pytest
from hypothesis import given, settings, strategies as st

import capture
import common
import db
import panorama_source as ps
import projection
from generators import BASE, candidates, convex_outlines, offset, rect
from test_capture import CELL, FakeSource, make_cfg

SCHOOL_CENTER = BASE


def rot_rect(center, w, h, deg):
    """A w x h rectangle turned `deg` degrees clockwise from north-up."""
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return tuple(offset(center, (sx * w / 2) * c + (sy * h / 2) * s, -(sx * w / 2) * s + (sy * h / 2) * c)
                 for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)))


def az_set(faces):
    return sorted(round(f.azimuth_deg) % 360 for f in faces)


# --- faces of an outline -------------------------------------------------------------------------------------------

def test_a_rectangle_has_four_faces_facing_the_compass_directions():
    faces = projection.building_faces(rect(BASE, 40, 20), 1)
    assert az_set(faces) == [0, 90, 180, 270]
    assert sorted(round(f.length_m) for f in faces) == [20, 20, 40, 40]
    assert faces[0].length_m == pytest.approx(40, abs=0.5)  # longest first


@settings(max_examples=40)
@given(st.floats(0, 359), st.floats(15, 80), st.floats(8, 40))
def test_p3_9_turning_a_building_turns_its_faces_and_the_winding_does_not_matter(deg, w, h):
    base = projection.building_faces(rot_rect(BASE, w, h, 0), 1)
    turned = projection.building_faces(rot_rect(BASE, w, h, deg), 1)
    reversed_ = projection.building_faces(tuple(reversed(rot_rect(BASE, w, h, deg))), 1)
    assert len(turned) == len(base) == 4
    assert sorted(round(f.length_m, 1) for f in turned) == pytest.approx(sorted(round(f.length_m, 1) for f in base), abs=0.3)
    for f in base:  # each direction of the unturned building shows up turned by `deg`
        assert any(projection.angle_gap_deg((f.azimuth_deg + deg) % 360, g.azimuth_deg) < 0.2 for g in turned)
    for f in turned:  # the same four directions, whichever way the outline is written (no rounding at 0.5 degrees)
        assert any(projection.angle_gap_deg(f.azimuth_deg, g.azimuth_deg) < 0.2 for g in reversed_)
    assert len(reversed_) == len(turned)


@settings(max_examples=60)
@given(convex_outlines())
def test_p3_9_every_face_points_away_from_the_building(outline):
    for face in projection.building_faces(outline, 1):
        out = offset(face.target, 0.5 * math.sin(math.radians(face.azimuth_deg)), 0.5 * math.cos(math.radians(face.azimuth_deg)))
        inn = offset(face.target, -0.5 * math.sin(math.radians(face.azimuth_deg)), -0.5 * math.cos(math.radians(face.azimuth_deg)))
        assert not projection.point_in_polygon(out, list(outline))
        assert projection.point_in_polygon(inn, list(outline))


def test_short_faces_are_left_out_and_an_l_shape_has_four_sides_with_summed_lengths():
    assert len(projection.building_faces(rect(BASE, 40, 6), 8)) == 2  # the two 6 m ends are dropped
    pts = [(0, 0), (40, 0), (40, 12), (12, 12), (12, 30), (0, 30)]
    l_shape = tuple(offset(BASE, x, y) for x, y in pts)
    faces = projection.building_faces(l_shape, 1)
    assert az_set(faces) == [0, 90, 180, 270]                       # six edges, four sides
    by_az = {round(f.azimuth_deg) % 360: f.length_m for f in faces}
    assert by_az[180] == pytest.approx(40, abs=0.5) and by_az[0] == pytest.approx(40, abs=0.5)  # 28 + 12 on the north side
    assert by_az[90] == pytest.approx(30, abs=0.5) and by_az[270] == pytest.approx(30, abs=0.5)


def test_a_stepped_wall_is_one_side_aimed_at_its_longest_step():
    # the north wall of a 60 m building has two notches that face east and west
    pts = [(0, 0), (60, 0), (60, 20), (45, 20), (45, 16), (30, 16), (30, 20), (0, 20)]
    faces = projection.building_faces(tuple(offset(BASE, x, y) for x, y in pts), 1)
    north = [f for f in faces if projection.angle_gap_deg(f.azimuth_deg, 0) < 5]
    assert len(north) == 1 and north[0].length_m == pytest.approx(15 + 15 + 30, abs=0.5)
    assert projection.distance_m(north[0].target, offset(BASE, 15, 20)) < 0.5   # the longest piece is x 0..30


@given(st.floats(0, 359.9), st.floats(1, 200))
def test_point_toward_goes_that_far_in_that_direction(az, meters):
    p = projection.point_toward(BASE, az, meters)
    assert projection.distance_m(BASE, p) == pytest.approx(meters, rel=1e-3, abs=1e-3)
    assert projection.angle_gap_deg(projection.bearing_deg(BASE, p), az) < 0.05


def test_a_gently_curved_wall_is_one_face_and_a_strongly_curved_one_is_several():
    def curved(half_angle):
        arc = [offset(BASE, 20 * math.sin(math.radians(a)), -20 * math.cos(math.radians(a)))
               for a in range(-half_angle, half_angle + 1, 5)]
        return tuple(arc + [offset(BASE, 0, 15)])

    def south_faces(outline):
        return [f for f in projection.building_faces(outline, 1) if projection.angle_gap_deg(f.azimuth_deg, 180) < 60
                and f.length_m < 30]
    gentle = [f for f in south_faces(curved(20)) if projection.angle_gap_deg(f.azimuth_deg, 180) < 5]
    assert len(gentle) == 1 and gentle[0].length_m > 12  # the whole 40 degree arc is one face
    assert len(south_faces(curved(60))) >= 2             # a 120 degree arc is split


def test_the_dropped_corner_and_degenerate_outlines_give_no_faces():
    assert projection.building_faces([BASE, offset(BASE, 5, 0)], 1) == []
    assert projection.building_faces([BASE, offset(BASE, 5, 0), offset(BASE, 10, 0)], 1) == []


# --- lines of sight ------------------------------------------------------------------------------------------------

def test_segment_and_polygon():
    poly = list(rect(BASE, 20, 20))
    assert projection.segment_hits_polygon(offset(BASE, -50, 0), offset(BASE, 50, 0), poly)       # straight through
    assert projection.segment_hits_polygon(offset(BASE, 0, 0), offset(BASE, 50, 50), poly)        # starts inside
    assert not projection.segment_hits_polygon(offset(BASE, -50, 30), offset(BASE, 50, 30), poly)  # passes beside
    assert not projection.segment_hits_polygon(offset(BASE, -50, -50), offset(BASE, -50, 50), poly)


def test_a_building_in_front_blocks_and_the_own_wall_does_not():
    house = rect(BASE, 40, 20)  # the school building
    south_wall = (offset(BASE, 0, -10)[0], offset(BASE, 0, -10)[1])
    pano_south = offset(BASE, 0, -60)
    pano_north = offset(BASE, 0, 60)
    shed = list(rect(offset(BASE, 0, -35), 10, 6))  # between the south pano and the south wall
    assert not projection.line_blocked(pano_south, south_wall, list(house))   # the wall's own building does not block from outside
    assert projection.line_blocked(pano_north, south_wall, list(house))       # seen through the building from behind
    assert projection.line_blocked(pano_south, south_wall, shed)
    assert not projection.line_blocked(pano_south, south_wall, list(rect(offset(BASE, 80, -35), 10, 6)))


# --- choosing a panorama for each face (P3-9) --------------------------------------------------------------------

def cand(pano_id, dx, dy):
    return ps.Candidate(pano_id, *offset(BASE, dx, dy))


def faces_of(w=40, h=20, min_len=8):
    outline = rect(BASE, w, h)
    return outline, projection.building_faces(outline, min_len)


def test_each_face_gets_the_best_panorama_on_its_own_side():
    outline, faces = faces_of()
    cands = [cand("south", 0, -60), cand("south2", 5, -90), cand("north", 0, 55), cand("east", 70, 0), cand("west", -75, 0),
             cand("far", 0, -300)]
    got = capture.select_faces(outline, faces, cands, [], limit_m=120, max_angle_deg=60, max_views=6, usable=lambda _: True)
    by_face = {round(f.azimuth_deg): p.pano_id for f, p in got}
    assert by_face == {180: "south", 0: "north", 90: "east", 270: "west"}
    assert len({p.pano_id for _, p in got}) == len(got)


def test_a_blocked_panorama_is_skipped_and_a_face_with_nothing_clear_gets_no_picture():
    outline, faces = faces_of()
    shed = list(rect(offset(BASE, 0, -35), 14, 6))
    cands = [cand("south", 0, -60), cand("south_east", 40, -70), cand("north", 0, 55)]
    got = capture.select_faces(outline, faces, cands, [shed], limit_m=120, max_angle_deg=60, max_views=6, usable=lambda _: True)
    by_face = {round(f.azimuth_deg): p.pano_id for f, p in got}
    assert by_face[180] == "south_east" and by_face[0] == "north"
    wall = list(rect(offset(BASE, 0, -35), 200, 6))  # a long wall hides everything on the south side
    got = capture.select_faces(outline, faces, cands, [wall], limit_m=120, max_angle_deg=60, max_views=6, usable=lambda _: True)
    assert 180 not in {round(f.azimuth_deg) for f, _ in got}


def test_an_unusable_panorama_is_skipped_and_the_longest_faces_come_first():
    outline, faces = faces_of()
    cands = [cand("south", 0, -60), cand("south_b", 10, -64), cand("north", 0, 55), cand("east", 70, 0), cand("west", -75, 0)]
    got = capture.select_faces(outline, faces, cands, [], limit_m=120, max_angle_deg=60, max_views=2,
                               usable=lambda pid: pid != "south")
    assert [round(f.azimuth_deg) for f, _ in got][0] in (180, 0) and len(got) == 2  # only the two long faces
    assert "south" not in {p.pano_id for _, p in got} and "south_b" in {p.pano_id for _, p in got}


@settings(max_examples=60)
@given(candidates(BASE, 150.0), st.floats(40, 150), st.floats(20, 80), st.integers(1, 6), st.integers(0, 10**6))
def test_p3_9_picks_are_in_range_in_view_unblocked_distinct_and_independent_of_order(cands, limit, max_angle, max_views, seed):
    outline, faces = faces_of(40, 20, 8)
    blockers = [list(rect(offset(BASE, 25, -45), 20, 8)), list(rect(offset(BASE, -35, 40), 15, 10))]
    kwargs = dict(limit_m=limit, max_angle_deg=max_angle, max_views=max_views, usable=lambda pid: int(pid[1:]) % 5 != 0)
    got = capture.select_faces(outline, faces, cands, blockers, **kwargs)
    ids = [p.pano_id for _, p in got]
    assert len(ids) == len(set(ids)) and len(got) <= min(max_views, len(faces))
    for face, pick in got:
        pos = (pick.lat, pick.lon)
        assert 1.0 <= pick.distance_m <= limit
        assert projection.angle_gap_deg(projection.bearing_deg(face.target, pos), face.azimuth_deg) <= max_angle + 1e-6
        assert not projection.line_blocked(pos, face.target, list(outline))
        assert not any(projection.line_blocked(pos, face.target, b) for b in blockers)
        assert int(pick.pano_id[1:]) % 5 != 0
    shuffled = list(cands)
    random.Random(seed).shuffle(shuffled)
    again = capture.select_faces(outline, faces, shuffled, blockers, **kwargs)
    assert [(round(f.azimuth_deg, 6), p.pano_id) for f, p in again] == [(round(f.azimuth_deg, 6), p.pano_id) for f, p in got]


# --- a run with a school building (P3-10) ----------------------------------------------------------------------

def school_row(i, center, w=40, h=20):
    return {"building_id": f"gis:{i}", "cell_id": CELL, "source": "gis", "outline": [list(p) for p in rect(center, w, h)],
            "centroid": list(center), "gis_key": str(i), "osm_id": None, "name": "", "osm_tags": None,
            "floors_above": 5, "floors_below": 0, "height_m": 20.0, "usability_code": None, "approval_date": None,
            "building_area": 800.0, "osm_height_m": None, "osm_levels": None, "status": "ok"}


def world_around():
    spots = {"s1": (0, -60, 0.0), "s2": (35, -75, 10.0), "n1": (0, 55, 180.0), "e1": (70, 0, 270.0), "w1": (-75, 0, 90.0),
             "q1": (400, -50, 0.0), "q2": (440, 40, 180.0), "q3": (350, 10, 90.0)}  # q*: near the plain building
    return {pid: {"lat": offset(BASE, dx, dy)[0], "lon": offset(BASE, dx, dy)[1], "heading": hd} for pid, (dx, dy, hd) in spots.items()}


def square_around(center, half=60):
    return [[*offset(center, dx, dy)] for dx, dy in ((-half, -half), (half, -half), (half, half), (-half, half))]


def make_school_db():
    conn = db.connect(":memory:")
    plain = offset(BASE, 400, 0)  # far from the school, so it blocks nothing
    db.replace_cell_rows(conn, CELL, {"buildings": [school_row(1, BASE), school_row(2, plain, 20, 15)]})
    return conn


def school_cfg(root, **extra):
    return {**make_cfg(root), "school_polygons": [square_around(BASE)], **extra}


def run_school(conn, cfg, source, root, replan=False, replan_school=False):
    cap = capture.Capture(conn, cfg, source, root)
    return cap, cap.run_cell(CELL, replan, replan_school)


def views_of(conn, building_id):
    return [v for v in db.views_for_cell(conn, CELL) if v["building_id"] == building_id]


def test_a_school_building_gets_one_view_per_face_and_other_buildings_keep_the_nearest_first_rule(tmp_path):
    conn, source = make_school_db(), FakeSource(world_around())
    cap, counts = run_school(conn, school_cfg(tmp_path), source, tmp_path)
    school, plain = views_of(conn, "gis:1"), views_of(conn, "gis:2")
    assert counts["school_buildings"] == 1 and counts["face_views"] == len(school) >= 3
    assert all(v["face_deg"] is not None and v["target_lat"] is not None and v["status"] == "cropped" for v in school)
    assert [v["rank"] for v in school] == list(range(1, len(school) + 1))
    assert len({v["pano_id"] for v in school}) == len(school)
    assert all(v["face_deg"] is None and v["target_lat"] is None for v in plain)
    for v in school:  # the picture is aimed at the face, not at the center
        pano = cap.panos[v["pano_id"]]
        bearing = projection.bearing_deg((pano["lat"], pano["lon"]), (v["target_lat"], v["target_lon"]))
        assert v["bearing_deg"] == pytest.approx(bearing, abs=1e-6)
        assert v["yaw_deg"] == pytest.approx(projection.yaw_deg(bearing, pano["heading_deg"]), abs=1e-6)
        assert (tmp_path / v["crop_path"]).is_file()


def test_the_first_face_view_is_the_longest_face_and_the_south_face_gets_the_south_panorama(tmp_path):
    conn = make_school_db()
    run_school(conn, school_cfg(tmp_path), FakeSource(world_around()), tmp_path)
    school = views_of(conn, "gis:1")
    assert round(school[0]["face_deg"]) in (0, 180)  # the 40 m faces face north and south
    south = next(v for v in school if round(v["face_deg"]) == 180)
    assert south["pano_id"] in ("s1", "s2")


def test_lookups_are_also_made_in_front_of_each_face_and_shared_between_close_points(tmp_path):
    conn, source = make_school_db(), FakeSource(world_around())
    run_school(conn, school_cfg(tmp_path), source, tmp_path)
    faces = projection.building_faces(rect(BASE, 40, 20), 8)
    asked = {call[1] for call in source.calls if call[0] == "nearby"}
    for f in faces:
        for m in capture.PROBE_DISTANCES_M:
            p = projection.point_toward(f.target, f.azimuth_deg, m)
            assert f"{p[0]},{p[1]}" in asked
    nearby_calls = [c for c in source.calls if c[0] == "nearby"]
    assert len(nearby_calls) == len(set(nearby_calls))   # nothing is asked twice


def test_running_again_changes_nothing_and_downloads_nothing(tmp_path):
    conn, source = make_school_db(), FakeSource(world_around())
    run_school(conn, school_cfg(tmp_path), source, tmp_path)
    first = [tuple(v.values()) for v in db.views_for_cell(conn, CELL)]
    again = FakeSource(world_around())
    _, counts = run_school(conn, school_cfg(tmp_path), again, tmp_path)
    assert [tuple(v.values()) for v in db.views_for_cell(conn, CELL)] == first
    assert again.downloads == [] and counts["new_downloads"] == 0 and counts["crops"] == 0


def test_replan_school_starts_over_for_the_school_only(tmp_path):
    conn = make_school_db()
    run_school(conn, school_cfg(tmp_path), FakeSource(world_around()), tmp_path)
    plain_before = [tuple(v.values()) for v in views_of(conn, "gis:2")]
    plain_files = {v["crop_path"]: (tmp_path / v["crop_path"]).read_bytes() for v in views_of(conn, "gis:2")}
    old_school_crops = [v["crop_path"] for v in views_of(conn, "gis:1")]
    source = FakeSource(world_around())
    cap, counts = run_school(conn, school_cfg(tmp_path, school_max_views=2), source, tmp_path, replan_school=True)
    assert len(views_of(conn, "gis:1")) == 2 and counts["face_views"] == 2          # replanned with the new setting
    assert [tuple(v.values()) for v in views_of(conn, "gis:2")] == plain_before     # the other building is untouched
    assert {v["crop_path"]: (tmp_path / v["crop_path"]).read_bytes() for v in views_of(conn, "gis:2")} == plain_files
    kept = {v["crop_path"] for v in views_of(conn, "gis:1")}
    assert all(not (tmp_path / p).exists() for p in old_school_crops if p not in kept)  # stale crops are removed
    plain_center = offset(BASE, 400, 0)
    assert ("nearby", f"{plain_center[0]},{plain_center[1]}") not in source.calls  # it was not looked up again


def test_a_school_building_with_no_panorama_in_view_falls_back_to_nearest_first(tmp_path):
    conn = make_school_db()
    far = {"x": {"lat": offset(BASE, 0, -500)[0], "lon": offset(BASE, 0, -500)[1], "heading": 0.0}}  # beyond 120 m
    _, counts = run_school(conn, school_cfg(tmp_path), FakeSource(far), tmp_path)
    assert all(v["status"] == "no_photo" and v["face_deg"] is None for v in views_of(conn, "gis:1"))
    assert counts["face_views"] == 0 and counts["no_photo"] == 2


def test_without_school_polygons_nothing_changes(tmp_path):
    conn = make_school_db()
    cfg = {**make_cfg(tmp_path), "school_polygons": []}
    _, counts = run_school(conn, cfg, FakeSource(world_around()), tmp_path)
    assert counts["school_buildings"] == 0 and counts["face_views"] == 0
    assert all(v["face_deg"] is None for v in db.views_for_cell(conn, CELL))


def test_a_tall_neighbour_hides_a_wall_but_a_low_school_structure_does_not(tmp_path):
    conn = db.connect(":memory:")
    low = school_row(3, offset(BASE, 0, -30), 12, 6)        # a shed inside the school, height unknown
    low["height_m"], low["floors_above"] = None, None
    tall_house = school_row(4, offset(BASE, 0, -45), 30, 8)  # outside the school polygon, 15 m tall
    tall_house["height_m"] = 15.0
    cfg = school_cfg(tmp_path, school_polygons=[square_around(BASE, 40)])
    db.replace_cell_rows(conn, CELL, {"buildings": [school_row(1, BASE), low, tall_house]})
    cap = capture.Capture(conn, cfg, FakeSource(world_around()), tmp_path)
    cap.neighbor_buildings = db.rows_in_cells(conn, "buildings", [CELL])
    ids = {tuple(map(tuple, o)) for o in cap._blocking_outlines(school_row(1, BASE))}
    tall = tuple(tuple(p) for p in tall_house["outline"])
    shed = tuple(tuple(p) for p in low["outline"])
    assert tall in ids and shed not in ids


# --- database and settings ---------------------------------------------------------------------------------------

def test_an_older_database_gets_the_new_columns_and_keeps_its_rows(tmp_path):
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.executescript("""CREATE TABLE building_views (
        building_id TEXT NOT NULL, rank INTEGER NOT NULL, pano_id TEXT, distance_m REAL, bearing_deg REAL,
        yaw_deg REAL, fov_deg REAL, pitch_deg REAL, crop_path TEXT, status TEXT NOT NULL, PRIMARY KEY (building_id, rank));
        INSERT INTO building_views VALUES ('gis:1', 1, 'p', 10.0, 20.0, 30.0, 60.0, 5.0, 'a.jpg', 'cropped');""")
    old.commit()
    old.close()
    conn = db.connect(path)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(building_views)")}
    assert {"face_deg", "target_lat", "target_lon"} <= cols
    assert conn.execute("SELECT building_id, crop_path, face_deg FROM building_views").fetchall() == [("gis:1", "a.jpg", None)]
    db.connect(path)  # a second time must not fail


def test_deleting_views_for_some_buildings_only_returns_their_crop_paths():
    conn = db.connect(":memory:")
    row = lambda b, r, p: {"building_id": b, "rank": r, "pano_id": "p", "distance_m": 1.0, "bearing_deg": 1.0, "yaw_deg": 1.0,
                           "fov_deg": 60.0, "pitch_deg": 0.0, "crop_path": p, "status": "cropped", "face_deg": None,
                           "target_lat": None, "target_lon": None}
    db.upsert_building_views(conn, [row("a", 1, "a1.jpg"), row("a", 2, "a2.jpg"), row("b", 1, "b1.jpg")])
    assert sorted(db.delete_views_for_buildings(conn, ["a"])) == ["a1.jpg", "a2.jpg"]
    assert [r[0] for r in conn.execute("SELECT building_id FROM building_views")] == ["b"]
    assert db.delete_views_for_buildings(conn, []) == []


def test_the_school_settings_are_checked(tmp_path):
    p = tmp_path / "c.toml"
    for bad in ("school_max_views = 0", "school_face_min_m = 0", "school_face_max_deg = 95"):
        p.write_text(bad + "\n", encoding="utf-8")
        with pytest.raises(ValueError):
            common.load_config(p)
    for polys in ([[[37.5, 126.7], [37.5, 126.8]]], [[[137.5, 126.7], [37.5, 126.8], [37.4, 126.8]]], 5):  # region.toml keys
        with pytest.raises(ValueError):
            common.check_config({**common.DEFAULTS, "school_polygons": polys})
    common.check_config({**common.DEFAULTS, "school_polygons": [[[37.5, 126.7], [37.5, 126.8], [37.6, 126.8]]]})


def test_the_configured_school_polygon_holds_the_high_school_and_not_its_neighbours():
    polygon = [tuple(p) for p in common.cell_config(common.load_config(), "8930e0af13bffff")["school_polygons"][0]]
    assert projection.point_in_polygon((37.50469, 126.77911), polygon)      # the main building
    assert projection.point_in_polygon((37.50413, 126.77866), polygon)      # the west wing
    assert not projection.point_in_polygon((37.50542, 126.77778), polygon)  # the middle school next door
    assert not projection.point_in_polygon((37.50309, 126.77920), polygon)  # the elementary school next door
