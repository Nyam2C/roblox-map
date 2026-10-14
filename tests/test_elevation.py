"""Ground heights from street-view altitudes (src/elevation.py)."""
import pytest

import elevation as E


def test_the_surface_is_linear_between_road_points_and_flat_beyond_them():
    pts = [(0, 0, 10.0), (100, 0, 14.0), (0, 100, 10.0), (100, 100, 14.0)]
    xs, zs, h = E.surface(pts, 10.0)
    at = lambda x, z: h[list(zs).index(z), list(xs).index(x)]
    assert at(50, 50) == pytest.approx(12.0) and at(0, 0) == pytest.approx(10.0)
    assert at(xs[0], zs[0]) == pytest.approx(10.0) and at(xs[-1], zs[-1]) == pytest.approx(14.0)  # outside: the nearest road


def test_collect_keeps_going_on_a_bad_answer_and_stops_on_a_block(tmp_path, monkeypatch):
    import sqlite3, types
    db = tmp_path / "m.db"
    c = sqlite3.connect(db)
    c.execute("create table captures (pano_id text, lat real, lon real)")
    c.executemany("insert into captures values (?, ?, ?)", [("a", 37.5, 126.7), ("b", 37.5, 126.7), ("c", 37.5, 126.7)])
    c.commit()
    monkeypatch.setattr(E, "PAUSE_S", 0)
    cfg = {"db_path": str(db), "regions_dir": str(tmp_path)}
    monkeypatch.setattr(E.common, "resolve", lambda p: __import__("pathlib").Path(p))

    class Blocked(Exception):
        status = 429

    class Src:
        def by_id(self, pid):
            if pid == "b":
                raise Blocked()
            return types.SimpleNamespace(altitude=40.0)

    new, reason = E.collect(cfg, "r", 10, Src())
    assert new == 1 and reason.startswith("blocked") and list(E.load(E.path_of(cfg, "r"))) == ["a"]


def test_a_camera_far_above_its_neighbours_is_left_out():
    pts = [(x, 0.0, 37.0 + 0.01 * x) for x in range(0, 300, 10)] + [(140.0, 2.0, 42.5), (150.0, 2.0, 42.6), (160.0, 2.0, 42.4)]
    kept = E.clean(pts)
    assert len(kept) == 30 and all(p[2] < 40 for p in kept)  # a run of three high points goes too


def test_probe_keeps_neighbours_round_the_cell_with_altitudes_and_stops_on_a_block(tmp_path, monkeypatch):
    import types
    import h3
    cell = "8930e0af117ffff"
    monkeypatch.setattr(E, "PAUSE_S", 0)
    monkeypatch.setattr(E.common, "resolve", lambda p: __import__("pathlib").Path(p))
    cfg = {"regions_dir": str(tmp_path), "h3_res": 9}
    lat, lon = h3.cell_to_latlng(cell)
    pano = lambda i, dlat, alt: types.SimpleNamespace(id=i, lat=lat + dlat, lon=lon, altitude=alt)  # noqa: E731
    calls = []

    class Blocked(Exception):
        status = 403

    class Src:
        def nearby(self, a, b):
            calls.append((a, b))
            if len(calls) == 3:
                raise Blocked()
            return types.SimpleNamespace(id="c", lat=lat, lon=lon, altitude=39.0,
                                         neighbors=types.SimpleNamespace(street=[pano("n1", 0.001, 39.2), pano("far", 0.05, 30.0),
                                                                                 pano("none", 0.0, None)]))

    new, reason = E.probe(cfg, "r", [cell], Src())
    got = E.load(E.path_of(cfg, "r"))
    assert reason.startswith("blocked") and len(calls) == 3
    assert set(got) == {"c", "n1"} and new == 2  # far off the cell's ring and no altitude are left out, a repeat is not new
    assert len(E.probe_points(cell)) == 7 and all(h3.latlng_to_cell(a, b, 9) == cell for a, b in E.probe_points(cell))
