"""satellite.py (U7 B, moved from the cycle skills): tile math agrees with trees.py, the mosaic covers the cell."""
from __future__ import annotations

import h3
import pytest

import common
import layout
import satellite as S
import trees as T

CELL = "8930e0af13bffff"


@pytest.mark.parametrize("lat,lon", [(37.504169, 126.779628), (37.49, 126.76), (37.52, 126.80)])
def test_tile_xy_is_the_inverse_of_the_trees_georef(lat, lon):
    x, y = S.tile_xy(lat, lon)
    back = T.Georef(0, 0).to_latlon(x * 256, y * 256)
    assert back == pytest.approx((lat, lon), abs=1e-9)


def test_the_cell_mosaic_covers_the_cell_with_margin():
    tx0, tx1, ty0, ty1 = S.cell_tiles(CELL)
    assert (tx0, ty0) == (446774, 203141)  # the first cell's mosaic made by the skill script (data/satellite/<cell>-z19.json)
    for lat, lon in h3.cell_to_boundary(CELL):
        x, y = S.tile_xy(lat, lon)
        assert tx0 < x < tx1 + 1 and ty0 < y < ty1 + 1


def test_the_capture_centre_maps_to_the_tile_of_its_stud_point():
    frame = layout.Frame.from_cfg(common.DEFAULTS)
    to_tile = S.capture_to_tile(frame, (1631, 882), 100.0, -50.0, 0.974)
    assert to_tile(1631 / 2, 882 / 2) == pytest.approx(S.tile_xy(*layout.from_studs(frame, 100.0, -50.0)))
    (x0, y0), (x1, y1) = to_tile(0, 0), to_tile(1631, 882)
    assert x1 > x0 and y1 > y0  # east is right, south is down
