"""The light version of a cell (2026-10-15, user: "칸만들때 지도에 맞게 가벼운판 같이 넣으면 안됨?"): the far view of the B plan, where the
server builds only the cells near players. Building boxes and roofs as the full cell has them, and the ground as tiles of one
grid shared by the whole region (a tile belongs to the cell its centre is in, so neighbours neither overlap nor leave gaps), a
little under the full cell's ground so a built neighbour's tiles win where they meet. About 150-250 parts a cell. build_luau.py
writes it next to chunks.json as lite.json (same format, one chunk).
"""
from __future__ import annotations

import dataclasses
import math
from typing import Any, Sequence

import h3

import layout
import terrain

GRID = 192.0  # studs: one ground tile of the far view
SINK = 0.3  # studs under the full ground's tile tops (terrain.TILE_UNDER under the heights)
KINDS = ("building", "roof")


def ground_tiles(cell_id: str, frame: layout.Frame, ground: Any, slab: layout.Item) -> list[layout.Item]:
    """The region grid's tiles whose centre lies in the cell, each lying on the heights at its centre (flat when there are none)."""
    res = h3.get_resolution(cell_id)
    i0, i1 = math.floor((slab.cx - slab.sx / 2) / GRID), math.ceil((slab.cx + slab.sx / 2) / GRID)
    j0, j1 = math.floor((slab.cz - slab.sz / 2) / GRID), math.ceil((slab.cz + slab.sz / 2) / GRID)
    out: list[layout.Item] = []
    for j in range(j0, j1 + 1):
        for i in range(i0, i1 + 1):
            x, z = (i + 0.5) * GRID, (j + 0.5) * GRID
            if h3.latlng_to_cell(*layout.from_studs(frame, x, z), res) != cell_id:
                continue
            ax = az = 0.0
            top = -terrain.TILE_UNDER - SINK
            if ground is not None:
                ax, az = terrain._slopes(ground, x, z, 0.0, GRID, GRID)
                top += ground.h(x, z)
            out.append(dataclasses.replace(slab, name=f"Lite.{j}.{i}", seq=len(out), cx=layout.fmt(x), cz=layout.fmt(z),
                                           cy=layout.fmt(top - terrain.TILE_T / 2), sx=GRID + 0.4, sy=terrain.TILE_T, sz=GRID + 0.4,
                                           tilt_x=ax, tilt_z=az))
    return out


def lite_items(cell_id: str, frame: layout.Frame, items: Sequence[layout.Item], ground: Any, slab: layout.Item) -> list[layout.Item]:
    """The full cell's building boxes and roofs (already on the ground) plus the cell's ground tiles."""
    return ground_tiles(cell_id, frame, ground, slab) + [i for i in items if i.kind in KINDS]
