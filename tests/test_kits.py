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


S = 3.6
FAKE = {n: 1 for n in kits.STACKS}


def ac(k, pitch_m=2.8, x=10.0):
    return layout._item("facade", f"gis:7#aa0f{k}-1", "gis:7", k, (x, (k * pitch_m + 0.3) * S, 5.0), (0.85 * S, 0.6 * S, 0.4 * S), 30.0,
                        material="Metal", owner="gis:7", color_name="ac")


def test_a_column_of_15_ac_boxes_becomes_four_stacks_covering_the_same_span():
    run = [ac(k) for k in range(1, 16)]
    out = kits.stack_items(run + [ac(3, x=40.0)], S, FAKE)
    stacks = [i for i in out if i.kit]
    assert sorted(kits.STACKS[i.kit][2] for i in stacks) == [2, 4, 8] and len(out) == 5  # 8+4+2, one left as a part, the lone box stays
    lo = min(i.cy - i.sy / 2 for i in out if i.cx == 10.0)
    hi = max(i.cy + i.sy / 2 for i in out if i.cx == 10.0)
    assert abs(lo - (run[0].cy - run[0].sy / 2)) < 1e-6 and abs(hi - (run[-1].cy + run[-1].sy / 2)) < 2e-3
    for i in stacks:  # every box lands within the tolerance of its part
        h, p, n = kits.STACKS[i.kit]
        scale = i.sy / S / ((n - 1) * p + h)
        first = next(r for r in run if abs((r.cy - r.sy / 2) - (i.cy - i.sy / 2)) < 2e-3)
        k0 = run.index(first)
        for j in range(n):
            want = run[k0 + j].cy - run[k0 + j].sy / 2
            got = i.cy - i.sy / 2 + j * p * scale * S
            assert abs(got - want) / S <= kits.STACK_TOL_M + 1e-6


def test_no_uploaded_stack_leaves_the_parts_and_a_column_no_stack_fits_stays_parts():
    run = [ac(k) for k in range(1, 9)]
    assert kits.stack_items(run, S, {"crown-1": 1}) == run  # no stk- kit uploaded
    tall = [ac(k, pitch_m=5.0) for k in range(1, 9)]  # a 5 m pitch stretches the 0.6 m boxes past the tolerance
    assert kits.stack_items(tall, S, FAKE) == tall


def test_every_stack_face_points_out_and_has_its_own_corners():
    for name in kits.STACKS:
        v, f, nrm = kits.stack_mesh(name)
        assert len(v) == 2 * len(f)  # 4 corners per 2 triangles: no corner shared between faces
        for (a, b, c), m in zip(f, nrm):
            u = [v[b][i] - v[a][i] for i in range(3)]
            w = [v[c][i] - v[a][i] for i in range(3)]
            n = (u[1] * w[2] - u[2] * w[1], u[2] * w[0] - u[0] * w[2], u[0] * w[1] - u[1] * w[0])
            assert sum(n[i] * m[i] for i in range(3)) > 0
    text = kits.stacks_obj()
    assert text.count("\no stk-") == len(kits.STACKS)


def test_every_whole_tree_face_points_out_and_its_texture_spots_stay_in_its_column():
    for name in kits.TREES:
        v, f, uv = kits.tree_mesh(name)
        _, green = kits.TREES[name]
        assert len(uv) == len(v)
        trunk = 2 * kits.TREE_SIDES
        for i, (u, w) in enumerate(uv):
            col = 0 if i < trunk else 1 + green
            assert col / kits.TREE_COLS < u < (col + 1) / kits.TREE_COLS and 0 < w < 1
        c = [sum(p[i] for p in v[trunk:]) / len(v[trunk:]) for i in range(3)]
        for a, b, d in f[2 * kits.TREE_SIDES:]:  # the crown's faces point away from its centre
            A, B, C = v[a], v[b], v[d]
            u_ = [B[i] - A[i] for i in range(3)]
            w_ = [C[i] - A[i] for i in range(3)]
            n = (u_[1] * w_[2] - u_[2] * w_[1], u_[2] * w_[0] - u_[0] * w_[2], u_[0] * w_[1] - u_[1] * w_[0])
            assert sum(n[i] * ((A[i] + B[i] + C[i]) / 3 - c[i]) for i in range(3)) > -1e-9
    assert kits.trees_obj().count("\no tree-") + kits.trees_obj().startswith("o tree-") == len(kits.TREES)


def test_a_tree_is_one_kit_part_once_the_whole_trees_are_uploaded(monkeypatch):
    frame = layout.Frame.from_cfg(common.DEFAULTS)
    two = streets.tree_items(frame, [[0.0, 0.0, 7.0], [30.0, 0.0, 5.0]])
    assert len(two) == 4  # no whole-tree kit yet: trunk + crown
    monkeypatch.setitem(kits.MESH_IDS, "tree-1a", 1)
    for t in kits.TREES:
        monkeypatch.setitem(kits.MESH_IDS, t, 1)
    one = streets.tree_items(frame, [[0.0, 0.0, 7.0], [30.0, 0.0, 5.0]])
    assert len(one) == 2 and all(i.kit in kits.TREES and i.collides is False for i in one)
    # the same shape and green as before: the crown kit and leaf of the two-part tree
    for old_crown, new in zip(two[1::2], one):
        shape, green = kits.TREES[new.kit]
        assert shape == old_crown.kit and new.color_name == old_crown.color_name
