"""U7 K sign image reuse: P7-11 a reused image has the sign's tail, panel color and an aspect within 12 %; every sign of the
building's name then reads the image's text; the cell's own image wins; no library changes nothing."""
from __future__ import annotations

import math

from hypothesis import given, settings
from hypothesis import strategies as st

import build_luau
import details_rules as R
import layout


def sign(owner, tail, text, w=10.0, h=1.0, bg="sign_blue", ink="ink_white"):
    return layout.Item("sign", f"{owner}#{tail}0", owner, 0, 0, 0, 0, w, h, 0.2, 0, "SmoothPlastic", (0, 0, 0), {}, owner=owner,
                       color_name=bg, text=text, ink=ink)


def row(text, tail="sg", aspect="10.0", bg="sign_blue", ink="ink_white", asset=7):
    return {"key": R.sign_image_key(text, tail, bg, ink, aspect), "asset_id": asset, "text": text, "tail": tail, "bg": bg, "ink": ink,
            "aspect": aspect}


LIB = [row("새봄김밥", asset=1), row("행복약국", aspect="10.5", asset=2), row("푸른마트", tail="sgf", asset=3), row("한빛카페", bg="sign_red", asset=4),
       row("멀리간판", aspect="15.0", asset=5)]


@settings(max_examples=60)
@given(st.floats(6, 16), st.sampled_from(["sg", "sgf"]), st.sampled_from(["sign_blue", "sign_red"]), st.text("가나다라", min_size=1, max_size=4))
def test_p7_11_a_reused_image_has_the_tail_color_and_a_near_aspect(w, tail, bg, owner):
    items = [sign(f"gis:{owner}", tail, "옛이름치킨", w=w, bg=bg), sign(f"gis:{owner}", "pl", "옛이름치킨", bg=bg)]
    out, n_img, reused = build_luau.apply_sign_images(items, {}, LIB)
    assert n_img == reused
    if n_img:
        r = next(r for r in LIB if r["asset_id"] == out[0].attrs["ImageAsset"])
        assert (r["tail"], r["bg"]) == (tail, bg)
        assert abs(math.log(float(r["aspect"]) / float(R.aspect_bucket(w, 1.0)))) <= math.log(1.12) + 1e-9
        assert out[0].text == out[1].text == r["text"]  # the plate of the same name follows
    else:
        assert [i.text for i in out] == ["옛이름치킨"] * 2


def test_the_cells_own_image_wins_and_keeps_the_name():
    own = sign("gis:1", "sg", "새봄김밥", w=10.0)
    other = sign("gis:2", "sg", "다른가게", w=10.0)
    out, n_img, reused = build_luau.apply_sign_images([own, other], {}, LIB)
    assert out[0].text == "새봄김밥" and out[0].attrs["ImageAsset"] == 1
    assert n_img == 2 and reused == 1 and out[1].text in ("새봄김밥", "행복약국")


def test_reuse_is_deterministic_and_no_library_leaves_text_signs():
    items = [sign(f"gis:{k}", "sg", "옛가게", w=10.0) for k in range(20)]
    a = build_luau.apply_sign_images(items, {}, LIB)
    b = build_luau.apply_sign_images(items, {}, LIB)
    assert [(i.text, i.attrs.get("ImageAsset")) for i in a[0]] == [(i.text, i.attrs.get("ImageAsset")) for i in b[0]]
    assert len({i.text for i in a[0]}) == 2  # both blue 10-ish images get used
    out, n_img, reused = build_luau.apply_sign_images(items, {}, [])
    assert (n_img, reused) == (0, 0) and all(i.text == "옛가게" and "ImageAsset" not in i.attrs for i in out)


def test_the_library_refuses_a_row_whose_key_does_not_match(tmp_path, monkeypatch):
    import json
    cells = tmp_path / "r" / "cells" / "8930e0af13bffff"
    cells.mkdir(parents=True)
    r = row("새봄김밥")
    bad = {**r, "text": "바뀐글자"}
    (cells / "signs.json").write_text(json.dumps({"signs": {r["key"]: bad}}), encoding="utf-8")
    monkeypatch.setattr(build_luau.common, "region_of", lambda cfg, cell: (tmp_path / "r", {}))
    try:
        build_luau.load_sign_library({}, "8930e0af13bffff")
    except ValueError as e:
        assert "does not match" in str(e)
    else:
        raise AssertionError("a tampered row was accepted")
