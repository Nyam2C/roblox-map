"""P7-9: tiers are classified deterministically, a hand-set tier survives reclassification, and the first three cells are tier 1."""
from __future__ import annotations

import json
import random
import sys

import h3
import pytest

import common
import tiers as T
from conftest import one_region

CELL = "8930e0af13bffff"
CELLS = ("8930e0af13bffff", "8930e0af123ffff", "8930e0af12bffff")


def landuse(kind, frac=1.0, cell=CELL):
    """A closed landuse way: the cell's own hexagon shrunk toward its centre so it covers about `frac` of the cell."""
    lat0, lon0 = h3.cell_to_latlng(cell)
    s = frac ** 0.5
    ring = [{"lat": lat0 + (lat - lat0) * s, "lon": lon0 + (lon - lon0) * s} for lat, lon in h3.cell_to_boundary(cell)]
    return {"type": "way", "id": 1, "tags": {"landuse": kind}, "geometry": ring + ring[:1]}


def count(n):  # an element classify ignores
    return {"type": "count", "id": 0, "tags": {"ways": str(n)}}


def school_near_vertex(out):
    """A school square centred on the cell's first boundary vertex, moved outward by `out` x (vertex - centre)."""
    lat, lon = h3.cell_to_latlng(CELL)
    blat, blon = h3.cell_to_boundary(CELL)[0]
    cy, cx, t = blat + (blat - lat) * out, blon + (blon - lon) * out, 0.0005
    ring = [{"lat": cy - t, "lon": cx - t}, {"lat": cy - t, "lon": cx + t}, {"lat": cy + t, "lon": cx + t}, {"lat": cy + t, "lon": cx - t}]
    return {"type": "way", "id": 8, "tags": {"amenity": "school", "name": "s"}, "geometry": ring + ring[:1]}


def shop(i):
    return {"type": "node", "id": 100 + i, "tags": {"shop": "convenience"}}


@pytest.mark.parametrize("elements,tier", [
    ([count(80), {"type": "way", "id": 5, "tags": {"amenity": "school", "name": "x school"}}], 1),
    ([count(80), {"type": "node", "id": 6, "tags": {"railway": "station"}}], 1),
    ([count(80)] + [shop(i) for i in range(T.POI_MIN)], 1),
    ([count(80), landuse("retail", 0.4)], 1),
    ([count(80), landuse("residential", 0.9)] + [shop(i) for i in range(T.POI_MIN - 1)], 2),
    ([count(80), {"type": "node", "id": 7, "tags": {"amenity": "hospital", "name": "clinic"}}], 2),  # a clinic point is no landmark
    ([count(80), landuse("industrial", 0.6)], 3),
    ([count(80), landuse("farmland", 0.7)], 3),
    ([count(3)], 2),  # few OSM buildings mean nothing: OSM has few here (2026-10-14)
    ([school_near_vertex(0.0)], 1),  # about a third of it in the cell
    ([school_near_vertex(0.25)], 2),  # a sliver of a school is no landmark of this cell
])
def test_classify_follows_the_rules(elements, tier):
    got, reason, counts = T.classify(CELL, elements)
    assert got == tier and reason


def test_classify_is_deterministic_whatever_the_order():
    elements = [count(80), landuse("residential", 0.5), landuse("retail", 0.1), {"type": "way", "id": 9, "tags": {"leisure": "park", "name": "p"}}] + \
        [shop(i) for i in range(5)]
    first = T.classify(CELL, elements)
    for seed in range(5):
        shuffled = elements[:]
        random.Random(seed).shuffle(shuffled)
        assert T.classify(CELL, shuffled) == first
    assert first[2]["share"]["residential"] == pytest.approx(0.5, abs=0.02)


def test_a_hand_set_tier_survives_reclassification_and_set_needs_a_reason(tmp_path, monkeypatch, capsys):
    cfg = {**common.DEFAULTS, **one_region(tmp_path, CELL)}
    path = T.tiers_path(cfg, CELL)
    T.write_tiers(path, {CELL: T.merge(None, 1, "landmarks", {"pois": 1})})
    assert T.tier_of(cfg, CELL) == 1
    monkeypatch.setattr(sys, "argv", ["tiers.py", "set", "--cell", CELL, "--tier", "2", "--reason", "user: mostly villas"])
    assert T.main(cfg) == 0
    rows = T.read_tiers(path)
    rows[CELL] = T.merge(rows[CELL], 1, "landmarks", {"pois": 9})
    assert (rows[CELL]["tier"], rows[CELL]["manual"], rows[CELL]["counts"]) == (2, True, {"pois": 9})
    monkeypatch.setattr(sys, "argv", ["tiers.py", "set", "--cell", CELL, "--tier", "2", "--reason", " "])
    with pytest.raises(SystemExit):
        T.main(cfg)
    assert T.tier_of({**common.DEFAULTS, **one_region(tmp_path / "other", "8930e0af12bffff")}, "8930e0af12bffff") is None


def test_the_first_three_cells_are_tier_1():
    cfg = common.load_config()
    rows = T.read_tiers(T.tiers_path(cfg, CELL))
    assert {c: (rows[c]["tier"], rows[c]["manual"]) for c in CELLS} == {c: (1, False) for c in CELLS}
    assert json.loads(T.tiers_path(cfg, CELL).read_text(encoding="utf-8"))["cells"].keys() >= set(CELLS)
