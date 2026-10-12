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
    cfg = dict(common.load_config())
    assert cfg.pop("school_polygons")  # the file holds this project's school parcel; the code default is empty
    assert cfg == {k: v for k, v in common.DEFAULTS.items() if k != "school_polygons"}
    assert common.DEFAULTS["school_polygons"] == []


def test_config_fills_missing_keys_and_rejects_bad_values(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text("buffer_m = 200\n", encoding="utf-8")
    assert common.load_config(p)["buffer_m"] == 200 and common.load_config(p)["h3_res"] == 9
    for bad in ("h3_res = 99", "overlap_threshold = 0", "vworld_page_size = 5000", "retry_waits_s = [-1]",
                "backup_keep = -1", 'db_path = ""', "mystery = 1",
                "pano_limit_m = 0", "pano_max_views = 2.5", "pano_max_views = true", "max_new_panos = 0",
                "crop_quality = 101", "fov_min_deg = 120", "pitch_max_deg = 90", "pano_pause_s = -1",
                'captures_dir = ""'):
        p.write_text(bad + "\n", encoding="utf-8")
        with pytest.raises(ValueError):
            common.load_config(p)


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
