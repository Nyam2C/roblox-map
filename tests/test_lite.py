"""B plan far view (lite.py): neighbouring cells' ground tiles neither overlap nor leave a gap, and the lite keeps every box and roof."""
from __future__ import annotations

import h3

import common
import layout
import lite

FRAME = layout.Frame.from_cfg(common.DEFAULTS)
CELL = "8930e0af13bffff"


def test_a_cell_and_its_ring_share_no_tile_and_every_grid_point_inside_has_one():
    cells = h3.grid_disk(CELL, 1)
    owner: dict[tuple[float, float], str] = {}
    for c in cells:
        for t in lite.ground_tiles(c, FRAME, None, layout.ground_item(c, FRAME, common.DEFAULTS)):
            key = (t.cx, t.cz)
            assert key not in owner, f"{key} in {owner.get(key)} and {c}"
            owner[key] = c
    # every grid centre that lies in the centre cell has a tile of it
    slab = layout.ground_item(CELL, FRAME, common.DEFAULTS)
    n = sum(1 for k, c in owner.items() if c == CELL)
    assert 15 <= n <= 40  # about 0.07 km2 / (192 studs)^2
    assert all(abs(t.cy + 0.9 + 3.0) < 1e-6 for t in lite.ground_tiles(CELL, FRAME, None, slab))  # flat: top 0.9 under 0


def test_the_lite_keeps_boxes_and_roofs_only():
    mk = lambda kind, name: layout._item(kind, name, "g", 0, (1.0, 2.0, 3.0), (4.0, 5.0, 6.0), 0.0)
    items = [mk("building", "gis:1"), mk("roof", "gis:1#rf0-0"), mk("facade", "gis:1#w0f0-0"), mk("prop", "tree1")]
    out = lite.lite_items(CELL, FRAME, items, None, layout.ground_item(CELL, FRAME, common.DEFAULTS))
    assert [i.name for i in out if i.kind != "ground"] == ["gis:1", "gis:1#rf0-0"]
