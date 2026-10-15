"""U4 pure functions: judgement and override validation, the final value of a building, review flags, the export file format.

No input or output. Rules: aidlc-docs/construction/u4-judgement-corrections/functional-design/business-rules.md
(BR-2.2, BR-3 to BR-7.1, BR-8.3, BR-8.5). Priority for every field: override > photo judgement > register > default.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

FIELDS = ("floors_above", "height_m", "wall_color", "roof_shape")  # what an override may change (Q7=A)
ROOF_SHAPES = ("flat", "gable", "hip", "shed", "other")
CONFIDENCES = ("high", "medium", "low")
FLAGS = ("conflict", "changed", "filled", "low_confidence", "default_height", "height_out_of_range", "osm_differs", "unjudged")
FLOORS_RANGE = (1, 100)
HEIGHT_RANGE = (2.0, 500.0)
DEFAULT_WALL = "light_gray"
DEFAULT_ROOF = "flat"
OTHER_COLOR = "other"  # a color that is not in the table: painted light_gray, the note says which
ID_RE = re.compile(r"[A-Za-z0-9:#_.\-]{1,100}")  # the characters U2 lets into Luau code and file names (N-U4-7)
CELL_RE = re.compile(r"[0-9a-f]{15}")
TIME_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\+00:00|Z)")
CONTROL = re.compile(r"[\x00-\x1f\x7f]")
NOTE_MAX, REASON_MAX = 300, 500
EXPORT_VERSION = 1
MAX_EXPORT_BYTES = 5_000_000
OVERRIDE_KEYS = ("building_id", "field", "value", "reason", "set_at")
ESTIMATE_KEYS = ("building_id", "floors_seen", "confidence", "height_est_m", "wall_color", "roof_shape", "views_used", "note", "judged_at")
JUDGEMENT_KEYS = ESTIMATE_KEYS[:-1]  # what a judgement carries before it gets a time


# --- validation (BR-2.2, BR-6.1, BR-6.2) ----------------------------------------------------------------

def _is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _is_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _colors(cfg: Mapping[str, Any]) -> set[str]:
    return set(cfg["wall_colors"]) | {OTHER_COLOR}


def _text(value: Any, label: str, limit: int, required: bool) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str) or (required and not value.strip()):
        raise ValueError(f"{label} must be {'non-empty ' if required else ''}text")
    if len(value) > limit or CONTROL.search(value):
        raise ValueError(f"{label} must be at most {limit} characters without control characters")
    return value.strip() if required else value


def is_building_id(value: Any) -> bool:
    return isinstance(value, str) and ID_RE.fullmatch(value) is not None


def validate_judgement(j: Mapping[str, Any], cfg: Mapping[str, Any], valid_ranks: set[int] | None) -> dict[str, Any]:
    """One judgement as it is stored. `valid_ranks` are the crop ranks the building has (None: any positive rank, for files)."""
    unknown = set(j) - set(JUDGEMENT_KEYS)
    if unknown:
        raise ValueError(f"unknown keys {sorted(unknown)}")
    bid = j.get("building_id")
    if not is_building_id(bid):
        raise ValueError(f"building_id is missing or has characters that are not allowed: {str(bid)[:40]!r}")
    try:
        floors, height, conf = j.get("floors_seen"), j.get("height_est_m"), j.get("confidence")
        if floors is not None and not (_is_int(floors) and FLOORS_RANGE[0] <= floors <= FLOORS_RANGE[1]):
            raise ValueError(f"floors_seen must be an integer from {FLOORS_RANGE[0]} to {FLOORS_RANGE[1]} or empty")
        if height is not None:
            if floors is not None:
                raise ValueError("height_est_m is only for buildings whose floors could not be counted")
            if not (_is_num(height) and HEIGHT_RANGE[0] <= height <= HEIGHT_RANGE[1]):
                raise ValueError(f"height_est_m must be a number from {HEIGHT_RANGE[0]} to {HEIGHT_RANGE[1]}")
        if conf is not None and conf not in CONFIDENCES:
            raise ValueError(f"confidence must be one of {CONFIDENCES}")
        if conf is None and (floors is not None or height is not None):
            raise ValueError("confidence is required when floors_seen or height_est_m is given")
        color, roof = j.get("wall_color"), j.get("roof_shape")
        if color is not None and color not in _colors(cfg):
            raise ValueError(f"wall_color {str(color)[:20]!r} is not in the color table")
        if roof is not None and roof not in ROOF_SHAPES:
            raise ValueError(f"roof_shape must be one of {ROOF_SHAPES}")
        ranks = j.get("views_used")
        if not (isinstance(ranks, list) and ranks and all(_is_int(r) and r >= 1 for r in ranks)):
            raise ValueError("views_used must be a non-empty list of crop ranks")
        if valid_ranks is not None and not set(ranks) <= valid_ranks:
            raise ValueError(f"views_used {sorted(set(ranks) - valid_ranks)} are not cropped views of this building")
        note = _text(j.get("note"), "note", NOTE_MAX, False)
    except ValueError as e:
        raise ValueError(f"{bid}: {e}") from None
    return {"building_id": bid, "floors_seen": floors, "confidence": conf, "height_est_m": None if height is None else float(height),
            "wall_color": color, "roof_shape": roof, "views_used": sorted(set(ranks)), "note": note}


def validate_override(field: str, value: Any, reason: Any, cfg: Mapping[str, Any]) -> tuple[Any, str]:
    """(normalized value, trimmed reason) of one override, or ValueError."""
    if field not in FIELDS:
        raise ValueError(f"field must be one of {FIELDS}")
    if field == "floors_above":
        if not (_is_int(value) and FLOORS_RANGE[0] <= value <= FLOORS_RANGE[1]):
            raise ValueError(f"floors_above must be an integer from {FLOORS_RANGE[0]} to {FLOORS_RANGE[1]}")
    elif field == "height_m":
        if not (_is_num(value) and HEIGHT_RANGE[0] <= value <= HEIGHT_RANGE[1]):
            raise ValueError(f"height_m must be a number from {HEIGHT_RANGE[0]} to {HEIGHT_RANGE[1]}")
        value = float(value)
    elif field == "wall_color":
        if value not in _colors(cfg):
            raise ValueError("wall_color is not in the color table")
    elif value not in ROOF_SHAPES:
        raise ValueError(f"roof_shape must be one of {ROOF_SHAPES}")
    return value, _text(reason, "reason", REASON_MAX, True)  # type: ignore[return-value]


# --- the final value of a building (BR-3 to BR-7.1) -----------------------------------------------------

@dataclass(frozen=True)
class EffectiveBuilding:
    building_id: str
    floors_above: int | None
    floors_basis: str | None  # override, register, photo_count
    floors_status: str  # override, verified, unverified, changed, conflict, filled, none, unjudged
    height_m: float
    height_basis: str  # override, register, from_floors, photo_geometry, default
    wall_color: str
    wall_basis: str  # override, photo, default
    roof_shape: str
    roof_basis: str
    flags: tuple[str, ...]
    register_floors: int | None  # reference values: they are shown, never merged
    register_height_m: float | None
    photo_floors: int | None
    photo_confidence: str | None
    osm_height_m: float | None
    osm_levels: int | None


def _positive(v: Any) -> Any:
    return v if _is_num(v) and v > 0 else None


def effective_building(building: Mapping[str, Any], estimate: Mapping[str, Any] | None,
                      overrides: Mapping[str, Any] | None, cfg: Mapping[str, Any]) -> EffectiveBuilding:
    ov = overrides or {}
    reg_f, reg_h = _positive(building.get("floors_above")), _positive(building.get("height_m"))
    reg_f = None if reg_f is None else int(reg_f)
    osm_h, osm_l = _positive(building.get("osm_height_m")), _positive(building.get("osm_levels"))
    photo_f = estimate.get("floors_seen") if estimate else None
    conf = estimate.get("confidence") if estimate else None
    flags: set[str] = set()

    # floors (BR-3)
    if "floors_above" in ov:
        floors, f_basis, status = ov["floors_above"], "override", "override"
    elif estimate is None:
        floors, f_basis, status = reg_f, "register" if reg_f else None, "unjudged"
    elif reg_f and photo_f:
        if photo_f == reg_f:
            floors, f_basis, status = reg_f, "register", "verified" if conf in ("high", "medium") else "unverified"
        elif conf == "high":
            floors, f_basis, status = photo_f, "photo_count", "changed"
            flags.add("changed")
        else:
            floors, f_basis, status = reg_f, "register", "conflict"
            flags.add("conflict")
    elif reg_f:
        floors, f_basis, status = reg_f, "register", "unverified"
    elif photo_f:
        floors, f_basis, status = photo_f, "photo_count", "filled"
        flags.add("filled")
        if conf == "low":
            flags.add("low_confidence")
    else:
        floors, f_basis, status = None, None, "none"
    if estimate is None:  # no photo judgement yet, even if the floors were overridden
        flags.add("unjudged")

    # height (BR-4)
    floor_h = float(cfg["floor_height_m"])
    if "height_m" in ov:
        height, h_basis = float(ov["height_m"]), "override"
    elif reg_h is not None and floors is not None and (reg_f is None or floors == reg_f):
        if cfg["floor_height_min_m"] <= reg_h / floors <= cfg["floor_height_max_m"]:
            height, h_basis = float(reg_h), "register"
        else:
            height, h_basis = floors * floor_h, "from_floors"
            flags.add("height_out_of_range")
    elif reg_h is not None and floors is not None and reg_f is not None and floors < reg_f and f_basis == "photo_count":
        # the photo counted fewer floors than the register: a tall shop or hall floor, or pilotis, read as one; the register's
        # measured height still stands (a 2-floor 8.8 m market hall came out 3.4 m and looked sunk, 1a3 2026-10-15)
        height, h_basis = float(reg_h), "register"
    elif reg_h is not None and floors is not None:
        height, h_basis = floors * floor_h, "from_floors"
    elif reg_h is not None:
        height, h_basis = float(reg_h), "register"
    elif floors is not None:
        height, h_basis = floors * floor_h, "from_floors"
    elif estimate and estimate.get("height_est_m"):
        height, h_basis = float(estimate["height_est_m"]), "photo_geometry"
        if conf == "low":
            flags.add("low_confidence")
    else:
        height, h_basis = float(cfg["default_height_m"]), "default"
        flags.add("default_height")
        if osm_h or osm_l:
            flags.add("osm_differs")

    # appearance (BR-5)
    def pick(field: str, default: str) -> tuple[str, str]:
        if field in ov:
            return ov[field], "override"
        if estimate and estimate.get(field):
            return estimate[field], "photo"
        return default, "default"

    wall, wall_basis = pick("wall_color", DEFAULT_WALL)
    roof, roof_basis = pick("roof_shape", DEFAULT_ROOF)
    return EffectiveBuilding(
        str(building["building_id"]), floors, f_basis, status, height, h_basis, wall, wall_basis, roof, roof_basis,
        tuple(f for f in FLAGS if f in flags), reg_f, None if reg_h is None else float(reg_h), photo_f, conf,
        None if osm_h is None else float(osm_h), None if osm_l is None else int(osm_l))


def wall_rgb(key: str, cfg: Mapping[str, Any]) -> tuple[int, int, int]:
    """RGB of a wall color name; `other` and unknown names are painted light_gray."""
    r, g, b = cfg["wall_colors"].get(key) or cfg["wall_colors"][DEFAULT_WALL]
    return int(r), int(g), int(b)


# --- the export file (BR-8.3, BR-8.5) ----------------------------------------------------------------------

def export_payload(cell_id: str, overrides: Sequence[Mapping[str, Any]], estimates: Sequence[Mapping[str, Any]]) -> str:
    """The text of an overrides.json: same rows, same text, whatever the order they come in."""
    data = {
        "version": EXPORT_VERSION, "cell_id": cell_id,
        "overrides": sorted(({k: o[k] for k in OVERRIDE_KEYS} for o in overrides), key=lambda o: (o["building_id"], o["field"])),
        "estimates": sorted(({k: e[k] for k in ESTIMATE_KEYS} for e in estimates), key=lambda e: e["building_id"]),
    }
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _row(row: Any, keys: Sequence[str], what: str) -> dict[str, Any]:
    if not isinstance(row, dict) or set(row) != set(keys):
        raise ValueError(f"{what}: each row needs exactly the keys {list(keys)}")
    if not is_building_id(row["building_id"]):
        raise ValueError(f"{what}: bad building_id {str(row['building_id'])[:40]!r}")
    if not (isinstance(row[keys[-1]], str) and TIME_RE.fullmatch(row[keys[-1]])):
        raise ValueError(f"{what} {row['building_id']}: bad time {str(row[keys[-1]])[:30]!r}")
    return row


def parse_export(text: str, cfg: Mapping[str, Any]) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    """(cell id, overrides, estimates) of an export file, every row checked; any problem is a ValueError and nothing is used."""
    if len(text.encode("utf-8")) > MAX_EXPORT_BYTES:
        raise ValueError("export file is too large")
    try:
        data = json.loads(text)
    except ValueError as e:
        raise ValueError(f"export file is not valid JSON: {e}") from None
    if not isinstance(data, dict) or set(data) != {"version", "cell_id", "overrides", "estimates"}:
        raise ValueError("export file needs exactly version, cell_id, overrides, estimates")
    if data["version"] != EXPORT_VERSION:
        raise ValueError(f"unknown export version {data['version']!r}")
    cell_id = data["cell_id"]
    if not (isinstance(cell_id, str) and CELL_RE.fullmatch(cell_id)):
        raise ValueError("cell_id is not an H3 cell id")
    if not (isinstance(data["overrides"], list) and isinstance(data["estimates"], list)):
        raise ValueError("overrides and estimates must be lists")
    overrides, seen = [], set()
    for raw in data["overrides"]:
        row = _row(raw, OVERRIDE_KEYS, "override")
        value, reason = validate_override(row["field"], row["value"], row["reason"], cfg)
        key = (row["building_id"], row["field"])
        if key in seen:
            raise ValueError(f"override {key} appears twice")
        seen.add(key)
        overrides.append({**row, "value": value, "reason": reason})
    estimates, seen_ids = [], set()
    for raw in data["estimates"]:
        row = _row(raw, ESTIMATE_KEYS, "estimate")
        j = validate_judgement({k: row[k] for k in JUDGEMENT_KEYS}, cfg, None)
        if j["building_id"] in seen_ids:
            raise ValueError(f"estimate {j['building_id']} appears twice")
        seen_ids.add(j["building_id"])
        estimates.append({**j, "judged_at": row["judged_at"]})
    return cell_id, overrides, estimates
