# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""H: kit meshes made in Python -> data/kits/<name>.obj, uploaded once by the user with Studio's Import 3D (U7 H).

Usage (repo root):
  uv run src/kits.py trees      # crown-1.obj, crown-2.obj: the three crown balls of details_rules.TREE_CROWNS[0] and [1] as one lumpy
                                # mesh (about 240 triangles) in metres, centred on the cluster, ground at the lowest point
  uv run src/kits.py stacks     # stacks.obj: every column-stack kit (STACKS) as one object each, for one Import 3D

The Studio MCP can upload images but not meshes, so the user imports the files (Home > Import 3D) and Claude reads the MeshId of the
imported MeshPart and fixes it in git. A crown mesh replaces three Ball parts per tree; the trunk stays a Cylinder part. Variety stays
with details_rules.pick (no randomness): the lumps are moved by crc32 of the vertex index.
"""
from __future__ import annotations

import dataclasses
import math
import re
import sys
import zlib
from pathlib import Path
from typing import Any, Mapping, Sequence

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


# Column stacks (2026-10-15, user decision: keep the detail, fewer parts). A face repeats the same piece once per floor (an AC box, a
# balcony glass band, a rail panel, a slab, a window): n of them one above the other at the floor pitch become one MeshPart of n boxes,
# stretched to the run's size. A mesh has one colour, so each look is its own stack. The piece's share of the pitch is baked in, so
# a tail has a mesh per pitch bucket where the piece height does not follow the pitch; a run takes a stack only when every piece
# lands within STACK_TOL_M of where its part was. Runs split greedily into STACK_N; what is left stays parts.
STACK_N = (16, 8, 4, 2)
STACK_TOL_M = 0.08
STACK_LOOKS: dict[str, tuple[tuple[str, float, float], ...]] = {  # name tail -> (bucket, piece height m, pitch m), from the 25 built cells
    "aa": (("31", 0.6, 3.1),), "as": (("31", 0.3, 3.1),), "ar": (("31", 0.85, 3.1),),  # apartment AC, slab, rail panel (BR-6.5)
    "ag": (("28", 1.3, 2.8), ("34", 1.9, 3.4)),  # apartment glass band: fh - 1.5 m tall
    "w": (("34", 1.5, 3.4), ("37", 1.5, 3.7), ("41", 1.5, 4.1)),  # grid windows (offices, schools, shops' upper floors)
    "rb": (("50", 1.7, 3.4), ("38", 1.7, 3.8)),  # ribbon windows: half the floor up to 1.7 m
    "fl": (("31", 0.12, 3.1),),  # floor bands round the box
    "ws": (("30", 1.5, 3.0), ("34", 1.9, 3.4)),  # villa wall skin between window rows: fh - 1.5 m
}
STACKS: dict[str, tuple[float, float, int]] = {f"stk-{t}{b}-{n}": (h, p, n) for t, rows in STACK_LOOKS.items() for b, h, p in rows for n in STACK_N}
_TAIL = re.compile(r"#(aa|as|ar|ag|w|rb|fl|ws)\d")


# a box's six faces: (outward normal, its four corners as (x, y, z) signs, counter-clockwise seen from outside)
_BOX_FACES = (((0, -1, 0), ((-1, 0, -1), (1, 0, -1), (1, 0, 1), (-1, 0, 1))), ((0, 1, 0), ((-1, 1, -1), (-1, 1, 1), (1, 1, 1), (1, 1, -1))),
              ((0, 0, -1), ((-1, 0, -1), (-1, 1, -1), (1, 1, -1), (1, 0, -1))), ((0, 0, 1), ((-1, 0, 1), (1, 0, 1), (1, 1, 1), (-1, 1, 1))),
              ((-1, 0, 0), ((-1, 0, -1), (-1, 0, 1), (-1, 1, 1), (-1, 1, -1))), ((1, 0, 0), ((1, 0, -1), (1, 1, -1), (1, 1, 1), (1, 0, 1))))


def stack_mesh(name: str) -> tuple[list[tuple[float, float, float]], list[tuple[int, int, int]], list[tuple[int, int, int]]]:
    """n unit-wide boxes (x, z in -0.5..0.5; metres up) from y = 0, one per pitch: the MeshPart's box is the run's box.
    Returns vertices, triangles and each triangle's normal; every face has its own corners so the boxes shade flat (shared corners
    made Roblox smooth the AC boxes into shiny blobs, 2026-10-15)."""
    h, p, n = STACKS[name]
    verts: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int]] = []
    normals: list[tuple[int, int, int]] = []
    for i in range(n):
        y0 = i * p
        for nrm, corners in _BOX_FACES:
            o = len(verts)
            verts += [(sx / 2, y0 + sy * h, sz / 2) for sx, sy, sz in corners]
            faces += [(o, o + 1, o + 2), (o, o + 2, o + 3)]
            normals += [nrm, nrm]
    return verts, faces, normals


def stacks_obj(names: Sequence[str] | None = None) -> str:
    """One OBJ with an object per stack kit (Import 3D makes one MeshPart each), every object centred on its own box."""
    lines = ["# roblox-map column-stack kits (src/kits.py), metres"]
    lines += [f"vn {x} {y} {z}" for (x, y, z), _ in _BOX_FACES]
    base = 0
    for name in names or sorted(STACKS):
        verts, faces, normals = stack_mesh(name)
        top = max(v[1] for v in verts)
        lines.append(f"o {name}")
        lines += [f"v {x:.4f} {y - top / 2:.4f} {z:.4f}" for x, y, z in verts]
        nidx = {nrm: k + 1 for k, (nrm, _) in enumerate(_BOX_FACES)}
        lines += [f"f {a + base + 1}//{nidx[m]} {b + base + 1}//{nidx[m]} {c + base + 1}//{nidx[m]}" for (a, b, c), m in zip(faces, normals)]
        base += len(verts)
    return "\n".join(lines) + "\n"


def _fit(tail: str, n: int, pitch_m: float, h_m: float, ids: Mapping[str, int]) -> str | None:
    """The stack kit of this tail and length whose pieces land nearest the parts' places, if within STACK_TOL_M."""
    best = None
    for b, h, p in STACK_LOOKS[tail]:
        name = f"stk-{tail}{b}-{n}"
        if name not in ids:
            continue
        scale = ((n - 1) * pitch_m + h_m) / ((n - 1) * p + h)
        err = max(abs(h * scale - h_m), (n - 1) * abs(p * scale - pitch_m))
        if err <= STACK_TOL_M and (best is None or err < best[0]):
            best = (err, name)
    return best and best[1]


def stack_items(items: Sequence[Any], studs_per_m: float, ids: Mapping[str, int] | None = None) -> list[Any]:
    """Runs of the same piece one above the other at one pitch -> stack kit items (only kits in ids, default MESH_IDS)."""
    ids = MESH_IDS if ids is None else ids
    if not any(k.startswith("stk-") for k in ids):
        return list(items)
    groups: dict[tuple, list[Any]] = {}
    out: list[Any] = []
    for i in items:
        m = _TAIL.search(i.name)
        if m is None or i.kit is not None or i.shape != "Block" or i.tilt_x or i.tilt_z:
            out.append(i)
            continue
        key = (m[1], i.owner, i.kind, i.cx, i.cz, i.sx, i.sy, i.sz, i.yaw_deg, i.material, i.color, i.color_name, i.reflectance, i.transparency,
               i.shadow, i.collide)
        groups.setdefault(key, []).append(i)
    for key, rows in groups.items():
        rows.sort(key=lambda r: r.cy)
        runs: list[list[Any]] = [[rows[0]]]
        for r in rows[1:]:
            run = runs[-1]
            step = r.cy - run[-1].cy
            if step > r.sy + 1e-6 and (len(run) == 1 or abs(step - (run[1].cy - run[0].cy)) < 0.01):
                run.append(r)
            else:
                runs.append([r])
        for run in runs:
            k = 0
            while k < len(run):
                rest = len(run) - k
                pitch = (run[1].cy - run[0].cy) / studs_per_m if len(run) > 1 else 0.0
                kit = next((name for n in STACK_N if n <= rest for name in [_fit(key[0], n, pitch, run[0].sy / studs_per_m, ids)] if name), None)
                if kit is None:
                    out.append(run[k])
                    k += 1
                    continue
                n = STACKS[kit][2]
                lo, hi = run[k], run[k + n - 1]
                bottom, top = lo.cy - lo.sy / 2, hi.cy + hi.sy / 2
                out.append(dataclasses.replace(lo, name=f"{lo.name}x{n}", cy=round((bottom + top) / 2, 3), sy=round(top - bottom, 3), kit=kit))
                k += n
    return out


def main(argv: list[str]) -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if argv == ["trees"]:
        for name in CROWNS:
            path = OUT_DIR / f"{name}.obj"
            path.write_text(crown_obj(name), encoding="utf-8")
            print(f"-> {path}")
        return 0
    if argv == ["stacks"]:
        path = OUT_DIR / "stacks.obj"
        path.write_text(stacks_obj(), encoding="utf-8")
        print(f"{len(STACKS)} stack kits -> {path}")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
