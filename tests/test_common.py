"""Secret masking, whitespace trimming, retry schedule, config validation and the CLI runner."""
from __future__ import annotations

import io
import json
import logging
import urllib.error

import pytest
from hypothesis import given, strategies as st

import common

KEY = "00000000-1111-2222-3333-444444444444"  # made-up value for tests, not a real key


@pytest.fixture(autouse=True)
def _clear_secrets():
    common._SECRETS.clear()
    yield
    common._SECRETS.clear()


# --- secrets -----------------------------------------------------------------------

def test_get_secret_trims_surrounding_whitespace():
    assert common.get_secret("K", {"K": f"  {KEY}\n"}) == KEY  # a leading space once broke the V-World key


def test_missing_or_blank_secret_names_the_variable_without_a_value():
    for env in ({}, {"K": ""}, {"K": "   "}):
        with pytest.raises(common.MissingSecretError) as err:
            common.get_secret("K", env)
        assert "K" in str(err.value)


@given(st.text(alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")), min_size=8, max_size=40))
def test_mask_hides_the_secret_and_key_parameters(secret):
    common._SECRETS.clear()
    common.get_secret("K", {"K": secret})
    text = f"GET https://x.test/req?key={secret}&a=1 failed for {secret}"
    masked = common.mask(text)
    assert secret not in masked
    assert "key=<KEY>" in masked and "a=1" in masked


def test_mask_hides_url_encoded_form_and_service_key():
    common.get_secret("K", {"K": "ab/cd+ef=="})
    masked = common.mask("https://x.test/?serviceKey=ab%2Fcd%2Bef%3D%3D&z=1 and ab/cd+ef==")
    assert "ab%2Fcd" not in masked and "ab/cd+ef" not in masked and "z=1" in masked


# --- logging -----------------------------------------------------------------------

def test_logging_writes_json_lines_and_a_readable_console_line_without_secrets(tmp_path):
    common.get_secret("K", {"K": KEY})
    stream = io.StringIO()
    common.setup_logging("demo", tmp_path, console_stream=stream)
    common.log(logging.INFO, f"fetched with key={KEY}", cell_id="8930e0af13bffff", count=3)
    for h in logging.getLogger("roblox_map").handlers:
        h.flush()
    [file] = list(tmp_path.glob("demo-*.jsonl"))
    entry = json.loads(file.read_text(encoding="utf-8").strip())
    assert entry["cell_id"] == "8930e0af13bffff" and entry["script"] == "demo" and entry["extra"] == {"count": 3}
    assert KEY not in file.read_text(encoding="utf-8") and KEY not in stream.getvalue()
    assert "INFO [8930e0af13bffff]" in stream.getvalue()
    assert "count=3" in stream.getvalue()  # counts show on the console, not only in the file


def test_setup_logging_twice_does_not_duplicate_handlers(tmp_path):
    common.setup_logging("demo", tmp_path, console_stream=io.StringIO())
    common.setup_logging("demo", tmp_path, console_stream=io.StringIO())
    assert len(logging.getLogger("roblox_map").handlers) == 2


# --- http_get_json -------------------------------------------------------------------

class _Resp:
    def __init__(self, body: bytes):
        self._body = body
    def read(self):
        return self._body
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


def _opener(script):
    """script: list of bytes (success) or exceptions, consumed one per call."""
    calls = []
    def opener(req, timeout=None):
        calls.append(req.full_url)
        item = script.pop(0)
        if isinstance(item, Exception):
            raise item
        return _Resp(item)
    opener.calls = calls
    return opener


def _http_error(code):
    return urllib.error.HTTPError("https://x.test", code, "err", {}, None)


def test_retries_429_and_502_with_the_configured_waits_then_succeeds():
    sleeps = []
    opener = _opener([_http_error(429), _http_error(502), b'{"ok": true}'])
    data = common.http_get_json("https://x.test/a", {"q": 1}, waits=[10, 30, 60], opener=opener, sleep=sleeps.append)
    assert data == {"ok": True} and sleeps == [10, 30] and len(opener.calls) == 3


def test_gives_up_after_the_last_wait():
    sleeps = []
    opener = _opener([_http_error(504)] * 4)
    with pytest.raises(common.HttpError) as err:
        common.http_get_json("https://x.test/a?key=SECRETVALUE1", waits=[10, 30, 60], opener=opener, sleep=sleeps.append)
    assert sleeps == [10, 30, 60] and err.value.status == 504 and "SECRETVALUE1" not in str(err.value)


@pytest.mark.parametrize("code", [400, 401, 403, 404, 500])
def test_other_http_errors_are_not_retried(code):
    sleeps = []
    with pytest.raises(common.HttpError):
        common.http_get_json("https://x.test/a", waits=[10], opener=_opener([_http_error(code)]), sleep=sleeps.append)
    assert sleeps == []


def test_timeouts_are_retried_but_other_url_errors_are_not():
    sleeps = []
    assert common.http_get_json("https://x.test/a", waits=[5], sleep=sleeps.append,
                                opener=_opener([TimeoutError(), b"[1]"])) == [1] and sleeps == [5]
    with pytest.raises(common.HttpError):
        common.http_get_json("https://x.test/a", waits=[5], sleep=sleeps.append,
                             opener=_opener([urllib.error.URLError(ConnectionRefusedError())]))


def test_pause_after_success_and_https_only_and_json_only():
    sleeps = []
    common.http_get_json("https://x.test/a", pause_s=1.5, opener=_opener([b"{}"]), sleep=sleeps.append)
    assert sleeps == [1.5]
    with pytest.raises(ValueError):
        common.http_get_json("http://x.test/a", opener=_opener([b"{}"]))
    with pytest.raises(ValueError):
        common.http_get_json("https://x.test/a", opener=_opener([b"not json"]))


# --- config --------------------------------------------------------------------------

def test_default_config_file_matches_the_defaults_in_code():
    cfg = common.load_config()
    assert cfg.pop("regions_dir") == "regions"  # DEFAULTS' value is moved out of the repository for tests (conftest)
    assert cfg == {k: v for k, v in common.DEFAULTS.items() if k != "regions_dir"}
    assert common.DEFAULTS["school_polygons"] == [] and common.DEFAULTS["spawn_lat"] is None  # region keys live in region.toml


def test_the_three_cells_get_the_first_region_keys():
    cfg = common.load_config()
    for cell in ("8930e0af13bffff", "8930e0af123ffff", "8930e0af12bffff"):
        c = common.cell_config(cfg, cell)
        assert c["region"] == "bucheon-dodang" and len(c["school_polygons"]) == 1 and c["road_lanes_by_name"]["길주로"] == 10
        assert c["spawn_lat"] is not None and common.cell_file(cfg, cell, "details").parts[-4:] == ("bucheon-dodang", "cells", cell, "details.json")


def _regions(tmp_path, *tables):
    for n, text in enumerate(tables):
        (tmp_path / f"r{n}").mkdir()
        (tmp_path / f"r{n}" / "region.toml").write_text(text, encoding="utf-8")
    return {**common.DEFAULTS, "regions_dir": str(tmp_path)}


def test_a_cell_must_be_in_exactly_one_region_and_region_keys_are_checked(tmp_path):
    cfg = _regions(tmp_path, 'cells = ["a"]\nspawn_lat = 37.5\nspawn_lon = 126.8\nspawn_yaw_deg = 90\n', 'cells = ["b", "c"]\n',
                   'cells = ["c"]\n', 'cells = ["d"]\nspawn_lat = 37.5\n', 'cells = ["e"]\nbuffer_m = 9\n',
                   'cells = ["f"]\n[road_lanes_by_name]\n"x" = 0\n')
    a = common.cell_config(cfg, "a")
    assert (a["spawn_lat"], a["spawn_lon"], a["spawn_yaw_deg"], a["region"]) == (37.5, 126.8, 90, "r0")
    assert common.cell_config(cfg, "b")["spawn_lat"] is None and common.cell_config(cfg, "b")["cell_dir"] == str(tmp_path / "r1" / "cells" / "b")
    for cell in ("c", "zz", "d", "e", "f"):  # two regions, none, unpaired spawn, a key that is not a region key, bad lanes
        with pytest.raises(ValueError):
            common.cell_config(cfg, cell)


def test_config_fills_missing_keys_and_rejects_bad_values(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text("buffer_m = 200\n", encoding="utf-8")
    assert common.load_config(p)["buffer_m"] == 200 and common.load_config(p)["h3_res"] == 9
    for bad in ("h3_res = 99", "overlap_threshold = 0", "vworld_page_size = 5000", "retry_waits_s = [-1]",
                "backup_keep = -1", 'db_path = ""', "mystery = 1",
                "pano_limit_m = 0", "pano_max_views = 2.5", "pano_max_views = true", "max_new_panos = 0",
                "crop_quality = 101", "fov_min_deg = 120", "pitch_max_deg = 90", "pano_pause_s = -1",
                'captures_dir = ""', "studs_per_m = 0", "chunk_size = 0", "chunk_size = 2.5", "poor_fit_ratio = 0",
                "sidewalk_width_m = 0", "origin_lat = 91", "ground_margin_m = -1", "spawn_lat = 37.5",
                "spawn_lon = 126.8", "spawn_lat = 95\nspawn_lon = 126.8", "[road_widths_m]\ntertiary = 0",
                '[road_widths_m]\ntertiary = "wide"',
                "floor_height_min_m = 6", "floor_height_min_m = 5\nfloor_height_max_m = 5", "review_batch_size = 0",
                "sheet_tile_w = 10", "sheet_jpeg_quality = 101", 'regions_dir = ""', "blind_broken = [1]", 'blind_broken = [""]',
                "pole_spacing_m = -1", "lamp_spacing_m = 201", "tree_spacing_m = 51", "car_spacing_m = -0.5", "school_zone_m = 301",
                "roof_pitch_deg = 4", 'window_faces = "side"', 'assets_dir = ""'):
        p.write_text(bad + "\n", encoding="utf-8")
        with pytest.raises(ValueError):
            common.load_config(p)


def test_a_partial_road_width_table_only_overrides_the_classes_it_names(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text("[road_widths_m]\ntertiary = 12\n", encoding="utf-8")
    widths = common.load_config(p)["road_widths_m"]
    assert widths["tertiary"] == 12 and widths["residential"] == common.DEFAULTS["road_widths_m"]["residential"]
    assert common.DEFAULTS["road_widths_m"]["tertiary"] == 10  # the shared defaults are never changed


def test_region_keys_are_refused_in_the_config_file(tmp_path):
    p = tmp_path / "c.toml"
    assert common.load_config(p)["spawn_lat"] is None
    for text in ("spawn_lat = 37.5044\nspawn_lon = 126.7794\n", "school_polygons = []\n", '[road_lanes_by_name]\n"x" = 2\n'):
        p.write_text(text, encoding="utf-8")
        with pytest.raises(ValueError, match="region.toml"):
            common.load_config(p)


def test_wall_color_table_is_merged_by_name_and_checked(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text("[wall_colors]\ncream = [1, 2, 3]\nmint = [150, 220, 190]\n", encoding="utf-8")
    colors = common.load_config(p)["wall_colors"]
    assert colors["cream"] == [1, 2, 3] and colors["mint"] == [150, 220, 190]
    assert colors["light_gray"] == common.DEFAULTS["wall_colors"]["light_gray"]
    assert common.DEFAULTS["wall_colors"]["cream"] == [236, 224, 190]  # the shared defaults are never changed
    for bad in ("white = [256, 0, 0]", "white = [1, 2]", 'white = "red"', "white = [1.5, 2, 3]", "Bad = [1, 2, 3]",
                "white = [true, 2, 3]", "bad-name = [1, 2, 3]"):
        p.write_text("[wall_colors]\n" + bad + "\n", encoding="utf-8")
        with pytest.raises(ValueError):
            common.load_config(p)


def test_building_height_follows_the_priority_vworld_floors_default():
    cfg = common.DEFAULTS
    assert common.building_height_m(12.5, 4, cfg) == 12.5
    assert common.building_height_m(None, 5, cfg) == 5 * cfg["floor_height_m"]
    assert common.building_height_m(0, 0, cfg) == cfg["default_height_m"]


def test_resolve_makes_relative_paths_relative_to_the_repository_root():
    assert common.resolve("data/map.db") == common.ROOT / "data" / "map.db"
    assert str(common.resolve("/somewhere/else")) == "/somewhere/else"


# --- run ------------------------------------------------------------------------------

def _cfg(tmp_path):
    return {**common.DEFAULTS, "log_dir": str(tmp_path)}


def test_run_returns_the_exit_code_and_catches_errors_with_masked_messages(tmp_path, capsys):
    common.get_secret("K", {"K": KEY})
    assert common.run(lambda cfg: None, "demo", _cfg(tmp_path)) == 0
    assert common.run(lambda cfg: 3, "demo", _cfg(tmp_path)) == 3

    def boom(cfg):
        raise RuntimeError(f"failed with key={KEY}")
    assert common.run(boom, "demo", _cfg(tmp_path)) == 1
    logged = "".join(f.read_text(encoding="utf-8") for f in tmp_path.glob("demo-*.jsonl"))
    assert "RuntimeError" in logged and KEY not in logged and KEY not in capsys.readouterr().err


def test_run_maps_ctrl_c_to_130_and_system_exit_to_its_code(tmp_path):
    def interrupted(cfg):
        raise KeyboardInterrupt
    def usage(cfg):
        raise SystemExit(2)
    assert common.run(interrupted, "demo", _cfg(tmp_path)) == 130
    assert common.run(usage, "demo", _cfg(tmp_path)) == 2


def test_run_reports_a_bad_config_without_crashing(monkeypatch, capsys):
    def broken():
        raise ValueError("config: h3_res must be an integer from 0 to 15")
    monkeypatch.setattr(common, "load_config", broken)
    assert common.run(lambda cfg: 0, "demo") == 1
    assert "startup error: ValueError: config: h3_res" in capsys.readouterr().err
