# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""H: kit meshes made in Python -> data/kits/<name>.obj, uploaded once by the user with Studio's Import 3D (U7 H).

Usage (repo root):
  uv run src/kits.py trees      # crown-1.obj, crown-2.obj: the three crown balls of details_rules.TREE_CROWNS[0] and [1] as one lumpy
                                # mesh (about 240 triangles) in metres, centred on the cluster, ground at the lowest point

The Studio MCP can upload images but not meshes, so the user imports the files (Home > Import 3D) and Claude reads the MeshId of the
imported MeshPart and fixes it in git. A crown mesh replaces three Ball parts per tree; the trunk stays a Cylinder part. Variety stays
with details_rules.pick (no randomness): the lumps are moved by crc32 of the vertex index.
"""
from __future__ import annotations

import math
import sys
import zlib
from pathlib import Path

import details_rules as R

OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "kits"
LUMP = 0.12  # each vertex moves in or out by up to this share of its ball's radius


def icosphere(level: int = 1) -> tuple[list[tuple[float, float, float]], list[tuple[int, int, int]]]:
    t = (1 + 5 ** 0.5) / 2
    v = [(-1, t, 0), (1, t, 0), (-1, -t, 0), (1, -t, 0), (0, -1, t), (0, 1, t), (0, -1, -t), (0, 1, -t), (t, 0, -1), (t, 0, 1), (-t, 0, -1), (-t, 0, 1)]
    v = [tuple(c / math.sqrt(sum(x * x for x in p)) for c in p) for p in v]
    f = [(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11), (1, 5, 9), (5, 11, 4), (11, 10, 2), (10, 7, 6), (7, 1, 8), (3, 9, 4), (3, 4, 2),
         (3, 2, 6), (3, 6, 8), (3, 8, 9), (4, 9, 5), (2, 4, 11), (6, 2, 10), (8, 6, 7), (9, 8, 1)]
    for _ in range(level):
        mid: dict[tuple[int, int], int] = {}

        def m(a: int, b: int) -> int:
            k = (min(a, b), max(a, b))
            if k not in mid:
                p = [(x + y) / 2 for x, y in zip(v[a], v[b])]
                n = math.sqrt(sum(c * c for c in p))
                v.append(tuple(c / n for c in p))
                mid[k] = len(v) - 1
            return mid[k]
        f = [g for a, b, c in f for g in ((a, m(a, b), m(a, c)), (b, m(b, c), m(a, b)), (c, m(a, c), m(b, c)), (m(a, b), m(b, c), m(a, c)))]
    return v, f  # type: ignore[return-value]


# uploaded with Studio Import 3D by the user on 2026-10-14 (both shown in Studio, not moderated); Studio keeps a MeshPart of each
# in ServerStorage/Kits/<name> for the Builder to clone (cycle-build 7)
MESH_IDS = {"crown-1": 95964295607986, "crown-2": 128934972963239}
CROWNS = {"crown-1": 0, "crown-2": 1}  # kit -> its details_rules.TREE_CROWNS layout


def crown_mesh(name: str) -> tuple[list[tuple[float, float, float]], list[tuple[int, int, int]]]:
    """Vertices (cluster frame, metres: x along, y up, z = -left) and triangles of a crown kit, before centring."""
    base_v, base_f = icosphere(1)
    verts: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int]] = []
    for k, (da, dl, cy, bd) in enumerate(R.TREE_CROWNS[CROWNS[name]]):
        r = bd / 2
        off = len(verts)
        for i, (x, y, z) in enumerate(base_v):
            lump = 1 + LUMP * ((zlib.crc32(f"{name}|{k}|{i}".encode()) % 2001) / 1000 - 1)
            verts.append((da + x * r * lump, cy + y * r * lump, -dl + z * r * lump))
        faces += [(a + off, b + off, c + off) for a, b, c in base_f]
    return verts, faces


def crown_box(name: str) -> tuple[float, float, float, tuple[float, float, float]]:
    """(along, left, bottom height, size) in metres of a crown kit's bounding box in the cluster frame at scale 1."""
    v, _ = crown_mesh(name)
    lo = [min(p[i] for p in v) for i in range(3)]
    hi = [max(p[i] for p in v) for i in range(3)]
    return (lo[0] + hi[0]) / 2, -(lo[2] + hi[2]) / 2, lo[1], (hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2])


def crown_obj(name: str) -> str:
    """OBJ text of a crown kit, Y up, centred on its box, its lowest point at y = 0 (the MeshPart's centre is the box centre)."""
    verts, faces = crown_mesh(name)
    cx = (min(p[0] for p in verts) + max(p[0] for p in verts)) / 2
    cz = (min(p[2] for p in verts) + max(p[2] for p in verts)) / 2
    y0 = min(p[1] for p in verts)
    lines = [f"# {name}: roblox-map kit (src/kits.py), metres, {len(faces)} triangles", f"o {name}"]
    lines += [f"v {x - cx:.4f} {y - y0:.4f} {z - cz:.4f}" for x, y, z in verts]
    lines += [f"f {a + 1} {b + 1} {c + 1}" for a, b, c in faces]  # counter-clockwise seen from outside (tests/test_kits.py)
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    if argv != ["trees"]:
        print(__doc__)
        return 2
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name in CROWNS:
        path = OUT_DIR / f"{name}.obj"
        path.write_text(crown_obj(name), encoding="utf-8")
        print(f"-> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
