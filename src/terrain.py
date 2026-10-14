"""Ground heights on the map (2026-10-15, user: the place is not flat; 래미안's side road climbs about 4 m).

The heights come from regions/<region>/elevation.json (street-view camera altitudes, elevation.py) and are turned into studs above
`ground_base_m` (the flat south, so most of the map moves little). `Ground.h(x, z)` is bilinear on a regular grid. `lift` moves the
plan items onto it:
  - a building and everything it owns rise together by the lowest ground under the building's boxes (the uphill side sits in the
    ground, nothing floats);
  - flat pieces lying on the ground (roads, paths, sidewalks, markings, curbs, crosswalks, school grounds: thin and at least
    `FLAT_MIN` long) rise to the ground at their middle and tilt with it along both their own axes (keys ax, az);
  - a trick ramp and a subway entrance rise as one, by the ground at their first piece;
  - everything else (trees, lamps, poles, bollards, the spawn) rises by the ground under its middle;
  - the cell's ground slab goes down out of sight: Studio fills Terrain to the grid instead (MapBuilder.terrain).
"""
from __future__ import annotations

import dataclasses
import math
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence

import common
import elevation
import layout

STEP = 8.0  # studs between grid heights (Studio's terrain voxels are 4)
FLAT_MAX_H = 1.0  # studs: a piece this thin lies on the ground
FLAT_MIN = 3.0  # studs: and this long along one axis tilts with the ground
SLAB_DROP = 40.0  # studs the ground slab goes down under the terrain
POST_SINK = 2.0  # studs a standing prop (tree, lamp, pole) goes into the ground: Studio's terrain lies 0.5 to 2 under the heights


@dataclasses.dataclass(frozen=True)
class Ground:
    x0: float
    z0: float
    step: float
    nx: int
    nz: int
    hs: tuple[float, ...]  # row-major by z, in studs

    def h(self, x: float, z: float) -> float:
        fx = min(max((x - self.x0) / self.step, 0.0), self.nx - 1.0)
        fz = min(max((z - self.z0) / self.step, 0.0), self.nz - 1.0)
        i, j = min(int(fx), self.nx - 2), min(int(fz), self.nz - 2)
        tx, tz = fx - i, fz - j
        a, b = self.hs[j * self.nx + i], self.hs[j * self.nx + i + 1]
        c, d = self.hs[(j + 1) * self.nx + i], self.hs[(j + 1) * self.nx + i + 1]
        return (a * (1 - tx) + b * tx) * (1 - tz) + (c * (1 - tx) + d * tx) * tz

    def coarse(self, step: float) -> "Ground":
        """The same ground sampled every `step` studs (a smaller file for the whole region)."""
        nx = int((self.nx - 1) * self.step // step) + 1
        nz = int((self.nz - 1) * self.step // step) + 1
        hs = tuple(self.h(self.x0 + i * step, self.z0 + j * step) for j in range(nz) for i in range(nx))
        return Ground(self.x0, self.z0, step, nx, nz, hs)

    def window(self, x0: float, x1: float, z0: float, z1: float) -> dict[str, Any]:
        """The grid over a box as plain data for Studio: x0, z0, step, nx, nz, h (row-major by z, 0.01 stud)."""
        i0, i1 = max(0, int((x0 - self.x0) // self.step)), min(self.nx - 1, int(math.ceil((x1 - self.x0) / self.step)))
        j0, j1 = max(0, int((z0 - self.z0) // self.step)), min(self.nz - 1, int(math.ceil((z1 - self.z0) / self.step)))
        hs = [round(self.hs[j * self.nx + i], 2) for j in range(j0, j1 + 1) for i in range(i0, i1 + 1)]
        return {"x0": self.x0 + i0 * self.step, "z0": self.z0 + j0 * self.step, "step": self.step, "nx": i1 - i0 + 1, "nz": j1 - j0 + 1, "h": hs}


def from_points(points: Sequence[Sequence[float]], base_m: float, studs_per_m: float, step: float = STEP) -> Ground:
    """points: (x studs, z studs, altitude m)."""
    xs, zs, hm = elevation.surface(elevation.clean(points), step)
    hs = tuple(float((v - base_m) * studs_per_m) for v in hm.ravel())
    return Ground(float(xs[0]), float(zs[0]), step, len(xs), len(zs), hs)


@lru_cache(maxsize=4)
def _region_ground(region_dir: str, base_m: float, origin: tuple[float, float, float]) -> Ground | None:
    frame = layout.Frame(*origin)
    pts = elevation.load(Path(region_dir) / "elevation.json")
    if len(pts) < 4:
        return None
    return from_points([(*layout.to_studs(frame, lat, lon), alt) for lat, lon, alt in pts.values()], base_m, frame.studs_per_m)


def ground_for(cfg: Mapping[str, Any]) -> Ground | None:
    """The cell's region ground, or None when the region has no heights yet (the map stays flat)."""
    frame = layout.Frame.from_cfg(cfg)
    region_dir = common.resolve(cfg["regions_dir"]) / cfg["region"] if cfg.get("region") else None
    if region_dir is None:
        return None
    return _region_ground(str(region_dir), float(cfg.get("ground_base_m", 37.0)), (frame.origin_lat, frame.origin_lon, frame.studs_per_m))


def _axes(yaw_deg: float) -> tuple[tuple[float, float], tuple[float, float]]:
    t = math.radians(yaw_deg)
    return (math.cos(t), -math.sin(t)), (math.sin(t), math.cos(t))  # local X and Z in (x, z), the item rule


def _corners(i: layout.Item) -> list[tuple[float, float]]:
    (ux, uz), (vx, vz) = _axes(i.yaw_deg)
    return [(i.cx + a * ux * i.sx / 2 + b * vx * i.sz / 2, i.cz + a * uz * i.sx / 2 + b * vz * i.sz / 2) for a in (-1, 1) for b in (-1, 1)]


def _unit(i: layout.Item) -> str | None:
    """The key of the group an item rises with, or None when it rises on its own."""
    if i.kind in ("building", "roof", "facade", "sign"):
        return "b:" + (i.owner or i.name.split("#", 1)[0])
    if "#ramp" in i.name:
        return "r:" + i.name.split("#ramp", 1)[0]
    if i.name.startswith("node:"):
        return "n:" + i.name.split("#", 1)[0]
    return None


def lift(items: Sequence[layout.Item], ground: Ground | None) -> list[layout.Item]:
    if ground is None:
        return list(items)
    by_unit: dict[str, float] = {}
    for i in items:  # a building's lift: the lowest ground under its boxes
        u = _unit(i)
        if u and u.startswith("b:") and i.kind == "building":
            low = min(ground.h(x, z) for x, z in _corners(i) + [(i.cx, i.cz)])
            by_unit[u] = min(by_unit.get(u, low), low)
    out = []
    for i in items:
        if i.kind == "ground":
            out.append(dataclasses.replace(i, cy=layout.fmt(i.cy - SLAB_DROP)))
            continue
        u = _unit(i)
        if u is not None:
            if u not in by_unit:
                by_unit[u] = ground.h(i.cx, i.cz)
            out.append(dataclasses.replace(i, cy=layout.fmt(i.cy + by_unit[u])))
            continue
        dy = ground.h(i.cx, i.cz)
        if i.sy <= FLAT_MAX_H and max(i.sx, i.sz) >= FLAT_MIN and i.shape == "Block":
            (ux, uz), (vx, vz) = _axes(i.yaw_deg)
            sx = (ground.h(i.cx + ux * i.sx / 2, i.cz + uz * i.sx / 2) - ground.h(i.cx - ux * i.sx / 2, i.cz - uz * i.sx / 2)) / max(i.sx, 1e-6)
            sz = (ground.h(i.cx + vx * i.sz / 2, i.cz + vz * i.sz / 2) - ground.h(i.cx - vx * i.sz / 2, i.cz - vz * i.sz / 2)) / max(i.sz, 1e-6)
            out.append(dataclasses.replace(i, cy=layout.fmt(i.cy + dy), tilt_x=layout.fmt(-math.degrees(math.atan(sz))),
                                           tilt_z=layout.fmt(math.degrees(math.atan(sx)))))
        else:
            cyl = i.shape == "Cylinder"  # a standing cylinder's height is its first size
            height = i.sx if cyl else i.sy
            if i.kind == "prop" and i.kit is None and height > FLAT_MAX_H and i.cy - height / 2 < 0.5:
                # standing on the ground: reach POST_SINK further down so no gap shows over the terrain, the top stays
                grow = dict(sx=layout.fmt(i.sx + POST_SINK)) if cyl else dict(sy=layout.fmt(i.sy + POST_SINK))
                out.append(dataclasses.replace(i, cy=layout.fmt(i.cy + dy - POST_SINK / 2), **grow))
            else:
                out.append(dataclasses.replace(i, cy=layout.fmt(i.cy + dy)))
    return out
