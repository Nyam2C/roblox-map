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
  - long flat pieces are first cut into SEG-stud parts so a long road follows a bending slope instead of cutting into it;
  - the cell's ground slab becomes TILE-stud tiles, each tilted to its patch, their tops just under the roads (2026-10-15: Studio
    Terrain stepped 2 studs, came up over road edges on slopes and looked spiky, so the ground is parts again).
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
TILE = 48.0  # studs: the ground is tiles this size, each tilted to its own patch of ground (2026-10-15: Terrain stepped 2 studs,
#               rose over road edges on slopes and looked spiky, user)
TILE_T = 6.0  # thick enough that neighbouring tiles' edges overlap where their tilts differ
TILE_UNDER = 0.6  # studs the tile top stays under the ground heights (roads and sidewalks lie on the heights)
SEG = 40.0  # studs: a flat piece longer than this is cut so each part follows its own stretch of ground
BEND = 0.12  # studs: where the ground bends more than this off a road piece's plane, it is halved again (user 2026-10-15: "곡선으로")
BEND_TILE = 0.3  # studs: the same for a ground tile (between the roads, a little more is not seen)
SMOOTH = 16.0  # studs: the heights are smoothed this much (Gaussian sigma) before use
SEG_MIN = 10.0  # studs: no piece or tile is cut shorter than this
POST_SINK = 0.5  # studs a standing prop (tree, lamp, pole) reaches into the ground tiles, so none shows a gap at its foot


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
    from scipy.ndimage import gaussian_filter
    xs, zs, hm = elevation.surface(elevation.clean(points), step)
    hm = gaussian_filter(hm, SMOOTH / step, mode="nearest")  # camera heights wobble a few cm: a smooth ground bends only where it rises
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


def _slopes(ground: Ground, x: float, z: float, yaw: float, lx: float, lz: float) -> tuple[float, float]:
    """(tilt_x, tilt_z) in degrees for a flat part of size lx by lz at (x, z) turned `yaw` (the Builder's order)."""
    (ux, uz), (vx, vz) = _axes(yaw)
    sx = (ground.h(x + ux * lx / 2, z + uz * lx / 2) - ground.h(x - ux * lx / 2, z - uz * lx / 2)) / max(lx, 1e-6)
    sz = (ground.h(x + vx * lz / 2, z + vz * lz / 2) - ground.h(x - vx * lz / 2, z - vz * lz / 2)) / max(lz, 1e-6)
    return layout.fmt(-math.degrees(math.atan(sz))), layout.fmt(math.degrees(math.atan(sx)))


def _bend(ground: Ground, x: float, z: float, yaw: float, lx: float, lz: float) -> float:
    """How far (studs) the ground leaves the plane a flat part of lx by lz at (x, z) gets (centre height and _slopes)."""
    (ux, uz), (vx, vz) = _axes(yaw)
    h0 = ground.h(x, z)
    sx = (ground.h(x + ux * lx / 2, z + uz * lx / 2) - ground.h(x - ux * lx / 2, z - uz * lx / 2)) / max(lx, 1e-6)
    sz = (ground.h(x + vx * lz / 2, z + vz * lz / 2) - ground.h(x - vx * lz / 2, z - vz * lz / 2)) / max(lz, 1e-6)
    worst = 0.0
    for a in (-0.5, -0.25, 0.25, 0.5):
        for b in (-0.5, 0.0, 0.5):
            px, pz = x + ux * a * lx + vx * b * lz, z + uz * a * lx + vz * b * lz
            worst = max(worst, abs(ground.h(px, pz) - (h0 + sx * a * lx + sz * b * lz)))
    return worst


def tiles(slab: layout.Item, ground: Ground) -> list[layout.Item]:
    """The cell's ground slab as tiles lying on the heights (tops TILE_UNDER under them): TILE studs on the flat, halved again and
    again (quarters, down to SEG_MIN) where the ground bends more than BEND off a tile's plane."""
    nx, nz = max(1, math.ceil(slab.sx / TILE)), max(1, math.ceil(slab.sz / TILE))
    w0, d0 = slab.sx / nx, slab.sz / nz
    x0, z0 = slab.cx - slab.sx / 2, slab.cz - slab.sz / 2
    out: list[layout.Item] = []

    def tile(x: float, z: float, w: float, d: float, name: str) -> None:
        if w / 2 >= SEG_MIN and _bend(ground, x, z, 0.0, w, d) > BEND_TILE:
            for k, (a, b) in enumerate(((-1, -1), (1, -1), (-1, 1), (1, 1))):
                tile(x + a * w / 4, z + b * d / 4, w / 2, d / 2, f"{name}{k}")
            return
        ax, az = _slopes(ground, x, z, 0.0, w, d)
        top = ground.h(x, z) - TILE_UNDER
        out.append(dataclasses.replace(slab, name=name, seq=len(out), cx=layout.fmt(x), cz=layout.fmt(z), cy=layout.fmt(top - TILE_T / 2),
                                       sx=layout.fmt(w + 0.2), sy=TILE_T, sz=layout.fmt(d + 0.2), tilt_x=ax, tilt_z=az))

    for j in range(nz):
        for i in range(nx):
            tile(x0 + (i + 0.5) * w0, z0 + (j + 0.5) * d0, w0, d0, f"Ground.{j}-{i}.")
    return out


def _cut(i: layout.Item, ground: Ground) -> list[layout.Item]:
    """A flat piece longer than SEG, or bending more than BEND off its plane, halved along its long axis until it lies on its own
    stretch (down to SEG_MIN); parts are named <name>.<k>."""
    along_x = i.sx >= i.sz
    length = i.sx if along_x else i.sz
    if length / 2 < SEG_MIN or (length <= SEG and _bend(ground, i.cx, i.cz, i.yaw_deg, i.sx, i.sz) <= BEND):
        return [i]
    (ux, uz), (vx, vz) = _axes(i.yaw_deg)
    dx, dz = (ux, uz) if along_x else (vx, vz)
    out = []
    for k, sgn in enumerate((-1, 1)):
        half = dataclasses.replace(i, name=f"{i.name}.{k}", cx=layout.fmt(i.cx + dx * sgn * length / 4), cz=layout.fmt(i.cz + dz * sgn * length / 4),
                                   **({"sx": layout.fmt(length / 2 + 0.03)} if along_x else {"sz": layout.fmt(length / 2 + 0.03)}))
        out += _cut(half, ground)
    return out


class _Flat:
    def h(self, x: float, z: float) -> float:
        return 0.0


class _Raised:
    """The ground plus a bridge deck's rise over it (bridges.Decks.offset_studs) for the items of one bridge way."""

    def __init__(self, ground: Any, decks: Any, fid: str):
        self.ground, self.decks, self.fid = ground, decks, fid

    def h(self, x: float, z: float) -> float:
        return self.ground.h(x, z) + self.decks.offset_studs(self.fid, x, z)


def _on_deck(i: layout.Item, ground: Any, decks: Any) -> list[layout.Item]:
    """An item of a bridge way on its deck: blocks are cut and tilted along it (the road, lines, girder, walls), the rest rise by
    the centre; street props a deck does not carry are dropped where it is up (bridges.KEEP)."""
    g = _Raised(ground, decks, i.group)
    rise = decks.offset_studs(i.group, i.cx, i.cz)
    if i.kind == "prop" and rise > 1.0 and not any(k in i.name for k in decks.keep) and "#deck" not in i.name and "#bw" not in i.name:
        return []
    if i.shape == "Block" and i.kind in ("road", "prop") and max(i.sx, i.sz) >= FLAT_MIN and not any(k in i.name for k in ("#lamp", "#larm", "#lhead")):
        out = []
        for p in _cut(i, g):
            ax, az = _slopes(g, p.cx, p.cz, p.yaw_deg, p.sx, p.sz)
            out.append(dataclasses.replace(p, cy=layout.fmt(p.cy + g.h(p.cx, p.cz)), tilt_x=ax, tilt_z=az))
        return out
    return [dataclasses.replace(i, cy=layout.fmt(i.cy + g.h(i.cx, i.cz)))]


def lift(items: Sequence[layout.Item], ground: Ground | None, decks: Any = None) -> list[layout.Item]:
    """Items onto the ground heights; the items of a bridge way (decks: bridges.Decks) onto its deck."""
    if decks is not None and decks.fids:
        on = [i for i in items if i.group in decks.fids]
        rest = [i for i in items if i.group not in decks.fids]
        return [p for i in on for p in _on_deck(i, ground or _Flat(), decks)] + lift(rest, ground)
    if ground is None:
        return list(items)
    by_unit: dict[str, float] = {}
    for i in items:  # a building's lift: the lowest ground under its boxes
        u = _unit(i)
        if u and u.startswith("b:") and i.kind == "building":
            low = min(ground.h(x, z) for x, z in _corners(i) + [(i.cx, i.cz)])
            by_unit[u] = min(by_unit.get(u, low), low)
    out = []
    flat = lambda i: i.sy <= FLAT_MAX_H and max(i.sx, i.sz) >= FLAT_MIN and i.shape == "Block" and _unit(i) is None
    items = [p for i in items for p in (_cut(i, ground) if i.kind != "ground" and flat(i) else [i])]
    for i in items:
        if i.kind == "ground":
            out += tiles(i, ground)
            continue
        u = _unit(i)
        if u is not None:
            if u not in by_unit:
                by_unit[u] = ground.h(i.cx, i.cz)
            out.append(dataclasses.replace(i, cy=layout.fmt(i.cy + by_unit[u])))
            continue
        dy = ground.h(i.cx, i.cz)
        if flat(i):
            ax, az = _slopes(ground, i.cx, i.cz, i.yaw_deg, i.sx, i.sz)
            out.append(dataclasses.replace(i, cy=layout.fmt(i.cy + dy), tilt_x=ax, tilt_z=az))
        else:
            cyl = i.shape == "Cylinder"  # a standing cylinder's height is its first size
            height = i.sx if cyl else i.sy
            if i.kind == "prop" and i.kit is None and height > FLAT_MAX_H and i.cy - height / 2 < 0.5:
                # standing on the ground: reach POST_SINK further down so no gap shows over the tiles, the top stays
                grow = dict(sx=layout.fmt(i.sx + POST_SINK)) if cyl else dict(sy=layout.fmt(i.sy + POST_SINK))
                out.append(dataclasses.replace(i, cy=layout.fmt(i.cy + dy - POST_SINK / 2), **grow))
            else:
                out.append(dataclasses.replace(i, cy=layout.fmt(i.cy + dy)))
    return out
