"""U4 pure functions: the blind view of a building, the order to judge and to review, Studio camera values, agreement statistics.

No input or output. Rules: aidlc-docs/construction/u4-judgement-corrections/functional-design/business-rules.md
(BR-1 blind judgement, BR-7.2 to BR-7.4 review batches and camera, S4-2 agreement).
"""
from __future__ import annotations

import math
from typing import Any, Iterable, Mapping, Sequence

import layout

# BR-1.3: what the judge must not see before judging. Nothing built here ever carries these.
HIDDEN_FIELDS = ("floors_above", "floors_below", "height_m", "osm_height_m", "osm_levels", "usability_code", "building_area")
COMPASS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
ASPECT = 4 / 3  # crops are 1024 x 768
STUDIO_FOV_H_DEG = 100.0  # the widest crop; Studio is set to the matching vertical angle once and narrower crops are cut from it (N-U4-4)
LOOK_DISTANCE = 100.0  # studs from the camera to the point it looks at


# --- bearings and angles (BR-7.4) ---------------------------------------------------------------------

def camera_bearing(heading_deg: float, yaw_deg: float) -> float:
    """Compass direction a crop looks at: the panorama's front heading plus the crop's yaw, in [0, 360)."""
    b = (heading_deg + yaw_deg) % 360.0
    return 0.0 if b >= 360.0 else b


def compass(bearing_deg: float) -> str:
    return COMPASS[int(((bearing_deg % 360.0) + 22.5) // 45.0) % 8]


def h_to_v_fov(h_deg: float, aspect: float = ASPECT) -> float:
    """Vertical field of view for a horizontal one on an image of this width/height ratio."""
    return math.degrees(2 * math.atan(math.tan(math.radians(h_deg) / 2) / aspect))


def v_to_h_fov(v_deg: float, aspect: float = ASPECT) -> float:
    return math.degrees(2 * math.atan(math.tan(math.radians(v_deg) / 2) * aspect))


STUDIO_FOV_V_DEG = h_to_v_fov(STUDIO_FOV_H_DEG)  # 83.58


def direction(bearing_deg: float, pitch_deg: float) -> tuple[float, float, float]:
    """Unit vector in Studio axes (east +X, up +Y, north -Z) for a compass bearing and an upward angle."""
    t, p = math.radians(bearing_deg), math.radians(pitch_deg)
    return math.sin(t) * math.cos(p), math.sin(p), -math.cos(t) * math.cos(p)


def camera_for_view(frame: layout.Frame, pano_lat: float, pano_lon: float, heading_deg: float, yaw_deg: float,
                    pitch_deg: float, camera_height_m: float) -> dict[str, Any]:
    """Studio camera position and look-at point (studs) that repeat a street-view crop."""
    bearing = camera_bearing(heading_deg, yaw_deg)
    x, z = layout.to_studs(frame, pano_lat, pano_lon)
    y = camera_height_m * frame.studs_per_m
    dx, dy, dz = direction(bearing, pitch_deg)
    return {"position": [layout.fmt(x), layout.fmt(y), layout.fmt(z)],
            "look_at": [layout.fmt(x + LOOK_DISTANCE * dx), layout.fmt(y + LOOK_DISTANCE * dy), layout.fmt(z + LOOK_DISTANCE * dz)],
            "bearing_deg": layout.fmt(bearing)}


def capture_crop_box(width: int, height: int, fov_h_deg: float) -> tuple[int, int, int, int]:
    """(left, top, right, bottom) of the part of a Studio capture that matches a crop with this horizontal field of view.

    The capture shows the Studio vertical angle on a window that is at least 4:3. The middle 4:3 part has the widest crop's
    horizontal angle; a narrower crop is a smaller middle part of that (N-U4-4).
    """
    if width < round(height * ASPECT) - 1 or height < 1:
        raise ValueError(f"capture {width}x{height} is narrower than 4:3: make the Studio window wider")
    factor = min(1.0, math.tan(math.radians(fov_h_deg) / 2) / math.tan(math.radians(STUDIO_FOV_H_DEG) / 2))
    w43 = min(width, round(height * ASPECT))
    cw, ch = max(1, round(w43 * factor)), max(1, round(height * factor))
    left, top = round((width - cw) / 2), round((height - ch) / 2)
    return left, top, left + cw, top + ch


# --- the blind view (BR-1.3) --------------------------------------------------------------------------

def blind_item(building: Mapping[str, Any], views: Sequence[Mapping[str, Any]], frame: layout.Frame) -> dict[str, Any]:
    """What the judge may know about one building: id, name, place, size of the box around it, and which way each crop looks.

    `views` are cropped building_views rows joined with their panorama (rank, heading_deg, yaw_deg). Nothing else is copied.
    """
    box = layout.outline_to_box([(p[0], p[1]) for p in building["outline"]], frame)
    lat, lon = building["centroid"]
    return {
        "building_id": str(building["building_id"]),
        "name": building.get("name") or "",
        "lat": round(float(lat), 6), "lon": round(float(lon), 6),
        "box_m": [round(box.width_m, 1), round(box.depth_m, 1)] if box else [0.0, 0.0],
        "views": [{"rank": int(v["rank"]), "facing": compass(camera_bearing(float(v["heading_deg"]), float(v["yaw_deg"])))}
                  for v in sorted(views, key=lambda v: int(v["rank"]))],
    }


def _has_register_data(building: Mapping[str, Any]) -> bool:
    return any(isinstance(building.get(k), (int, float)) and not isinstance(building.get(k), bool) and building[k] > 0
               for k in ("floors_above", "height_m"))


def pending_order(buildings: Iterable[Mapping[str, Any]], school_ids: set[str]) -> list[str]:
    """Building ids in the order to judge them (BR-1.2): no register floors or height, then school buildings, then the rest."""
    def key(b: Mapping[str, Any]) -> tuple[int, str]:
        bid = str(b["building_id"])
        return (0 if not _has_register_data(b) else 1 if bid in school_ids else 2), bid
    return [str(b["building_id"]) for b in sorted(buildings, key=key)]


def review_batches(effective: Iterable[Any], school_ids: set[str], size: int) -> list[list[str]]:
    """Building ids in review batches of at most `size` (BR-7.2): flagged first, then school buildings, then the rest."""
    if size < 1:
        raise ValueError("batch size must be at least 1")
    def key(e: Any) -> tuple[int, str]:
        return (0 if e.flags else 1 if e.building_id in school_ids else 2), e.building_id
    ids = [e.building_id for e in sorted(effective, key=key)]
    return [ids[i:i + size] for i in range(0, len(ids), size)]


# --- how well the photos agree with the register (S4-2, P4-15) --------------------------------------------------

def agreement(rows: Iterable[tuple[str, int | None, int | None, str | None]], broken_ids: Iterable[str]) -> dict[str, Any]:
    """Agreement of counted floors with register floors. rows = (building id, register floors, photo floors, confidence).

    Only buildings that have both numbers count. `broken_ids` (whose register data was seen before judging) are left out.
    """
    broken = set(broken_ids)
    by: dict[str, dict[str, int]] = {}
    excluded = 0
    for bid, reg, photo, conf in rows:
        if not (reg and photo):
            continue
        if bid in broken:
            excluded += 1
            continue
        slot = by.setdefault(conf or "none", {"compared": 0, "agree": 0})
        slot["compared"] += 1
        slot["agree"] += int(reg == photo)
    compared = sum(s["compared"] for s in by.values())
    agree = sum(s["agree"] for s in by.values())
    return {"compared": compared, "agree": agree, "rate": agree / compared if compared else None,
            "by_confidence": {k: by[k] for k in sorted(by)}, "excluded": excluded}
