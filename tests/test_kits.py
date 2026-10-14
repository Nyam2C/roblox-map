"""U7 H kit meshes: the crown OBJ faces outwards, its box matches the file, and a tree's crown item carries the kit key."""
from __future__ import annotations

import build_luau
import kits
import layout
import streets
import common


def obj(name):
    v, f = [], []
    for line in kits.crown_obj(name).splitlines():
        if line.startswith("v "):
            v.append(tuple(map(float, line.split()[1:])))
        elif line.startswith("f "):
            f.append(tuple(int(x) - 1 for x in line.split()[1:]))
    return v, f


def test_every_crown_face_points_out_and_the_box_is_the_file_size():
    for name in kits.CROWNS:
        v, f = obj(name)
        c = [sum(p[i] for p in v) / len(v) for i in range(3)]
        for a, b, d in f:
            A, B, C = v[a], v[b], v[d]
            u = [B[i] - A[i] for i in range(3)]
            w = [C[i] - A[i] for i in range(3)]
            n = (u[1] * w[2] - u[2] * w[1], u[2] * w[0] - u[0] * w[2], u[0] * w[1] - u[1] * w[0])
            assert sum(n[i] * ((A[i] + B[i] + C[i]) / 3 - c[i]) for i in range(3)) > 0
        size = kits.crown_box(name)[3]
        for i in range(3):
            assert max(p[i] for p in v) - min(p[i] for p in v) == size[i] or abs(max(p[i] for p in v) - min(p[i] for p in v) - size[i]) < 1e-3
        assert min(p[1] for p in v) == 0.0


def test_a_crown_item_becomes_a_kt_key_and_an_unknown_kit_refuses():
    frame = layout.Frame.from_cfg(common.DEFAULTS)
    crown = streets.tree_items(frame, [[0.0, 0.0, 7.0]])[1]
    text = build_luau.item_literal(crown, "8930e0af13bffff")
    assert f'kt="{crown.kit}"' in text and "p=" not in text
    bad = layout.Item(**{**crown.__dict__, "kit": "nope"})
    try:
        build_luau.item_literal(bad, "8930e0af13bffff")
    except ValueError:
        pass
    else:
        raise AssertionError("an unknown kit reached Luau")
