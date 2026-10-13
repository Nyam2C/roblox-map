"""Shared infrastructure for the U1 and U3 scripts: config, secrets, logging, retrying HTTP GET, CLI runner.

Standard library only. Design: aidlc-docs/construction/u1-data-foundation/nfr-design/
"""
from __future__ import annotations

import json
import logging
import os
import re
import socket
import sys
import time
import tomllib
import traceback
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

ROOT = Path(__file__).resolve().parent.parent

DEFAULTS: dict[str, Any] = {
    "h3_res": 9,
    "overlap_threshold": 0.5,
    "buffer_m": 150,
    "overpass_pause_s": 1,
    "vworld_pause_s": 0.5,
    "vworld_page_size": 1000,
    "retry_waits_s": [10, 30, 60],
    "regions_dir": "regions",  # U7: regions/<region>/region.toml and cells/<cell>/{details,overrides,signs,trees}.json
    "db_path": "data/map.db",
    "log_dir": "data/logs",
    "backup_dir": "data/backups",
    "backup_keep": 5,
    # U3 street-view capture
    "captures_dir": "captures",
    "pano_limit_m": 120,
    "pano_separation_deg": 60,
    "pano_max_views": 3,
    "pano_pause_s": 1,
    "max_new_panos": 100,
    "crop_width": 1024,
    "crop_height": 768,
    "crop_quality": 85,
    "fov_min_deg": 60,
    "fov_max_deg": 100,
    "pitch_max_deg": 40,
    "camera_height_m": 2.5,
    "floor_height_m": 3.4,
    "default_height_m": 10,
    "school_polygons": [],  # region.toml
    "school_max_views": 6,
    "school_face_min_m": 8,
    "school_face_max_deg": 60,
    # U2 Studio builder
    "origin_lat": 37.504169,  # the vertex shared by the three target cells = Studio (0, 0, 0)
    "origin_lon": 126.779628,
    "studs_per_m": 3.6,
    "poor_fit_ratio": 0.8,
    "ground_margin_m": 20,
    "sidewalk_width_m": 1.5,
    "lane_width_m": 3.25,  # an OSM lanes tag (or road_lanes_by_name) sets the width to lanes x this
    "road_lanes_by_name": {},  # region.toml: both directions; a oneway=yes carriageway gets half (satellite, 2026-10-13)
    "road_widths_m": {
        "motorway": 14, "trunk": 14, "primary": 12, "secondary": 11, "tertiary": 10, "unclassified": 6,
        "residential": 6, "service": 4, "living_street": 5, "road": 6, "link": 6,
        "pedestrian": 2.5, "footway": 2, "path": 2, "cycleway": 2, "steps": 2, "corridor": 2, "bridleway": 2,
        "track": 3,
    },
    "chunk_size": 70,  # U5: about 11 KB per call with the detail items (U5 BR-14.6; 80 crossed the 15 KB line on building-heavy chunks)
    "spawn_lat": None,  # region.toml; unset = no spawn is built (decided together in Studio)
    "spawn_lon": None,
    "spawn_yaw_deg": 0,
    # U4 judgement and corrections
    "floor_height_min_m": 2.5,  # a register height counts only inside this band per floor (BR-4.1)
    "floor_height_max_m": 5.0,
    "review_batch_size": 12,
    "sheet_tile_w": 512,
    "sheet_tile_h": 384,
    "sheet_jpeg_quality": 85,
    "blind_broken": ["gis:11081057"],  # buildings whose photo and height were seen before judging; left out of the agreement rate
    "wall_colors": {
        "white": [236, 236, 232], "cream": [236, 224, 190], "beige": [214, 192, 156], "yellow": [232, 205, 110],
        "orange": [214, 140, 80], "red_brick": [170, 90, 70], "brown": [125, 92, 70], "pink": [225, 170, 170],
        "light_gray": [200, 200, 205], "dark_gray": [110, 112, 118], "green": [120, 150, 110], "blue": [110, 140, 180],
    },
    # U5 details (BR-14.9): the frame-rate knobs and the roof pitch; building dimensions are constants in details_rules.DIMS
    "pole_spacing_m": 30,
    "lamp_spacing_m": 30,
    "tree_spacing_m": 7,
    "car_spacing_m": 0,
    "school_zone_m": 50,
    "roof_pitch_deg": 25,
    "window_faces": "all",  # "front": windows only on the road-facing face (first step of the FPS ladder)
    "interiors": False,  # U7 BR-I1: hollow buildings with floors, stairs and rooms (config.toml turns it on; off = the U5 map)
    "assets_dir": "assets/signs", "sign_image_model": "gpt-image-2.5-sunburst",
    "sign_image_size": "1536x1024", "sign_image_workers": 4,
}

# U3 and U2 key -> (min, max, must be an integer)
RANGES: dict[str, tuple[float, float, bool]] = {
    "pano_limit_m": (1, 1000, False), "pano_separation_deg": (0, 180, False), "pano_max_views": (1, 6, True),
    "max_new_panos": (1, 10_000, True), "crop_width": (64, 4096, True), "crop_height": (64, 4096, True),
    "crop_quality": (1, 100, True), "fov_min_deg": (1, 179, False), "fov_max_deg": (1, 179, False),
    "pitch_max_deg": (0, 89, False), "camera_height_m": (0, 100, False), "floor_height_m": (0.5, 20, False),
    "default_height_m": (0.5, 500, False), "school_max_views": (1, 12, True), "school_face_min_m": (1, 100, False),
    "school_face_max_deg": (5, 89, False),
    "origin_lat": (-90, 90, False), "origin_lon": (-180, 180, False), "studs_per_m": (0.1, 100, False),
    "poor_fit_ratio": (0.01, 1, False), "sign_image_workers": (1, 16, True), "ground_margin_m": (0, 500, False), "sidewalk_width_m": (0.5, 10, False),
    "chunk_size": (1, 1000, True), "spawn_yaw_deg": (-360, 360, False),
    "floor_height_min_m": (0.5, 20, False), "floor_height_max_m": (0.5, 50, False), "review_batch_size": (1, 100, True),
    "sheet_tile_w": (64, 2048, True), "sheet_tile_h": (64, 2048, True), "sheet_jpeg_quality": (1, 100, True),
    "pole_spacing_m": (0, 200, False), "lamp_spacing_m": (0, 200, False), "tree_spacing_m": (0, 50, False),
    "car_spacing_m": (0, 50, False), "school_zone_m": (0, 300, False), "roof_pitch_deg": (5, 60, False),
}

# U7 B: keys that belong to one region (regions/<region>/region.toml), not to config.toml
REGION_KEYS = ("school_polygons", "spawn_lat", "spawn_lon", "spawn_yaw_deg", "road_lanes_by_name")

RETRY_CODES = {429, 502, 504}
MASK = "<KEY>"


# --- config ------------------------------------------------------------------------

def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """Read config.toml, fill missing keys with DEFAULTS and check types and ranges."""
    cfg = dict(DEFAULTS)
    p = Path(path) if path is not None else ROOT / "config.toml"
    if p.exists():
        with p.open("rb") as f:
            data = tomllib.load(f)
        unknown = sorted(set(data) - set(DEFAULTS))
        if unknown:
            raise ValueError(f"config: unknown keys {unknown}")
        misplaced = sorted(set(data) & set(REGION_KEYS))
        if misplaced:
            raise ValueError(f"config: {misplaced} belong in regions/<region>/region.toml")
        cfg.update(data)
        if isinstance(data.get("road_widths_m"), dict):  # a partial table only overrides the classes it names
            cfg["road_widths_m"] = {**DEFAULTS["road_widths_m"], **data["road_widths_m"]}
        if isinstance(data.get("wall_colors"), dict):  # same for the color table
            cfg["wall_colors"] = {**DEFAULTS["wall_colors"], **data["wall_colors"]}
    check_config(cfg)
    return cfg


def check_config(cfg: Mapping[str, Any]) -> None:
    """Types and ranges of a whole config (config.toml merged with DEFAULTS, and with a region's keys by cell_config)."""
    errors = []
    if not (isinstance(cfg["h3_res"], int) and not isinstance(cfg["h3_res"], bool) and 0 <= cfg["h3_res"] <= 15):
        errors.append("h3_res must be an integer from 0 to 15")
    if not (_is_number(cfg["overlap_threshold"]) and 0 < cfg["overlap_threshold"] <= 1):
        errors.append("overlap_threshold must be in (0, 1]")
    if not (_is_number(cfg["buffer_m"]) and 0 < cfg["buffer_m"] <= 2000):
        errors.append("buffer_m must be in (0, 2000]")
    for k in ("overpass_pause_s", "vworld_pause_s", "pano_pause_s"):
        if not (_is_number(cfg[k]) and cfg[k] >= 0):
            errors.append(f"{k} must be a number >= 0")
    size = cfg["vworld_page_size"]
    if not (isinstance(size, int) and not isinstance(size, bool) and 1 <= size <= 1000):
        errors.append("vworld_page_size must be an integer from 1 to 1000")
    waits = cfg["retry_waits_s"]
    if not (isinstance(waits, list) and all(_is_number(w) and w >= 0 for w in waits)):
        errors.append("retry_waits_s must be a list of numbers >= 0")
    for k in ("db_path", "log_dir", "backup_dir", "captures_dir", "regions_dir", "assets_dir", "sign_image_model", "sign_image_size"):
        if not (isinstance(cfg[k], str) and cfg[k].strip()):
            errors.append(f"{k} must be a non-empty string")
    keep = cfg["backup_keep"]
    if not (isinstance(keep, int) and not isinstance(keep, bool) and keep >= 0):
        errors.append("backup_keep must be an integer >= 0")
    for k, (lo, hi, integer) in RANGES.items():
        v = cfg[k]
        ok = (isinstance(v, int) and not isinstance(v, bool)) if integer else _is_number(v)
        if not (ok and lo <= v <= hi):
            errors.append(f"{k} must be {'an integer' if integer else 'a number'} from {lo} to {hi}")
    polys = cfg["school_polygons"]
    if not (isinstance(polys, list) and all(
            isinstance(poly, list) and len(poly) >= 3 and all(
                isinstance(p, list) and len(p) == 2 and all(_is_number(x) for x in p)
                and -90 <= p[0] <= 90 and -180 <= p[1] <= 180 for p in poly) for poly in polys)):
        errors.append("school_polygons must be a list of polygons, each with at least 3 [lat, lon] points")
    if not errors and cfg["fov_min_deg"] > cfg["fov_max_deg"]:
        errors.append("fov_min_deg must not exceed fov_max_deg")
    if not errors and cfg["floor_height_min_m"] >= cfg["floor_height_max_m"]:
        errors.append("floor_height_min_m must be below floor_height_max_m")
    if not isinstance(cfg["interiors"], bool):
        errors.append("interiors must be true or false")
    if cfg["window_faces"] not in ("all", "front"):
        errors.append('window_faces must be "all" or "front"')
    broken = cfg["blind_broken"]
    if not (isinstance(broken, list) and all(isinstance(b, str) and b.strip() for b in broken)):
        errors.append("blind_broken must be a list of building ids")
    colors = cfg["wall_colors"]
    if not (isinstance(colors, dict) and "light_gray" in colors and all(
            isinstance(k, str) and re.fullmatch(r"[a-z_]{1,20}", k) and isinstance(v, list) and len(v) == 3
            and all(isinstance(c, int) and not isinstance(c, bool) and 0 <= c <= 255 for c in v) for k, v in colors.items())):
        errors.append("wall_colors must be a table of [r, g, b] (0 to 255) with lowercase names and a light_gray entry")
    widths = cfg["road_widths_m"]
    if not (isinstance(widths, dict) and all(isinstance(k, str) and _is_number(v) and 0.5 <= v <= 50 for k, v in widths.items())):
        errors.append("road_widths_m must be a table of numbers from 0.5 to 50")
    lat, lon = cfg["spawn_lat"], cfg["spawn_lon"]
    if (lat is None) != (lon is None):
        errors.append("spawn_lat and spawn_lon must be set together")
    elif lat is not None and not (_is_number(lat) and _is_number(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
        errors.append("spawn_lat and spawn_lon must be a latitude and a longitude")
    lanes = cfg["road_lanes_by_name"]
    if not (isinstance(lanes, dict) and all(isinstance(k, str) and _is_number(v) and 1 <= v <= 20 for k, v in lanes.items())):
        errors.append("road_lanes_by_name must be a table of lane counts from 1 to 20")
    if errors:
        raise ValueError("config: " + "; ".join(errors))


def region_of(cfg: Mapping[str, Any], cell_id: str) -> tuple[Path, dict[str, Any]]:
    """The folder and the region.toml table of the one region whose `cells` list holds this cell."""
    hits = []
    for p in sorted(resolve(cfg["regions_dir"]).glob("*/region.toml")):
        with p.open("rb") as f:
            data = tomllib.load(f)
        if cell_id in data.get("cells", []):
            hits.append((p.parent, data))
    if len(hits) != 1:
        raise ValueError(f"{cell_id} is in {len(hits)} regions: add it to the cells list of exactly one {cfg['regions_dir']}/<region>/region.toml")
    return hits[0]


def cell_config(cfg: Mapping[str, Any], cell_id: str) -> dict[str, Any]:
    """cfg with the cell's region keys (school parcels, spawn, lanes by road name) and `region`, `cell_dir` set."""
    folder, data = region_of(cfg, cell_id)
    unknown = sorted(set(data) - {"name", "cells", *REGION_KEYS})
    if unknown:
        raise ValueError(f"{folder.name}/region.toml: unknown keys {unknown}")
    out = {**cfg, **{k: data[k] for k in REGION_KEYS if k in data}, "region": folder.name, "cell_dir": str(folder / "cells" / cell_id)}
    check_config(out)
    return out


def cell_file(cfg: Mapping[str, Any], cell_id: str, kind: str) -> Path:
    """regions/<region>/cells/<cell>/<kind>.json, kind = details | overrides | signs | trees (kept in git)."""
    return Path(cell_config(cfg, cell_id)["cell_dir"]) / f"{kind}.json"


def building_height_m(height_m: float | None, floors_above: int | None, cfg: Mapping[str, Any]) -> float:
    """Building height in meters: V-World height, else floors x floor height, else the default (U3 BR-4.3, U2 BR-2.4)."""
    if height_m and height_m > 0:
        return float(height_m)
    if floors_above and floors_above > 0:
        return floors_above * float(cfg["floor_height_m"])
    return float(cfg["default_height_m"])


def resolve(path: str | Path) -> Path:
    """Relative paths in the config are relative to the repository root."""
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


# --- secrets and masking ------------------------------------------------------------

class MissingSecretError(RuntimeError):
    pass


_SECRETS: set[str] = set()
_KEY_PARAM = re.compile(r"(?i)\b(key|servicekey|apikey)=[^&\s\"']+")


def get_secret(name: str, environ: Mapping[str, str] | None = None) -> str:
    """Read a secret from the environment, trimming surrounding whitespace (BR-7.5)."""
    env = os.environ if environ is None else environ
    value = (env.get(name) or "").strip()
    if not value:
        raise MissingSecretError(f"environment variable {name} is not set (see .env.example)")
    _SECRETS.add(value)
    _SECRETS.add(urllib.parse.quote(value, safe=""))
    return value


def mask(text: str) -> str:
    """Hide known secret values and key= query values."""
    for secret in sorted(_SECRETS, key=len, reverse=True):
        text = text.replace(secret, MASK)
    return _KEY_PARAM.sub(lambda m: m.group(0).split("=", 1)[0] + "=" + MASK, text)


# --- logging ------------------------------------------------------------------------

class _JsonFormatter(logging.Formatter):
    def __init__(self, script: str) -> None:
        super().__init__()
        self.script = script

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="seconds"),
            "level": record.levelname,
            "script": self.script,
            "cell_id": getattr(record, "cell_id", None),
            "msg": record.getMessage(),
        }
        extra = getattr(record, "fields", None)
        if extra:
            entry["extra"] = extra
        if record.exc_info:
            entry["traceback"] = "".join(traceback.format_exception(*record.exc_info))
        return mask(json.dumps(entry, ensure_ascii=False, default=str))


class _ConsoleFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        t = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
        cell = getattr(record, "cell_id", None)
        where = f" [{cell}]" if cell else ""
        fields = getattr(record, "fields", None)
        tail = " " + " ".join(f"{k}={v}" for k, v in fields.items()) if fields else ""
        return mask(f"{t} {record.levelname}{where} {record.getMessage()}{tail}")


def setup_logging(script: str, log_dir: str | Path, console_stream: Any = None) -> logging.Logger:
    """JSON lines in log_dir/<script>-<date>.jsonl, a readable summary on the console. Idempotent."""
    logger = logging.getLogger("roblox_map")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    for h in list(logger.handlers):
        logger.removeHandler(h)
        h.close()
    d = Path(log_dir)
    d.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(d / f"{script}-{datetime.now().strftime('%Y%m%d')}.jsonl", encoding="utf-8")
    file_handler.setFormatter(_JsonFormatter(script))
    console = logging.StreamHandler(console_stream or sys.stderr)
    console.setFormatter(_ConsoleFormatter())
    logger.addHandler(file_handler)
    logger.addHandler(console)
    return logger


def log(level: int, msg: str, cell_id: str | None = None, **fields: Any) -> None:
    logging.getLogger("roblox_map").log(level, msg, extra={"cell_id": cell_id, "fields": fields or None})


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --- HTTP ---------------------------------------------------------------------------

class HttpError(RuntimeError):
    def __init__(self, status: int | None, message: str) -> None:
        super().__init__(message)
        self.status = status


def http_get_json(url: str, params: Mapping[str, Any] | None = None, *,
                  waits: list[float] | None = None, pause_s: float = 0.0, timeout: float = 90.0,
                  headers: Mapping[str, str] | None = None,
                  opener: Callable[..., Any] = urllib.request.urlopen,
                  sleep: Callable[[float], None] = time.sleep) -> Any:
    """GET a JSON document over HTTPS.

    Retries 429/502/504 and timeouts after each wait in `waits` (BR-7.3), nothing else.
    Certificate verification is never disabled. Errors never contain the key (BR-7.5).
    """
    full = url + ("?" + urllib.parse.urlencode(params) if params else "")
    if not full.lower().startswith("https://"):
        raise ValueError("only https:// URLs are allowed")
    schedule: list[float | None] = list(DEFAULTS["retry_waits_s"] if waits is None else waits) + [None]
    request_headers = {"User-Agent": "roblox-map/0", **(headers or {})}
    body: bytes | None = None
    for wait in schedule:
        try:
            req = urllib.request.Request(full, headers=request_headers)
            with opener(req, timeout=timeout) as resp:
                body = resp.read()
            break
        except urllib.error.HTTPError as e:
            if e.code not in RETRY_CODES or wait is None:
                raise HttpError(e.code, mask(f"HTTP {e.code} from {full}")) from None
            log(logging.WARNING, f"HTTP {e.code}, retrying in {wait}s")
        except (TimeoutError, socket.timeout) as e:
            if wait is None:
                raise HttpError(None, mask(f"timeout from {full}")) from None
            log(logging.WARNING, f"timeout, retrying in {wait}s")
        except urllib.error.URLError as e:
            if isinstance(e.reason, (TimeoutError, socket.timeout)) and wait is not None:
                log(logging.WARNING, f"timeout, retrying in {wait}s")
            else:
                raise HttpError(None, mask(f"request failed ({type(e.reason).__name__}) for {full}")) from None
        sleep(wait)  # only reached when a retry follows
    if pause_s:
        sleep(pause_s)
    try:
        return json.loads(body.decode("utf-8"))  # JSON only, never pickle or eval (SECURITY-13)
    except (UnicodeDecodeError, ValueError):
        raise ValueError(mask(f"response from {full} is not valid JSON")) from None


# --- CLI runner ---------------------------------------------------------------------

def run(main: Callable[[dict[str, Any]], int | None], script: str, cfg: dict[str, Any] | None = None) -> int:
    """Run main(cfg) with logging and a top-level error handler. Returns the exit code.

    Unhandled errors are logged with secrets masked and end with code 1; Ctrl-C ends with 130.
    """
    try:
        cfg = cfg or load_config()
        setup_logging(script, resolve(cfg["log_dir"]))
    except Exception as e:  # config or log directory problems: nothing to log to yet
        print(mask(f"startup error: {type(e).__name__}: {e}"), file=sys.stderr)
        return 1
    try:
        return int(main(cfg) or 0)
    except KeyboardInterrupt:
        log(logging.WARNING, "interrupted")
        return 130
    except SystemExit as e:  # argparse usage errors and explicit exits
        return e.code if isinstance(e.code, int) else 1
    except Exception as e:
        logging.getLogger("roblox_map").error(f"{type(e).__name__}: {e}", exc_info=True)
        return 1


def run_cli(main: Callable[[dict[str, Any]], int | None], script: str) -> None:
    sys.exit(run(main, script))
