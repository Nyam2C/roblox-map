"""U3 pure functions: distance and bearing, crop settings, and cube-map -> perspective crop.

Needs only numpy and pillow (no shapely, so it stays out of geo.py). Cube-map layout and the meaning of
heading were checked by eye: aidlc-docs/construction/u3-street-view-capture/code/layout-notes.md
Rules: aidlc-docs/construction/u3-street-view-capture/functional-design/business-rules.md (BR-2.2, 2.3, 4.1-4.3;
BR-4.3 was changed in Build and Test, see build-and-test-summary.md)
"""
from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

import numpy as np
from PIL import Image

from common import building_height_m  # noqa: F401  (moved to common.py so build_luau.py needs no numpy; U3 still uses this name)

LatLon = tuple[float, float]
EARTH_R = 6371008.8  # same value as geo.EARTH_R, copied so this module does not import shapely
FOV_MARGIN_DEG = 20.0  # BR-4.2: room around the building's angular extent
VERTICAL_MARGIN_DEG = 8.0  # BR-4.3: spare view above the roof and below the ground line, together
MIN_WALL_M = 1.0  # a panorama closer than this to a wall is treated as 1 m away

# Face order in the 6144x1024 strip: front, right, back, left, up, down. Each row is
# (normal, image-right, image-up) in x=right, y=up, z=forward. Up and down were fixed by seam continuity.
FACE_AXES = np.array([
    [(0, 0, 1), (1, 0, 0), (0, 1, 0)],
    [(1, 0, 0), (0, 0, -1), (0, 1, 0)],
    [(0, 0, -1), (-1, 0, 0), (0, 1, 0)],
    [(-1, 0, 0), (0, 0, 1), (0, 1, 0)],
    [(0, 1, 0), (1, 0, 0), (0, 0, -1)],
    [(0, -1, 0), (1, 0, 0), (0, 0, 1)],
], dtype=np.float32)


def _wrap360(x: float) -> float:
    r = x % 360.0
    return 0.0 if r >= 360.0 else r  # a tiny negative x rounds to exactly 360.0


def _wrap180(x: float) -> float:
    r = (x + 180.0) % 360.0 - 180.0
    return r - 360.0 if r >= 180.0 else r


def _offset_m(a: LatLon, b: LatLon) -> tuple[float, float]:
    """East and north meters from a to b (flat approximation, symmetric in a and b)."""
    mid_lat = math.radians((a[0] + b[0]) / 2)
    return (math.radians(b[1] - a[1]) * math.cos(mid_lat) * EARTH_R, math.radians(b[0] - a[0]) * EARTH_R)


def distance_m(a: LatLon, b: LatLon) -> float:
    return math.hypot(*_offset_m(a, b))


def bearing_deg(a: LatLon, b: LatLon) -> float:
    """Compass bearing from a to b: north 0, clockwise, 0 <= result < 360 (BR-2.3)."""
    dx, dy = _offset_m(a, b)
    return _wrap360(math.degrees(math.atan2(dx, dy)))


def yaw_deg(bearing: float, heading: float) -> float:
    """Direction relative to the panorama's front face, -180 <= result < 180 (BR-4.1)."""
    return _wrap180(bearing - heading)


def building_extent_deg(outline: Sequence[LatLon], pano_pos: LatLon) -> float:
    """Width of the smallest arc, seen from the panorama, that contains every outline vertex."""
    bearings = sorted(bearing_deg(pano_pos, p) for p in outline)
    if len(bearings) < 2:
        return 0.0
    gaps = [b - a for a, b in zip(bearings, bearings[1:])] + [bearings[0] + 360.0 - bearings[-1]]
    return 360.0 - max(gaps)


def nearest_wall_m(outline: Sequence[LatLon], pano_pos: LatLon) -> float:
    """Distance from the panorama to the nearest edge of the outline (flat approximation)."""
    pts = [_offset_m(pano_pos, p) for p in outline]
    best = math.inf
    for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
        dx, dy = x2 - x1, y2 - y1
        length2 = dx * dx + dy * dy
        t = 0.0 if length2 == 0 else max(0.0, min(1.0, -(x1 * dx + y1 * dy) / length2))
        best = min(best, math.hypot(x1 + t * dx, y1 + t * dy))
    return best


def crop_params(extent_deg: float, wall_m: float, height_m: float, cfg: Mapping[str, Any]) -> tuple[float, float]:
    """(fov_deg, pitch_deg) for one building (BR-4.2, BR-4.3).

    Seen from the nearest wall, the roof is `up` degrees above the horizon and the ground line `down` degrees below
    it. The view is aimed at the middle of that span and widened until it fits (up to the fov limit), so close
    buildings keep their roof and their ground floor in frame.
    """
    wall = max(wall_m, MIN_WALL_M)
    camera = float(cfg["camera_height_m"])
    up, down = math.degrees(math.atan2(height_m - camera, wall)), math.degrees(math.atan2(camera, wall))
    aspect = cfg["crop_height"] / cfg["crop_width"]
    half_span = min((up + down + VERTICAL_MARGIN_DEG) / 2, 89.0)
    fov_for_height = 2 * math.degrees(math.atan(math.tan(math.radians(half_span)) / aspect))
    fov = min(float(cfg["fov_max_deg"]), max(float(cfg["fov_min_deg"]), extent_deg + FOV_MARGIN_DEG, fov_for_height))
    return fov, min(float(cfg["pitch_max_deg"]), max(0.0, (up - down) / 2))


def split_faces(strip: Image.Image) -> np.ndarray:
    """A 6N x N strip -> array (6, N, N, 3) in face order front, right, back, left, up, down."""
    n = strip.height
    if strip.width != 6 * n:
        raise ValueError(f"cube-map strip must be 6 times wider than tall, got {strip.size}")
    arr = np.asarray(strip.convert("RGB"))
    return arr.reshape(n, 6, n, 3).transpose(1, 0, 2, 3)


def render_crop(faces: np.ndarray, yaw: float, pitch: float, fov: float, size: tuple[int, int]) -> Image.Image:
    """Perspective view (size = width, height) looking at yaw (right of front) and pitch (up), fov = horizontal."""
    w, h = size
    n = faces.shape[1]
    f = (w / 2) / math.tan(math.radians(fov) / 2)
    x = np.broadcast_to(((np.arange(w) + 0.5) - w / 2) / f, (h, w))
    y = np.broadcast_to(((h / 2 - (np.arange(h) + 0.5)) / f)[:, None], (h, w))
    cp, sp = math.cos(math.radians(pitch)), math.sin(math.radians(pitch))
    cy, sy = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    y2, z2 = y * cp + sp, -y * sp + cp  # pitch about x (z = 1 before rotating)
    d = np.stack([x * cy + z2 * sy, y2, -x * sy + z2 * cy], axis=-1).astype(np.float32)
    along = d @ FACE_AXES[:, 0, :].T  # (h, w, 6): component along each face normal
    face = along.argmax(axis=-1)
    major = np.take_along_axis(along, face[..., None], axis=-1)[..., 0]
    a = (d * FACE_AXES[face, 1]).sum(-1) / major
    b = (d * FACE_AXES[face, 2]).sum(-1) / major
    col = np.clip((a + 1) / 2 * n - 0.5, 0, n - 1)
    row = np.clip((1 - b) / 2 * n - 0.5, 0, n - 1)
    x0, y0 = np.floor(col).astype(int), np.floor(row).astype(int)
    x1, y1 = np.minimum(x0 + 1, n - 1), np.minimum(y0 + 1, n - 1)
    fx, fy = (col - x0)[..., None], (row - y0)[..., None]
    top = faces[face, y0, x0] * (1 - fx) + faces[face, y0, x1] * fx
    bottom = faces[face, y1, x0] * (1 - fx) + faces[face, y1, x1] * fx
    return Image.fromarray(np.rint(top * (1 - fy) + bottom * fy).astype(np.uint8))
