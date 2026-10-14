"""U5 details_rules: the vocabulary (BR-7.1), the export file (P5-16 format), note keywords and merging (P5-8), archetypes (P5-4),
sign text and fictional names (P5-10), the palette and materials (P5-17)."""
from __future__ import annotations

import json
import re

import pytest
from hypothesis import given, settings, strategies as st

import common
import details_rules as R
from generators import SIGN_TEXTS, WALL_NAMES, detail_rows, notes

CFG = common.DEFAULTS
TIMES = st.builds("2026-10-{:02d}T{:02d}:{:02d}:{:02d}+00:00".format, st.integers(1, 28), st.integers(0, 23), st.integers(0, 59), st.integers(0, 59))


# --- vocabulary and validation (BR-7.1, BR-7.4) ---------------------------------------------------------------------

@given(detail_rows())
def test_a_row_in_the_vocabulary_is_accepted_and_normalized(row):
    out = R.validate_detail(row)
    assert set(out) == set(R.RECORD_KEYS) and out["building_id"] == row["building_id"]
    for f in R.DETAIL_FIELDS:
        assert out[f] == row[f]
    assert out["note"] == ((row["note"].strip() or None) if row["note"] else None)


@pytest.mark.parametrize("bad", [
    {"building_id": "gis:1", "finish": "wood"}, {"building_id": "gis:1", "bay": True}, {"building_id": "gis:1", "bay": 2},
    {"building_id": "gis:1", "mystery": 1}, {"building_id": 'gis:1"', "finish": "brick"}, {"building_id": "gis:1", "note": "x" * 301},
    {"building_id": "gis:1", "note": "a\x00b"}, {"finish": "brick"}, "not a row", {"building_id": "gis:1", "stair": 1}])
def test_rows_outside_the_vocabulary_are_refused(bad):
    with pytest.raises(ValueError):
        R.validate_detail(bad)


# --- export file (P5-16 format) ----------------------------------------------------------------------------------------

@settings(max_examples=40)
@given(st.lists(st.tuples(st.integers(1, 50), detail_rows(), TIMES), max_size=6, unique_by=lambda t: t[0]), st.randoms(use_true_random=False))
def test_p5_16_the_export_file_round_trips_and_does_not_depend_on_the_row_order(rows, rnd):
    stored = [{**R.validate_detail({**r, "building_id": f"gis:{i}"}), "judged_at": t} for i, r, t in rows]
    text = R.export_details_payload("8930e0af13bffff", stored)
    cell, back = R.parse_details_export(text)
    assert cell == "8930e0af13bffff" and back == sorted(stored, key=lambda r: r["building_id"])
    shuffled = list(stored)
    rnd.shuffle(shuffled)
    assert R.export_details_payload("8930e0af13bffff", shuffled) == text
    data = json.loads(text)
    assert list(data) == sorted(data) and all(list(r) == sorted(r) for r in data["details"])


@pytest.mark.parametrize("text", ['{"version": 2, "cell_id": "8930e0af13bffff", "details": []}', '{"cell_id": "8930e0af13bffff", "details": []}',
                                  '{"version": 1, "cell_id": "nothex", "details": []}', '{"version": 1, "cell_id": "8930e0af13bffff", "details": {}}',
                                  '{"version": 1, "cell_id": "8930e0af13bffff", "details": [{"building_id": "gis:1"}]}', "not json"])
def test_a_bad_export_file_is_refused_as_a_whole(text):
    with pytest.raises(ValueError):
        R.parse_details_export(text)


def test_a_duplicate_building_in_the_file_is_refused():
    row = {**R.validate_detail({"building_id": "gis:1", "finish": "brick"}), "judged_at": "2026-10-13T00:00:00Z"}
    with pytest.raises(ValueError, match="twice"):
        R.parse_details_export(R.export_details_payload("8930e0af13bffff", [row, row]))


# --- note keywords and merging (BR-7.2, BR-7.3, P5-8) -------------------------------------------------------------------

@pytest.mark.parametrize("note, expect", [
    ("two storey brick house", {}), ("dark brick shop house", {"ground_use": "shop"}), ("a convenience store on the ground floor", {"ground_use": "shop"}),
    ("house with a glass stair tower and bay windows", {"stair": "glass", "bay": 1}), ("balconies on every floor", {"balcony": 1}),
    ("garage on the ground floor", {"ground_use": "garage"}), ("roof terrace railing", {"rooftop": "railing"}), ("solar panels", {"rooftop": "tank"}),
    ("orange brick house with a green tiled roof", {"roof_color": "green"}), ("red roof", {"roof_color": "red"}), ("brown roof", {"roof_color": "brown"}),
    ("Shops and a Cafe", {"ground_use": "shop"}), ("", {}), (None, {})])
def test_note_keywords_are_word_bounded_and_case_insensitive(note, expect):
    assert R.from_note(note) == expect


@settings(max_examples=60)
@given(detail_rows(), notes(), st.sampled_from(WALL_NAMES), st.sampled_from(["villa", "commercial", "public", "school"]))
def test_p5_8_judged_values_win_then_notes_then_defaults(detail, note, wall, archetype):
    merged = R.merged_details(detail, note, wall, archetype)
    hints = R.from_note(note)
    for f in R.DETAIL_FIELDS:
        if archetype == "commercial" and f == "ground_use":  # BR-9.1: a shop unless the judgement (row, else note) says house or garage
            judged = detail[f] if detail[f] is not None else hints.get(f)
            assert merged[f] == (judged if judged in ("house", "garage") else "shop")
        elif detail[f] is not None:
            assert merged[f] == detail[f]
        elif f in hints:
            assert merged[f] == hints[f]
        elif f == "finish":
            assert merged[f] == R.default_finish(wall, archetype)
        else:
            assert merged[f] == R.DEFAULT_DETAILS[f]
    assert merged == R.merged_details(detail, note, wall, archetype)  # pure


@settings(max_examples=40)
@given(notes(), st.sampled_from(WALL_NAMES), st.sampled_from(["villa", "public"]))
def test_p5_8_no_row_equals_an_all_empty_row_and_a_judged_row_ignores_the_note(note, wall, archetype):
    empty = {"building_id": "gis:1", **{f: None for f in R.DETAIL_FIELDS}, "note": None}
    assert R.merged_details(None, note, wall, archetype) == R.merged_details(empty, note, wall, archetype)
    full = {"building_id": "gis:1", "finish": "stone", "ground_use": "garage", "stair": "round", "bay": 0, "balcony": 0, "roof_color": "pink", "rooftop": "box", "note": None}
    assert R.merged_details(full, note, wall, archetype) == R.merged_details(full, "shop stair bay balcony solar red roof", wall, archetype)


def test_default_finish_follows_the_wall_color_table():
    assert R.default_finish("red_brick", "villa") == "brick" and R.default_finish("beige", "commercial") == "stone"
    assert R.default_finish("light_gray", "villa") == "tile" and R.default_finish("light_gray", "commercial") == "panel"
    assert R.default_finish("white", "villa") == "tile" and R.default_finish("white", "public") == "paint"
    assert R.default_finish("pink", "villa") == "paint" and R.default_finish("other", "villa") == "panel"


# --- archetypes and public names (BR-1.5, BR-1.6, P5-4) ------------------------------------------------------------------

@pytest.mark.parametrize("code, floors, name, in_poly, expect", [
    ("01000", 3, "", False, "villa"), ("01000", 5, "", False, "commercial"), ("14000", 2, "", False, "commercial"), ("09000", 8, "", False, "commercial"),
    ("10000", 7, "로얄프라자", False, "commercial"), ("10000", 1, "옥산경로당", False, "public"), ("03000", 2, "행정복지센터", False, "public"),
    ("10000", 5, "부흥중학교", False, "school"), ("", 5, "", True, "school"), (None, None, "", False, "villa"), ("", 2, "", False, "villa"),
    ("02000", 20, "1004동", False, "apartment"), ("02000", 4, "", False, "villa"), ("02000", 5, "한빛학교", False, "school"),
    ("07000", 11, "", False, "store"), ("07000", 3, "", False, "villa"), ("20000", 6, "중동 공영노외주차장(6호)", False, "public"),
    ("20000", 2, "", False, "villa"), ("06000", 5, "순복음교회", False, "public")])
def test_archetype_is_school_then_commercial_then_public_then_villa(code, floors, name, in_poly, expect):
    assert R.archetype(code, floors, name, in_poly) == expect


def test_public_names_end_with_a_known_suffix():
    assert R.is_public_name("심원고등학교") and R.is_public_name("중3동행정복지센터") and R.is_public_name("옥산경로당") and R.is_public_name("중3동 주민센터")
    assert not R.is_public_name("중동샛별") and not R.is_public_name("") and not R.is_public_name(None)


# --- sign text (BR-10.4, P5-10) --------------------------------------------------------------------------------------------

@given(SIGN_TEXTS)
def test_sign_string_keeps_the_text_as_is_inside_plain_quotes(text):
    literal = R.sign_string(text)
    assert literal == f'"{text}"' and "\\" not in literal and literal.count('"') == 2
    assert all(0x80 <= b or chr(b) in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 \"" for b in literal.encode("utf-8"))


@pytest.mark.parametrize("bad", ['a"b', "a\\b", "a\nb", "", "x" * 13, "漢字", "かな", "😀", "한글!", "한글-", None, 12])
def test_sign_string_refuses_what_is_not_hangul_latin_digits_or_spaces(bad):
    with pytest.raises(ValueError):
        R.sign_string(bad)


# --- fictional names (BR-10.3, P5-10) ---------------------------------------------------------------------------------------

HANGUL = re.compile(r"[가-힣]+")


def test_the_name_tables_hold_no_brand_or_place_name():
    for prefix in R.PREFIXES:
        for pool, words in R.POOLS.items():
            for word in words:
                name = prefix + word
                assert HANGUL.fullmatch(name) and 2 <= len(name) <= 9, name
                assert not any(b in name for b in R.REAL_BRANDS), name
                assert not any(p in name for p in R.PLACE_NAMES), name
    assert len(R.PREFIXES) == 40 and len(set(R.PREFIXES)) == 40


@given(st.integers(1, 10**7), st.sampled_from(["0", "1", "f2-1", "p0", "r", "n"]), st.sampled_from(sorted(R.POOLS)))
def test_p5_10_a_name_is_hangul_ends_with_a_trade_word_and_is_fixed_by_owner_and_slot(i, slot, pool):
    name = R.sign_name(f"gis:{i}", slot, pool)
    assert HANGUL.fullmatch(name) and 2 <= len(name) <= 9 and any(name.endswith(w) for w in R.POOLS[pool])
    assert name == R.sign_name(f"gis:{i}", slot, pool) and R.SIGN_TEXT.fullmatch(name)


def test_p5_10_ten_thousand_owners_give_hundreds_of_different_names():
    assert len({R.sign_name(f"gis:{i}", "0", "villa_gf") for i in range(10_000)}) >= 300


def test_pools_follow_archetype_code_and_floor():
    assert R.pool_for("villa", "01000", 0, "gf") == "villa_gf" and R.pool_for("commercial", "14000", 0, "gf") == "com_gf"
    assert R.pool_for("commercial", "14000", 2, "upper") == "upper" and R.pool_for("commercial", "09000", 0, "gf") == "medical"
    assert R.pool_for("commercial", "11000", 3, "upper") == "care" and R.pool_for("commercial", "14000", 0, "roof") == "building"
    assert R.pool_for("public", "10000", 0, "plate") == "care"


@given(st.text(max_size=20), st.text(max_size=10), st.integers(1, 1000))
def test_pick_is_deterministic_and_in_range(name, purpose, n):
    v = R.pick(name, purpose, n)
    assert 0 <= v < n and v == R.pick(name, purpose, n)
    with pytest.raises(ValueError):
        R.pick(name, purpose, 0)


# --- palette, materials, dimensions (P5-17) --------------------------------------------------------------------------------------

def test_palette_names_and_materials_are_valid():
    for name, rgb in R.PALETTE.items():
        assert re.fullmatch(r"[a-z_]{1,20}", name) and len(rgb) == 3 and all(0 <= c <= 255 for c in rgb)
    for bg, ink in R.SIGN_PAIRS:
        assert bg in R.PALETTE and ink in R.PALETTE
    for material, key in R.ROOF_MATERIALS.values():
        assert material in R.MATERIALS and key in R.PALETTE
    for finish in R.VOCAB["finish"]:
        for wall in WALL_NAMES:
            assert R.wall_material(finish, wall) in R.MATERIALS
    assert len(R.MATERIALS) == 45 and set(R.SHAPES) == {"Block", "Wedge", "CornerWedge", "Cylinder", "Ball"}


@given(st.tuples(st.integers(0, 255), st.integers(0, 255), st.integers(0, 255)))
def test_p5_17_the_band_color_is_darker_than_the_wall_on_every_channel(rgb):
    band = R.band_color(rgb)
    assert all(0 <= b <= c for b, c in zip(band, rgb)) and band == R.band_color(rgb)


def test_dimensions_are_positive_numbers():
    assert all(isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0 for v in R.DIMS.values())


def test_a_small_shop_block_judged_with_shops_is_not_a_public_building():
    # 147·17b street view 2026-10-14: 03000 rows of small shops came out as plain public blocks
    shop, house = {"ground_use": "shop"}, {"ground_use": "house"}
    assert R.shop_house("03000", "미리내마을", shop) and not R.shop_house("03000", "미리내마을", house)
    assert not R.shop_house("03000", "중앙행정복지센터", shop) and not R.shop_house("10000", "", shop) and not R.shop_house("03000", "", None)
