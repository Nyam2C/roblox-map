"""U3 pure functions: distance and bearing, crop settings, and cube-map -> perspective crop.

Needs only numpy and pillow (no shapely, so it stays out of geo.py). Cube-map layout and the meaning of
heading were checked by eye: aidlc-docs/construction/u3-street-view-capture/code/layout-notes.md
Rules: aidlc-docs/construction/u3-street-view-capture/functional-design/business-rules.md (BR-2.2, 2.3, 4.1-4.3;
BR-4.3 was changed in Build and Test, see build-and-test-summary.md)
"""
from __future__ import annotations

import math
from dataclasses import dataclass
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


# --- faces of a building and lines of sight (BR-2.7) ---------------------------------------------------

FACE_MERGE_DEG = 25.0  # neighbouring edges whose outward directions differ by less than this form one face
BLOCK_SHIFT_M = 0.5  # the line of sight stops this far in front of the wall, so the wall itself does not block it


def angle_gap_deg(a: float, b: float) -> float:
    """Smallest difference between two compass angles, 0 to 180."""
    d = abs(a - b) % 360.0
    return min(d, 360.0 - d)


@dataclass(frozen=True)
class Face:
    azimuth_deg: float  # outward direction of the face, north 0, clockwise
    length_m: float  # total length of the edges merged into this face
    target: LatLon  # aim point: the middle of the face's longest edge
    a: LatLon  # ends of that longest edge, used for the angular extent and the wall distance
    b: LatLon


def point_toward(origin: LatLon, azimuth_deg: float, meters: float) -> LatLon:
    """The point `meters` away from `origin` in the compass direction `azimuth_deg` (flat approximation)."""
    east = meters * math.sin(math.radians(azimuth_deg))
    north = meters * math.cos(math.radians(azimuth_deg))
    lat = origin[0] + math.degrees(north / EARTH_R)
    return (lat, origin[1] + math.degrees(east / (EARTH_R * math.cos(math.radians((lat + origin[0]) / 2)))))


def point_in_polygon(point: LatLon, polygon: Sequence[LatLon]) -> bool:
    """Ray casting in latitude/longitude, fine for areas the size of a school."""
    y, x = point
    inside = False
    j = len(polygon) - 1
    for i in range(len(polygon)):
        (yi, xi), (yj, xj) = polygon[i], polygon[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def _mean_azimuth(edges: Sequence[tuple[float, float, int, int]]) -> float:
    sx = sum(length * math.sin(math.radians(az)) for az, length, _, _ in edges)
    sy = sum(length * math.cos(math.radians(az)) for az, length, _, _ in edges)
    return _wrap360(math.degrees(math.atan2(sx, sy)))


def building_faces(outline: Sequence[LatLon], min_len_m: float) -> list[Face]:
    """The sides of a building, longest first: all the edges that face the same way, however many steps they have.

    Neighbouring edges whose outward directions differ by less than FACE_MERGE_DEG form a run (a gently curved wall
    is one run, a corner starts a new one); runs that face the same way become one side. The aim point and the ends
    of a side belong to its longest edge. Sides shorter than `min_len_m` in total are left out.
    """
    ring = list(outline)
    if len(ring) > 1 and ring[0] == ring[-1]:
        ring = ring[:-1]
    if len(ring) < 3:
        return []
    pts = [_offset_m(ring[0], p) for p in ring]
    area2 = sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]))
    if abs(area2) < 1e-6:
        return []
    sign = 1.0 if area2 > 0 else -1.0  # counter-clockwise rings have their outside on the right of each edge
    edges: list[tuple[float, float, int, int]] = []
    for i in range(len(ring)):
        j = (i + 1) % len(ring)
        dx, dy = pts[j][0] - pts[i][0], pts[j][1] - pts[i][1]
        length = math.hypot(dx, dy)
        if length >= 0.5:
            edges.append((_wrap360(math.degrees(math.atan2(sign * dy, -sign * dx))), length, i, j))
    if not edges:
        return []
    turns = [angle_gap_deg(edges[k - 1][0], edges[k][0]) for k in range(len(edges))]
    start = max(range(len(edges)), key=lambda k: turns[k])  # begin at the sharpest corner so no face is cut in two
    ordered = edges[start:] + edges[:start]
    groups = [[ordered[0]]]
    for edge in ordered[1:]:
        if angle_gap_deg(_mean_azimuth(groups[-1]), edge[0]) < FACE_MERGE_DEG:
            groups[-1].append(edge)
        else:
            groups.append([edge])
    # A stepped wall is several runs facing the same way, parted by short edges that face across: they are one side.
    sides: list[list[tuple[float, float, int, int]]] = []
    for g in sorted(groups, key=lambda g: -sum(e[1] for e in g)):
        for side in sides:
            if angle_gap_deg(_mean_azimuth(side), _mean_azimuth(g)) < FACE_MERGE_DEG:
                side.extend(g)
                break
        else:
            sides.append(list(g))
    faces = []
    for g in sides:
        length = sum(e[1] for e in g)
        if length < min_len_m:
            continue
        _, _, i, j = max(g, key=lambda e: e[1])
        a, b = ring[i], ring[j]
        faces.append(Face(_mean_azimuth(g), length, ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2), a, b))
    faces.sort(key=lambda f: (-f.length_m, f.azimuth_deg))
    return faces


def _in_xy(pt: tuple[float, float], poly: Sequence[tuple[float, float]]) -> bool:
    x, y = pt
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        (xi, yi), (xj, yj) = poly[i], poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def _cross(o: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def segment_hits_polygon(p: LatLon, q: LatLon, polygon: Sequence[LatLon]) -> bool:
    """True if the straight line from p to q enters or crosses the polygon (flat approximation)."""
    ring = list(polygon)
    if len(ring) > 1 and ring[0] == ring[-1]:
        ring = ring[:-1]
    if len(ring) < 3:
        return False
    if (max(p[0], q[0]) < min(r[0] for r in ring) or min(p[0], q[0]) > max(r[0] for r in ring)
            or max(p[1], q[1]) < min(r[1] for r in ring) or min(p[1], q[1]) > max(r[1] for r in ring)):
        return False  # the line's box and the polygon's box do not even touch
    a, b = (0.0, 0.0), _offset_m(p, q)
    pts = [_offset_m(p, r) for r in ring]
    if _in_xy(a, pts) or _in_xy(b, pts):
        return True
    for c, d in zip(pts, pts[1:] + pts[:1]):
        if _cross(c, d, a) * _cross(c, d, b) < 0 and _cross(a, b, c) * _cross(a, b, d) < 0:
            return True
    return False


def line_blocked(pano: LatLon, target: LatLon, polygon: Sequence[LatLon]) -> bool:
    """Does `polygon` stand between the panorama and a point on a wall? The line ends BLOCK_SHIFT_M short of the wall."""
    d = distance_m(pano, target)
    if d <= BLOCK_SHIFT_M:
        return False
    t = BLOCK_SHIFT_M / d
    end = (target[0] + (pano[0] - target[0]) * t, target[1] + (pano[1] - target[1]) * t)
    return segment_hits_polygon(pano, end, polygon)

