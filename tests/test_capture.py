"""U3 capture: panorama selection (P3-3), cap and resume (P3-6), stop on block (P3-7), file paths (P3-8),
failure rules, and the adapter's error classes, retries and reply checks. Naver is never called: a fake source
and synthetic images stand in."""
from __future__ import annotations

import itertools
import math
import random
import re
import zlib
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from hypothesis import assume, given, settings, strategies as st
from PIL import Image

import capture
import common
import db
import panorama_source as ps
import projection
from generators import BASE, candidates, offset, rect

CELL = "8930e0af13bffff"
SAFE = re.compile(r"[A-Za-z0-9_.-]+")


# --- P3-3 choosing panoramas -------------------------------------------------------------------------------------

@settings(max_examples=100)
@given(candidates(), st.floats(30, 200), st.floats(0, 180), st.integers(1, 6), st.integers(1, 4), st.integers(0, 10**6))
def test_p3_3_selection_follows_the_rules_and_ignores_input_order(cands, limit, sep, max_views, salt, seed):
    asked: list[str] = []

    def usable(pano_id: str) -> bool:
        asked.append(pano_id)
        return int(pano_id[1:]) % salt != 0

    kwargs = dict(limit_m=limit, separation_deg=sep, max_views=max_views, usable=usable)
    picks = capture.select_panoramas(cands, BASE, **kwargs)
    near = sorted(((projection.distance_m((c.lat, c.lon), BASE), c.pano_id) for c in cands if
                   projection.distance_m((c.lat, c.lon), BASE) <= limit))
    first_usable = next((pid for _, pid in near if int(pid[1:]) % salt != 0), None)
    ids = [p.pano_id for p in picks]
    assert len(ids) == len(set(ids)) <= max_views
    assert all(p.distance_m <= limit and int(p.pano_id[1:]) % salt != 0 for p in picks)
    assert all(capture._angle_gap(a.bearing_deg, b.bearing_deg) >= sep for i, a in enumerate(picks) for b in picks[:i])
    assert (ids[0] if ids else None) == first_usable  # the nearest usable one comes first, and one is chosen if any can be
    assert all(a.distance_m <= b.distance_m for a, b in zip(picks, picks[1:]))
    assert set(asked) <= {pid for _, pid in near}  # the metadata check is only asked about candidates in range
    if len(picks) < max_views:  # nothing else could have been added
        for _, pid in near:
            if pid not in ids and int(pid[1:]) % salt != 0:
                c = next(c for c in cands if c.pano_id == pid)
                bearing = projection.bearing_deg((c.lat, c.lon), BASE)
                assert any(capture._angle_gap(bearing, q.bearing_deg) < sep for q in picks)
    shuffled = list(cands)
    random.Random(seed).shuffle(shuffled)
    assert [p.pano_id for p in capture.select_panoramas(shuffled, BASE, **kwargs)] == ids


# --- fake world ---------------------------------------------------------------------------------------------------------

FACE = 32


def _strip(pano_id: str) -> Image.Image:
    rng = np.random.default_rng(zlib.crc32(pano_id.encode()))
    return Image.fromarray(rng.integers(0, 256, (FACE, 6 * FACE, 3), dtype=np.uint8))


class FakeSource:
    """Stands in for PanoramaSource: same four members, records every call, can block or fail on demand."""

    def __init__(self, panos: dict[str, dict], blocked_at: int | None = None, fail_downloads: set[int] | None = None):
        self.panos, self.blocked_at, self.fail_downloads = panos, blocked_at, fail_downloads or set()
        self.calls: list[tuple[str, str]] = []
        self.downloads: list[str] = []
        self.rejected = 0

    def _call(self, kind: str, arg: str) -> None:
        self.calls.append((kind, arg))
        if self.blocked_at is not None and len(self.calls) >= self.blocked_at:
            raise ps.BlockedError("blocked: HTTPError (HTTP 429)")

    def find_nearby(self, lat, lon):
        self._call("nearby", f"{lat},{lon}")
        return [ps.Candidate(i, p["lat"], p["lon"]) for i, p in sorted(self.panos.items())]

    def get_metadata(self, pano_id):
        self._call("meta", pano_id)
        p = self.panos.get(pano_id)
        if p is None or not p.get("usable", True):
            return None
        return ps.PanoMeta(pano_id, p["lat"], p["lon"], p["heading"], "2026-05-27T14:28:00", True, 4)

    def download_strip(self, pano_id):
        self._call("download", pano_id)
        self.downloads.append(pano_id)
        if len(self.downloads) in self.fail_downloads:
            raise ps.SourceError("request failed: HTTPError (HTTP 404)")
        return _strip(pano_id)


def world() -> dict[str, dict]:
    panos = {f"p{x}{y}": {"lat": offset(BASE, 30 * x, 30 * y)[0], "lon": offset(BASE, 30 * x, 30 * y)[1],
                          "heading": float((x * 37 + y * 91) % 360)} for x in range(-2, 3) for y in range(-2, 3)}
    panos["old1"] = {**dict(zip(("lat", "lon"), offset(BASE, 5, 5))), "heading": 10.0, "usable": False}  # not the latest
    return panos


def building_row(i: int, center) -> dict:
    return {"building_id": f"gis:{i}", "cell_id": CELL, "source": "gis", "outline": [list(p) for p in rect(center, 20, 15)],
            "centroid": list(center), "gis_key": str(i), "osm_id": None, "name": "", "osm_tags": None,
            "floors_above": 5, "floors_below": 0, "height_m": None, "usability_code": None, "approval_date": None,
            "building_area": 300.0, "osm_height_m": None, "osm_levels": None, "status": "ok"}


def make_db(n_buildings: int, far: bool = False):
    conn = db.connect(":memory:")
    centers = [offset(BASE, -30 + 25 * i, 10) for i in range(n_buildings)] + ([offset(BASE, 600, 0)] if far else [])
    db.replace_cell_rows(conn, CELL, {"buildings": [building_row(i, c) for i, c in enumerate(centers)]})
    return conn


def make_cfg(root: Path, cap: int = 100) -> dict:
    return {**common.DEFAULTS, "pano_pause_s": 0, "crop_width": 64, "crop_height": 48, "max_new_panos": cap,
            "backup_dir": str(root / "backups")}


def run_once(conn, cfg, source, root, replan=False):
    """One invocation: fresh state, like starting the script again."""
    cap = capture.Capture(conn, cfg, source, root)
    try:
        return cap.run_cell(CELL, replan), None
    except capture.Stop as stop:
        return cap.counts, stop


def snapshot(conn, root: Path):
    views = [tuple(v.values()) for v in db.views_for_cell(conn, CELL)]
    caps = [tuple(v for k, v in c.items() if k != "downloaded_at") for c in db.all_captures(conn)]
    files = {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*.jpg"))}
    return views, caps, files


def test_view_params_aim_by_the_nearest_wall_so_a_close_building_keeps_its_roof_and_ground():
    # 4 floors (13.6 m), the facade 8 m from the panorama and the center 28 m away
    outline = [offset(BASE, -10, 8), offset(BASE, 10, 8), offset(BASE, 10, 48), offset(BASE, -10, 48)]
    building = {**building_row(0, offset(BASE, 0, 28)), "outline": [list(p) for p in outline], "floors_above": 4}
    v = capture.view_params(building, {"lat": BASE[0], "lon": BASE[1], "heading_deg": 0.0}, common.DEFAULTS)
    up, down = math.degrees(math.atan2(13.6 - 2.5, 8)), math.degrees(math.atan2(2.5, 8))
    half = math.degrees(math.atan(math.tan(math.radians(v["fov_deg"]) / 2) * 0.75))
    assert v["distance_m"] == pytest.approx(28, rel=3e-3)  # still the center distance (U4 reads it)
    assert up <= v["pitch_deg"] + half and -down >= v["pitch_deg"] - half
    assert v["pitch_deg"] > math.degrees(math.atan2(13.6 / 2 - 2.5, 28))  # the center-distance rule aimed lower and cut the roof


# --- P3-6 cap and resume --------------------------------------------------------------------------------------------------

@settings(max_examples=15, deadline=None)
@given(st.integers(1, 6), st.integers(1, 4), st.booleans())
def test_p3_6_capped_runs_resume_to_the_same_result_as_one_unlimited_run(tmp_path_factory, cap, n_buildings, far):
    base = tmp_path_factory.mktemp("p36")
    full_conn, full_root = make_db(n_buildings, far), base / "full"
    _, stop = run_once(full_conn, make_cfg(base, 100), FakeSource(world()), full_root)
    assert stop is None

    conn, root = make_db(n_buildings, far), base / "capped"
    source_runs = []
    for _ in range(60):
        source = FakeSource(world())
        _, stop = run_once(conn, make_cfg(base, cap), source, root)
        source_runs.append(source)
        assert len(source.downloads) <= cap  # never more new panoramas than the cap in one run
        if stop is None:
            break
        assert stop.reason == "cap"
    else:
        pytest.fail("capped runs never finished")
    assert snapshot(conn, root) == snapshot(full_conn, full_root)

    again = FakeSource(world())
    counts, stop = run_once(conn, make_cfg(base, cap), again, root)
    assert stop is None and again.calls == []  # everything is there: no lookups, no downloads (BR-1.2, BR-3.1)
    assert counts["crops"] == 0 and counts["crops_kept"] == sum(1 for v in db.views_for_cell(conn, CELL) if v["pano_id"])


def test_a_shared_panorama_is_downloaded_once(tmp_path):
    conn, source = make_db(4), FakeSource(world())
    counts, _ = run_once(conn, make_cfg(tmp_path), source, tmp_path / "c")
    assert counts["panos_skipped"] == 1  # the one panorama the metadata check rejects ("old1"), counted once for the run
    assert len(source.downloads) == len(set(source.downloads)) < sum(1 for v in db.views_for_cell(conn, CELL))


def test_no_photo_buildings_are_not_looked_up_again_until_replan(tmp_path):
    conn, root = make_db(2, far=True), tmp_path / "c"
    first = FakeSource(world())
    run_once(conn, make_cfg(tmp_path), first, root)
    views = {v["building_id"]: v for v in db.views_for_cell(conn, CELL)}
    assert views["gis:2"]["status"] == "no_photo" and views["gis:2"]["pano_id"] is None
    second = FakeSource(world())
    run_once(conn, make_cfg(tmp_path), second, root)
    assert second.calls == []
    third = FakeSource(world())
    run_once(conn, make_cfg(tmp_path), third, root, replan=True)
    assert [c for c in third.calls if c[0] == "nearby"] and not third.downloads  # looked up again, pictures reused
    assert {v["building_id"]: v["status"] for v in db.views_for_cell(conn, CELL)}["gis:2"] == "no_photo"


def test_replan_clears_this_cells_views_and_crops_but_keeps_panoramas_and_other_tables(tmp_path):
    conn, root = make_db(2), tmp_path / "c"
    run_once(conn, make_cfg(tmp_path), FakeSource(world()), root)
    buildings = db.rows_in_cells(conn, "buildings", [CELL])
    crops = [v["crop_path"] for v in db.views_for_cell(conn, CELL)]
    panos = [c["file_path"] for c in db.all_captures(conn) if c["file_path"]]
    assert crops and panos and all((root / c).is_file() for c in crops)
    _, stop = run_once(conn, make_cfg(tmp_path), FakeSource(world(), blocked_at=1), root, replan=True)
    assert stop.reason == "blocked"  # stopped right after the deletion, so the deletion alone can be seen
    assert db.views_for_cell(conn, CELL) == [] and not any((root / c).exists() for c in crops)
    assert db.rows_in_cells(conn, "buildings", [CELL]) == buildings and all((root / p).is_file() for p in panos)
    assert list((tmp_path / "backups").glob("map-*.db"))  # the database was copied before anything was deleted


# --- P3-7 stop on block -------------------------------------------------------------------------------------------------------

def _total_calls(tmp_path) -> int:
    source = FakeSource(world())
    run_once(make_db(3), make_cfg(tmp_path), source, tmp_path / "count")
    return len(source.calls)


def test_p3_7_no_call_follows_a_block_and_what_was_saved_stays(tmp_path_factory):
    base = tmp_path_factory.mktemp("p37")
    total = _total_calls(base)

    runs = itertools.count()

    @settings(max_examples=40, deadline=None)
    @given(st.integers(1, total))
    def check(k):
        conn, root = make_db(3), base / f"b{next(runs)}"
        source = FakeSource(world(), blocked_at=k)
        _, stop = run_once(conn, make_cfg(base), source, root)
        assert stop is not None and stop.reason == "blocked"
        assert len(source.calls) == k  # the blocked call was the last one made
        for c in db.all_captures(conn):
            assert c["status"] != "downloaded" or (root / c["file_path"]).is_file()
        for v in db.views_for_cell(conn, CELL):
            assert v["status"] != "cropped" or (root / v["crop_path"]).is_file()

    check()


# --- failure rules (BR-4.6, BR-5.2, BR-5.5) ----------------------------------------------------------------------------------------------------

def test_three_failures_in_a_row_stop_the_run(tmp_path):
    source = FakeSource(world(), fail_downloads={1, 2, 3, 4, 5, 6})
    counts, stop = run_once(make_db(3), make_cfg(tmp_path), source, tmp_path / "c")
    assert stop is not None and stop.reason == "failures" and len(source.downloads) == capture.STREAK_LIMIT
    assert counts["failures"] == capture.STREAK_LIMIT


def test_one_failed_panorama_does_not_stop_the_others_and_is_retried_next_run(tmp_path):
    conn, root = make_db(3), tmp_path / "c"
    source = FakeSource(world(), fail_downloads={1})
    counts, stop = run_once(conn, make_cfg(tmp_path), source, root)
    assert stop is None and counts["failures"] == 1 and counts["crops"] > 0
    failed = [c for c in db.all_captures(conn) if c["status"] == "failed"]
    assert len(failed) == 1
    pending = [v for v in db.views_for_cell(conn, CELL) if v["status"] == "planned"]
    assert pending and all(v["pano_id"] == failed[0]["pano_id"] for v in pending)
    run_once(conn, make_cfg(tmp_path), FakeSource(world()), root)
    assert {v["status"] for v in db.views_for_cell(conn, CELL)} == {"cropped"}
    assert {c["status"] for c in db.all_captures(conn)} == {"downloaded"}


def test_a_failing_crop_is_recorded_and_the_other_crops_continue(tmp_path, monkeypatch):
    conn, root = make_db(2), tmp_path / "c"
    real = projection.render_crop
    calls = []

    def flaky(*args, **kwargs):
        calls.append(1)
        if len(calls) == 2:
            raise ValueError("boom")
        return real(*args, **kwargs)

    monkeypatch.setattr(projection, "render_crop", flaky)
    counts, stop = run_once(conn, make_cfg(tmp_path), FakeSource(world()), root)
    statuses = [v["status"] for v in db.views_for_cell(conn, CELL)]
    assert stop is None and statuses.count("failed") == 1 and statuses.count("cropped") == len(statuses) - 1
    assert counts["failures"] == 1
    monkeypatch.setattr(projection, "render_crop", real)
    run_once(conn, make_cfg(tmp_path), FakeSource(world()), root)
    assert {v["status"] for v in db.views_for_cell(conn, CELL)} == {"cropped"}


def test_crops_are_remade_only_when_their_values_change(tmp_path):
    conn, root = make_db(2), tmp_path / "c"
    run_once(conn, make_cfg(tmp_path), FakeSource(world()), root)

    def fovs():
        return {(v["building_id"], v["rank"]): v["fov_deg"] for v in db.views_for_cell(conn, CELL) if v["pano_id"]}

    for change in ({"fov_max_deg": 110}, {"fov_min_deg": 70}):  # BR-4.5: a crop is remade exactly when its values changed
        before, source = fovs(), FakeSource(world())
        counts, _ = run_once(conn, {**make_cfg(tmp_path), **change}, source, root)
        after = fovs()
        changed = sum(1 for k in before if before[k] != after[k])
        assert 0 < changed < len(before)  # the world has crops on both sides of each limit
        assert source.calls == [] and counts["crops"] == changed and counts["crops_kept"] == len(before) - changed
        run_once(conn, make_cfg(tmp_path), FakeSource(world()), root)  # back to the defaults for the next change


def test_the_cap_ends_the_run_without_an_error(tmp_path):
    conn = make_db(3)
    counts, stop = run_once(conn, make_cfg(tmp_path, cap=1), FakeSource(world()), tmp_path / "c")
    assert stop.reason == "cap" and counts["stopped_reason"] == "cap" and counts["new_downloads"] == 1


def test_a_building_with_no_stored_buildings_is_reported(tmp_path):
    with pytest.raises(ValueError, match="register.py"):
        capture.Capture(db.connect(":memory:"), make_cfg(tmp_path), FakeSource({}), tmp_path / "c").run_cell(CELL)


# --- P3-8 file paths -----------------------------------------------------------------------------------------------------------------------------

@given(st.text(max_size=40))
def test_p3_8_names_are_safe_for_any_text(name):
    out = capture.safe_name(name)
    assert SAFE.fullmatch(out) and not out.startswith(".") and out not in (".", "..")


@given(st.text(max_size=30), st.text(max_size=30))
def test_p3_8_paths_stay_in_the_right_cell_folder_inside_the_captures_folder(building_id, pano_id):
    root = Path("/captures-root")
    pano_cell, building_cell = "8930e0af123ffff", "8930e0af13bffff"
    pano = capture.pano_file(pano_cell, pano_id)
    crop = capture.crop_file(building_cell, building_id, pano_id)
    assert pano.startswith(pano_cell + "/") and crop.startswith(building_cell + "/crops/")
    for rel in (pano, crop):
        assert all(SAFE.fullmatch(part) for part in rel.split("/"))
        assert capture._inside(root, rel).is_relative_to(root.resolve())


def test_p3_8_building_id_colon_becomes_an_underscore():
    assert capture.crop_file(CELL, "gis:11185213", "abc-_") == f"{CELL}/crops/gis_11185213__abc-_.jpg"
    assert capture._inside(Path("/r"), "x/../y.jpg").name == "y.jpg"
    with pytest.raises(ValueError):
        capture._inside(Path("/r"), "../outside.jpg")


def test_p3_8_stored_paths_point_to_files_in_the_matching_cell_folder(tmp_path):
    conn, root = make_db(3), tmp_path / "c"
    run_once(conn, make_cfg(tmp_path), FakeSource(world()), root)
    for c in db.all_captures(conn):
        if c["file_path"]:
            assert c["file_path"].startswith(c["cell_id"] + "/") and (root / c["file_path"]).is_file()
    for v in db.views_for_cell(conn, CELL):
        assert v["crop_path"].startswith(CELL + "/crops/") and (root / v["crop_path"]).is_file()
        with Image.open(root / v["crop_path"]) as img:
            assert img.size == (64, 48)


# --- adapter: classes of errors, retries, pacing, reply checks ---------------------------------------------------------------------------------


class HTTPStatus(Exception):
    def __init__(self, status):
        self.status = status


class ReadTimeout(Exception):
    pass


class JSONDecodeError(ValueError):
    pass


@pytest.mark.parametrize("exc, kind, retry", [
    (HTTPStatus(429), ps.BlockedError, True), (HTTPStatus(403), ps.BlockedError, True),
    (HTTPStatus(503), ps.TransientError, True), (ReadTimeout(), ps.TransientError, True),
    (TimeoutError(), ps.TransientError, True), (JSONDecodeError("<html>blocked</html>"), ps.BlockedError, False),
    (KeyError("features"), ps.BlockedError, False), (HTTPStatus(404), ps.SourceError, False),
    (RuntimeError("?"), ps.SourceError, False),
])
def test_classify(exc, kind, retry):
    error, retryable = ps.classify(exc)
    assert type(error) is kind and retryable is retry
    assert "://" not in str(error)  # messages carry the error name and status, never a URL


class Clock:
    def __init__(self):
        self.now, self.sleeps = 0.0, []

    def sleep(self, s):
        self.sleeps.append(s)
        self.now += s

    def __call__(self):
        return self.now


def pano(**kw):
    base = dict(id="p1", lat=BASE[0], lon=BASE[1], heading=0.5, is_latest=True, max_zoom=4, panorama_type=15,
                date=datetime(2026, 5, 27, 14, 28), neighbors=SimpleNamespace(street=[], other=[]))
    return SimpleNamespace(**{**base, **kw})


class Lib:
    def __init__(self, clock, by_id=None, nearby=None, strip=None):
        self.clock, self.starts = clock, []
        self._by_id, self._nearby, self._strip = by_id, nearby, strip

    def _run(self, fn, *args):
        self.starts.append(self.clock.now)
        self.clock.now += 0.1  # a call takes a moment
        result = fn(*args) if callable(fn) else fn
        if isinstance(result, Exception):
            raise result
        return result

    def by_id(self, pano_id):
        return self._run(self._by_id, pano_id)

    def nearby(self, lat, lon):
        return self._run(self._nearby, lat, lon)

    def strip(self, pano_id):
        return self._run(self._strip, pano_id)


def source_with(clock, **lib):
    return ps.PanoramaSource(pause_s=1, waits=[10, 30, 60], lib=Lib(clock, **lib), sleep=clock.sleep, clock=clock)


def test_a_persistent_429_is_retried_after_each_wait_and_then_reported_as_blocked():
    clock = Clock()
    src = source_with(clock, by_id=lambda i: (_ for _ in ()).throw(HTTPStatus(429)))
    with pytest.raises(ps.BlockedError):
        src.get_metadata("p1")
    assert len(src._lib.starts) == 4 and [s for s in clock.sleeps if s >= 10] == [10, 30, 60]


def test_a_timeout_that_clears_after_two_waits_succeeds():
    clock, outcomes = Clock(), [ReadTimeout(), ReadTimeout(), pano()]
    src = source_with(clock, by_id=lambda i: outcomes.pop(0))
    assert src.get_metadata("p1").pano_id == "p1" and [s for s in clock.sleeps if s >= 10] == [10, 30]


def test_a_reply_in_the_wrong_format_is_not_retried():
    clock = Clock()
    src = source_with(clock, by_id=JSONDecodeError("<html>"))
    with pytest.raises(ps.BlockedError):
        src.get_metadata("p1")
    assert len(src._lib.starts) == 1


def test_calls_are_spaced_by_at_least_the_pause():
    clock = Clock()
    src = source_with(clock, by_id=lambda i: pano(id=i))
    for _ in range(4):
        src.get_metadata("p1")
    starts = src._lib.starts
    assert all(b - a >= 1.0 - 1e-9 for a, b in zip(starts, starts[1:]))


def test_metadata_turns_the_heading_and_skips_what_cannot_be_used():
    clock = Clock()
    ok = source_with(clock, by_id=lambda i: pano(heading=0.17138868582424616)).get_metadata("p1")
    assert ok.heading_deg == pytest.approx(189.82, abs=0.01) and ok.captured_at == "2026-05-27T14:28:00" and ok.max_zoom == 4
    for bad in (None, pano(id="other"), pano(is_latest=False), pano(max_zoom=0), pano(max_zoom=None),
                pano(panorama_type=3), pano(heading=None)):
        assert source_with(Clock(), by_id=lambda i, b=bad: b).get_metadata("p1") is None


def test_nearby_drops_bad_replies_and_the_other_kinds():
    good = pano(id="a")
    far = pano(id="far", lat=BASE[0] + 0.02)  # more than 1 km away
    street = [pano(id="b", lat=BASE[0] + 0.0001), pano(id="a"), pano(id=""), far, pano(id="x", lat=95.0), pano(id="y", lon=None)]
    good.neighbors = SimpleNamespace(street=street, other=[pano(id="other-kind")])
    src = source_with(Clock(), nearby=good)
    assert [c.pano_id for c in src.find_nearby(*BASE)] == ["a", "b"] and src.rejected == 4
    assert source_with(Clock(), nearby=None).find_nearby(*BASE) == []


def test_download_checks_the_image_size_and_mode():
    assert source_with(Clock(), strip=Image.new("RGB", ps.STRIP_SIZE)).download_strip("p1").size == ps.STRIP_SIZE
    for bad in (Image.new("RGB", (6144, 512)), Image.new("L", ps.STRIP_SIZE), b"<html>"):
        with pytest.raises(ps.SourceError):
            source_with(Clock(), strip=bad).download_strip("p1")


def test_pillow_keeps_its_decompression_bomb_guard_with_an_explicit_limit():
    assert Image.MAX_IMAGE_PIXELS == ps.MAX_IMAGE_PIXELS == 8_000_000 and ps.STRIP_SIZE[0] * ps.STRIP_SIZE[1] < ps.MAX_IMAGE_PIXELS
