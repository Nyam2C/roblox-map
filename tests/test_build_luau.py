"""U2 build_luau: Luau text and the code-injection guard (SEC2), the plan, the files, same input same text (P2-8), run records."""
from __future__ import annotations

import json
import math
import random
import re
import sys

import h3
import pytest
from hypothesis import given, settings, strategies as st

import build_luau as B
import common
import db
import judgement
import layout
from generators import BASE, offset, rect, road_features

CELL = "8930e0af13bffff"
CFG = {**common.DEFAULTS, "chunk_size": 20}


def building(i, center=None, **kw):
    return {"building_id": f"gis:{1000 + i}", "cell_id": CELL, "source": "gis", "name": "", "floors_above": 3, "height_m": None,
            "outline": [list(p) for p in rect(center or offset(BASE, 30 * i, 0), 20, 15)], "status": "ok", **kw}


def row_for_db(b):
    return {"building_id": b["building_id"], "cell_id": b["cell_id"], "source": b["source"], "outline": b["outline"],
            "centroid": b["outline"][0], "gis_key": None, "osm_id": None, "name": b["name"], "osm_tags": None,
            "floors_above": b["floors_above"], "floors_below": None, "height_m": b["height_m"], "usability_code": None,
            "approval_date": None, "building_area": None, "osm_height_m": None, "osm_levels": None, "status": b["status"]}


CENTER = h3.cell_to_latlng(CELL)  # streets are built in the cell that holds their segment's middle, so put them well inside it


def street(fid="way:11", cls="tertiary", **tags):
    a, b = offset(CENTER, -60, 5), offset(CENTER, 60, 5)
    return {"feature_id": fid, "kind": "road", "highway_class": cls, "tags": tags, "geometry": [list(a), list(b)]}


def street_row(f):
    return {"feature_id": f["feature_id"], "cell_id": CELL, "kind": f["kind"], "highway_class": f["highway_class"],
            "geometry": f["geometry"], "tags": f["tags"]}


# --- Luau text -------------------------------------------------------------------------------------------

@given(st.text(max_size=120))
def test_luau_string_returns_only_safe_text_inside_plain_quotes(text):
    try:
        literal = B.luau_string(text)
    except ValueError:
        return
    assert literal == f'"{text}"' and B.SAFE_TEXT.fullmatch(text)
    assert all(c.isascii() and (c.isalnum() or c in ":#_.-") for c in text)


@pytest.mark.parametrize("text", ['gis:1"] os.exit() --', "a\nb", "a\\b", "a b", "]]", "한글", "", "x" * 101, 'a"b', "a'b", "a;b", "${x}"])
def test_luau_string_refuses_what_could_end_a_string_or_start_code(text):
    with pytest.raises(ValueError):
        B.luau_string(text)


def test_dashes_inside_the_quotes_are_just_text():
    assert B.luau_string("--x") == '"--x"'  # a comment marker cannot start a comment inside a string


@pytest.mark.parametrize("bad", [None, 12, b"abc", ["a"]])
def test_luau_string_refuses_non_text(bad):
    with pytest.raises(ValueError):
        B.luau_string(bad)


@given(st.floats(allow_nan=False, allow_infinity=False, min_value=-1e7, max_value=1e7))
def test_luau_number_is_plain_decimal_with_at_most_three_decimals(v):
    text = B.luau_number(v)
    assert re.fullmatch(r"-?\d+(\.\d{1,3})?", text) and text != "-0"
    assert float(text) == pytest.approx(v, abs=5.1e-4)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf"), True, "1", None])
def test_luau_number_refuses_what_is_not_a_finite_number(bad):
    with pytest.raises(ValueError):
        B.luau_number(bad)


def test_a_building_item_becomes_a_short_table_and_checks_its_cell():
    frame = layout.Frame.from_cfg(CFG)
    item, _ = layout.building_item(building(0, floors_above=5), frame, CFG)
    text = B.item_literal(item, CELL)
    assert text.startswith('{k="building",n="gis:1000",') and 's="gis"' in text and "f=5" in text and "q=" in text and "e=" in text
    assert "CellId" not in text and "BuildingId" not in text  # Builder takes them from the name and the cell
    with pytest.raises(ValueError, match="does not belong"):
        B.item_literal(item, "8930e0af123ffff")


def test_chunk_code_starts_the_cell_in_the_first_chunk_and_finishes_it_in_the_last():
    frame = layout.Frame.from_cfg(CFG)
    items = [layout.building_item(building(i), frame, CFG)[0] for i in range(2)]
    first, middle, last, only = (B.render_chunk(CELL, n, t, items) for n, t in ((1, 3), (2, 3), (3, 3), (1, 1)))
    assert "Builder.begin(CELL)" in first and "Builder.begin" not in middle + last
    assert "return added" in first and "return added" in middle and "return Builder.finish(CELL)" in last
    assert "Builder.begin(CELL)" in only and "return Builder.finish(CELL)" in only
    assert first.count('k="building"') == 2 and 'building={"Concrete",200,200,205}' in first


# --- the plan -----------------------------------------------------------------------------------------------

def every_quoted_text(files):
    for name, text in files.items():
        if name.endswith(".luau"):
            yield from re.findall(r'"([^"]*)"', text)


@settings(max_examples=60)
@given(st.lists(st.text(max_size=30), min_size=1, max_size=6))
def test_sec2_hostile_ids_never_reach_the_code(ids):
    buildings = [building(i, building_id=bid) for i, bid in enumerate(ids)]
    plan = B.plan_cell(CELL, buildings, [], CFG)
    for text in every_quoted_text(plan.files):
        assert B.SAFE_TEXT.fullmatch(text), text
    for name, text in plan.files.items():
        if name.endswith(".luau"):
            assert "\\" not in text and text.count('"') % 2 == 0
    built = {i.name for i in plan.items if i.kind == "building"}
    assert built == {bid for bid in ids if B.SAFE_TEXT.fullmatch(bid)}
    assert plan.counts["buildings_skipped"] == len(ids) - plan.counts["items_building"]


def test_a_hostile_building_id_is_skipped_with_a_warning_and_the_others_are_built():
    plan = B.plan_cell(CELL, [building(0), building(1, building_id='gis:2"] os.exit() --'), building(2)], [], CFG)
    assert plan.counts["items_building"] == 2 and plan.counts["buildings_skipped"] == 1
    assert any("not allowed in Luau code" in w for w in plan.warnings)
    assert "os.exit" not in "".join(t for n, t in plan.files.items() if n.endswith(".luau"))  # manifest.json is data and names what it skipped


def test_a_hostile_street_id_is_skipped_the_same_way():
    plan = B.plan_cell(CELL, [building(0)], [street("way:1"), street('way:2"; x()', "service")], CFG)
    assert plan.counts["items_road"] == 1 and any("way:2" in w for w in plan.warnings)
    assert "x()" not in "".join(t for n, t in plan.files.items() if n.endswith(".luau"))


def test_the_plan_counts_chunks_and_files_match_the_manifest():
    buildings = [building(i) for i in range(45)]
    plan = B.plan_cell(CELL, buildings, [street("way:1", "tertiary"), street("way:2", "residential")], CFG)
    manifest = json.loads(plan.files["manifest.json"])
    c = plan.counts
    assert c["items"] == sum(c[f"items_{k}"] for k in layout.ORDER) and c["items_ground"] == 1 and c["items_road"] == 2
    # the two streets lie on one line: the residential one's sidewalks fall inside the wider tertiary carriageway and are cut (2026-10-14)
    assert c["items_sidewalk"] == 2 and c["items_building"] == 45 and c["items_facade"] > 45
    assert c["chunks"] == math.ceil(c["items"] / 20) and sorted(k for k in plan.files if k.endswith(".luau")) == [f"chunk-{n:03d}.luau" for n in range(1, c["chunks"] + 1)]
    assert manifest["counts"] == c and manifest["cell_id"] == CELL
    assert manifest["files"] == {n: len(t.encode()) for n, t in plan.files.items() if n.endswith(".luau")}
    assert sum(len(re.findall(r'\{k="', t)) for n, t in plan.files.items() if n.endswith(".luau")) == c["items"]


def test_items_are_written_in_the_fixed_order_across_the_chunk_files():
    path = {**street("way:3", "footway"), "kind": "path"}
    spot = offset(CENTER, 0, 5)
    plan = B.plan_cell(CELL, [building(i) for i in (7, 2, 5)], [street("way:9", "tertiary"), path, street("way:1", "residential")],
                       {**CFG, "chunk_size": 4, "spawn_lat": spot[0], "spawn_lon": spot[1]})
    order = [m for n, t in sorted(plan.files.items()) if n.endswith(".luau") for m in re.findall(r'\{k="(\w+)",n="([^"]+)"', t)]
    ranks = [layout.ORDER[k] for k, _ in order]
    assert ranks == sorted(ranks) and order[0][0] == "ground" and order[-1][0] == "spawn"
    assert [k for k, _ in order if k in ("ground", "road", "path", "sidewalk", "building", "spawn")] == \
        ["ground", "road", "road", "sidewalk", "sidewalk", "building", "building", "building", "spawn"]  # way:1 and the footway lie inside way:9: cut
    assert [n for k, n in order if k == "building"] == ["gis:1002", "gis:1005", "gis:1007"] and [n for k, n in order if k == "road"] == ["way:1#0", "way:9#0"]


def test_poor_fit_buildings_are_listed_with_name_and_ratio():
    triangle = [list(offset(BASE, 0, 0)), list(offset(BASE, 30, 0)), list(offset(BASE, 0, 20))]
    plan = B.plan_cell(CELL, [building(0), building(1, outline=triangle, name="L자 학교")], [], CFG)
    poor = json.loads(plan.files["manifest.json"])["poor_fit"]
    assert [(p["building_id"], p["name"]) for p in poor] == [("gis:1001", "L자 학교")] and poor[0]["fit_ratio"] == pytest.approx(0.5, abs=1e-3)
    assert plan.counts["poor_fit"] == 1


def test_buildings_that_cannot_be_boxed_are_skipped_and_counted():
    plan = B.plan_cell(CELL, [building(0), building(1, outline=[[37.5, 126.78], [37.6, 126.8]])], [], CFG)
    assert plan.counts["buildings_in"] == 2 and plan.counts["buildings_skipped"] == 1 and plan.counts["items_building"] == 1
    assert any("gis:1001" in w for w in plan.warnings)


def test_underground_facilities_are_skipped_and_ordinary_basements_are_built():
    # a subway station (0 above, 2 below), a car park under a plaza (1 above, 4 below), an office with a deep basement (6 above, 7 below)
    rows = [building(0, floors_above=None, floors_below=2), building(1, floors_above=1, floors_below=4), building(2, floors_above=6, floors_below=7)]
    plan = B.plan_cell(CELL, rows, [], CFG)
    assert plan.counts["buildings_skipped"] == 2 and plan.counts["items_building"] == 1
    assert sum("underground" in w for w in plan.warnings) == 2


def test_without_a_spawn_point_there_is_a_warning_and_no_spawn_with_one_there_is_a_spawn():
    plain = B.plan_cell(CELL, [building(0)], [street()], CFG)
    assert plain.counts["items_spawn"] == 0 and any("no spawn point" in w for w in plain.warnings)
    spot = offset(CENTER, 0, 5)  # on the street
    with_spawn = B.plan_cell(CELL, [building(0)], [street()], {**CFG, "spawn_lat": spot[0], "spawn_lon": spot[1], "spawn_yaw_deg": 90})
    assert with_spawn.counts["items_spawn"] == 1 and not any("no spawn point" in w for w in with_spawn.warnings)
    assert 'k="spawn"' in "".join(with_spawn.files.values())


def test_a_chunk_file_over_ten_kilobytes_asks_for_a_smaller_chunk_size():
    plan = B.plan_cell(CELL, [building(i) for i in range(150)], [], {**CFG, "chunk_size": 150})
    assert any("lower chunk_size" in w for w in plan.warnings)


# --- P2-8 the same input gives the same text ------------------------------------------------------------------------------

@settings(max_examples=30)
@given(st.lists(road_features(max_points=4), max_size=4, unique_by=lambda f: f["feature_id"]), st.integers(0, 10**6))
def test_p2_8_row_order_and_repeats_do_not_change_a_single_character(features, seed):
    buildings = [building(i, name=f"b{i}") for i in range(8)]
    base = B.plan_cell(CELL, buildings, features, CFG)
    b2, f2 = list(buildings), list(features)
    rng = random.Random(seed)
    rng.shuffle(b2), rng.shuffle(f2)
    again = B.plan_cell(CELL, b2, f2, CFG)
    assert again.files == base.files and B.plan_cell(CELL, buildings, features, CFG).files == base.files
    assert not re.search(r"\d{4}-\d{2}-\d{2}T", "".join(base.files.values()))  # no timestamp is written into the files


# --- files and database ----------------------------------------------------------------------------------------------------------

def test_write_plan_writes_the_files_and_removes_chunk_files_of_an_earlier_longer_run(tmp_path):
    long = B.plan_cell(CELL, [building(i) for i in range(45)], [], CFG)
    B.write_plan(long, tmp_path)
    assert len(list((tmp_path / CELL).glob("chunk-*.luau"))) == long.counts["chunks"] > 3
    short = B.plan_cell(CELL, [building(0)], [], CFG)
    paths = B.write_plan(short, tmp_path)
    assert sorted(p.name for p in (tmp_path / CELL).iterdir()) == [f"chunk-{n:03d}.luau" for n in range(1, short.counts["chunks"] + 1)] + ["chunks.json", "manifest.json"]
    assert len(paths) == short.counts["chunks"] + 2 and short.counts["chunks"] < long.counts["chunks"]
    assert (tmp_path / CELL / "chunk-001.luau").read_text(encoding="utf-8") == short.files["chunk-001.luau"]
    data = json.loads(long.files["chunks.json"])  # the chunk files as data, read back from the Luau text
    assert len(data["chunks"]) == long.counts["chunks"] and data["building_ids"] == json.loads(long.files["manifest.json"])["building_ids"]
    assert {f"items_{k}": v for k, v in data["counts"].items()} == {k: v for k, v in long.counts.items() if k.startswith("items_") and v}


def make_db(buildings, features=()):
    conn = db.connect(":memory:")
    db.replace_cell_rows(conn, CELL, {"buildings": [row_for_db(b) for b in buildings], "street_features": [street_row(f) for f in features]})
    return conn


def test_build_cell_reads_the_database_and_ignores_other_kinds_and_not_ok_buildings(tmp_path):
    conn = make_db([building(0), building(1, status="invalid")], [street("way:1", "tertiary"),
                   {**street("way:2", "residential"), "kind": "crossing"}])
    plan = B.build_cell(conn, CFG, CELL, tmp_path)
    assert plan.counts["buildings_in"] == 1 and plan.counts["streets_in"] == 1 and plan.counts["items_sidewalk"] == 2
    assert (tmp_path / CELL / "manifest.json").is_file()


def test_a_cell_without_buildings_is_an_error_that_names_the_fix(tmp_path):
    with pytest.raises(ValueError, match="register.py"):
        B.build_cell(db.connect(":memory:"), CFG, CELL, tmp_path)


def run_main(monkeypatch, tmp_path, argv):
    monkeypatch.setattr(sys, "argv", ["build_luau.py", *argv])
    monkeypatch.setattr(B, "BUILD_DIR", str(tmp_path / "build"))
    return B.main({**CFG, "db_path": str(tmp_path / "map.db")})


def test_main_writes_files_and_records_a_run(monkeypatch, tmp_path):
    conn = db.connect(tmp_path / "map.db")
    db.replace_cell_rows(conn, CELL, {"buildings": [row_for_db(building(i)) for i in range(3)], "street_features": [street_row(street())]})
    conn.close()
    assert run_main(monkeypatch, tmp_path, ["--cells", CELL]) == 0
    assert (tmp_path / "build" / CELL / "chunk-001.luau").is_file()
    conn = db.connect(tmp_path / "map.db")
    unit, status, counts = conn.execute("SELECT unit, status, counts FROM collection_runs").fetchone()
    assert (unit, status) == ("C6", "ok") and json.loads(counts)["items_building"] == 3


def test_main_records_a_failed_cell_and_returns_one(monkeypatch, tmp_path):
    db.connect(tmp_path / "map.db").close()
    assert run_main(monkeypatch, tmp_path, ["--cells", CELL]) == 1
    conn = db.connect(tmp_path / "map.db")
    status, error = conn.execute("SELECT status, error FROM collection_runs").fetchone()
    assert status == "failed" and "register.py" in error


def test_the_command_line_rejects_bad_cell_ids_and_missing_cells(capsys):
    for argv in (["--cells", "nothex"], []):
        with pytest.raises(SystemExit) as e:
            B.parse_args(argv, 9)
        assert e.value.code == 2
    assert B.parse_args(["--selftest"], 9).selftest and B.parse_args(["--cells", CELL], 9).cells == [CELL]


# --- U4: final values reach the Luau text (BR-9) ------------------------------------------------------------------------------

def judged(bid, **kw):
    return {"building_id": bid, "floors_seen": 4, "confidence": "high", "height_est_m": None, "wall_color": "cream", "roof_shape": "gable",
            "views_used": [1], "note": None, **kw}


def test_u4_without_judgements_the_height_and_color_are_what_u2_made_before():
    frame = layout.Frame.from_cfg(CFG)
    for floors, height in ((3, None), (3, 10.2), (None, 12.0), (None, None), (5, 17.0)):
        b = building(0, floors_above=floors, height_m=height)
        old, _ = layout.building_item(b, frame, CFG)
        new, _ = layout.building_item(b, frame, CFG, judgement.effective_building(b, None, None, CFG))
        assert (new.sy, new.color, new.attrs["HeightM"]) == (old.sy, old.color, old.attrs["HeightM"]) and new.color == (200, 200, 205)
        assert new.attrs.get("Floors") == old.attrs.get("Floors") and new.attrs["Review"] == ("default_height-unjudged" if not floors and not height else "unjudged")


def test_u4_a_judgement_and_a_correction_change_height_color_and_attributes():
    b = building(0, floors_above=3, height_m=10.2)
    plan = B.plan_cell(CELL, [b], [], CFG, {b["building_id"]: judged(b["building_id"], floors_seen=4)},
                       {b["building_id"]: {"wall_color": "blue"}})
    (item,) = [i for i in plan.items if i.kind == "building"]
    assert item.attrs["HeightBasis"] == "from_floors" and item.attrs["FloorsBasis"] == "photo_count" and item.attrs["Floors"] == 4
    assert item.attrs["HeightM"] == pytest.approx(4 * 3.4, abs=1e-3) and item.attrs["WallColor"] == "blue" and item.attrs["Review"] == "changed"
    assert item.color == tuple(CFG["wall_colors"]["blue"])
    text = "".join(t for n, t in plan.files.items() if n.endswith(".luau"))
    assert 'b="from_floors"' in text and 'a="photo_count"' in text and 'c="blue"' in text and 'v="changed"' in text
    assert '["blue"]={110,140,180}' in text
    assert plan.counts["judged"] == 1 and plan.counts["flagged"] == 1


def test_u4_the_colors_of_a_chunk_are_sent_once_for_that_chunk_only():
    bs = [building(i) for i in range(3)]
    ests = {bs[0]["building_id"]: judged(bs[0]["building_id"], wall_color="pink"), bs[1]["building_id"]: judged(bs[1]["building_id"], wall_color="pink")}
    plan = B.plan_cell(CELL, bs, [], {**CFG, "chunk_size": 2}, ests)
    texts = [t for n, t in sorted(plan.files.items()) if n.endswith(".luau")]
    assert all(t.count('["pink"]') == (1 if 'c="pink"' in t else 0) for t in texts)  # a chunk sends a color once, and only when it uses it
    assert sum(t.count('["pink"]') for t in texts) >= 2 and all(t.count("walls=") == 1 for t in texts)
    plan = B.plan_cell(CELL, bs[2:], [], CFG)  # a chunk of buildings without a judgement still gets a table: light_gray is their color
    assert '["light_gray"]={200,200,205}' in "".join(plan.files.values())


def test_u4_a_hostile_text_from_the_judgement_never_reaches_the_code():
    b = building(0)
    bad = judged(b["building_id"], wall_color='x"]] os.exit() --')  # cannot come through record, but plan_cell must not trust it either
    plan = B.plan_cell(CELL, [b, building(1)], [], CFG, {b["building_id"]: bad})
    assert plan.counts["items_building"] == 1 and plan.counts["buildings_skipped"] == 1
    assert any("not allowed in Luau code" in w for w in plan.warnings)
    assert "os.exit" not in "".join(t for n, t in plan.files.items() if n.endswith(".luau"))


@settings(max_examples=25)
@given(st.randoms(use_true_random=False), st.integers(1, 4))
def test_u4_p2_8_same_text_whatever_the_order_of_buildings_judgements_and_corrections(rnd, n):
    bs = [building(i, floors_above=2 + i) for i in range(6)]
    ests = {b["building_id"]: judged(b["building_id"], floors_seen=3 + (i % n), wall_color=["cream", "pink", None][i % 3]) for i, b in enumerate(bs[:4])}
    ovs = {bs[1]["building_id"]: {"height_m": 21.5}, bs[5]["building_id"]: {"wall_color": "green", "floors_above": 9}}
    first = B.plan_cell(CELL, bs, [], CFG, ests, ovs)
    shuffled = list(bs)
    rnd.shuffle(shuffled)
    again = B.plan_cell(CELL, shuffled, [], CFG, dict(rnd.sample(sorted(ests.items()), len(ests))), dict(rnd.sample(sorted(ovs.items()), len(ovs))))
    assert first.files == again.files


def test_u4_build_cell_reads_judgements_and_corrections_from_the_database(tmp_path):
    conn = db.connect(":memory:")
    db.replace_cell_rows(conn, CELL, {"buildings": [row_for_db(building(i)) for i in range(2)]})
    db.upsert_building_views(conn, [{"building_id": "gis:1000", "rank": 1, "pano_id": None, "distance_m": 1.0, "bearing_deg": 0.0, "yaw_deg": 0.0,
                                     "fov_deg": 90.0, "pitch_deg": 0.0, "crop_path": "x.jpg", "status": "cropped", "face_deg": None,
                                     "target_lat": None, "target_lon": None}])
    db.record_judgements(conn, CFG, [judged("gis:1000", floors_seen=5, views_used=[1])], "2026-10-13T00:00:00+00:00")
    db.set_override(conn, CFG, "gis:1001", "height_m", 30.0, "checked", "2026-10-13T00:00:00+00:00")
    plan = B.build_cell(conn, CFG, CELL, tmp_path)
    heights = {i.name: i.attrs["HeightM"] for i in plan.items if i.kind == "building"}
    assert heights == {"gis:1000": pytest.approx(17.0), "gis:1001": 30.0}
    assert plan.counts["judged"] == 1 and (tmp_path / CELL / "manifest.json").is_file()


def test_a_sign_literal_carries_its_max_distance_as_md_and_one_x_only():
    """The SurfaceGui MaxDistance key is `md`; `x` is the position (mutation B1, the key clash seen in the smoke test)."""
    from layout import Item
    item = Item(kind="sign", name="gis:1#sg0", group="gis:1", seq=1, cx=1.0, cy=2.0, cz=3.0, sx=4.0, sy=1.0, sz=0.1, yaw_deg=0.0,
                material="SmoothPlastic", color=(255, 255, 255), attrs={"MaxDistance": 300}, owner="gis:1", color_name="sign_white",
                text="한솔약국", ink="ink_black", faces="F")
    lit = B.item_literal(item, "8930e0af13bffff")
    assert "md=300" in lit and lit.count("x=") == 1 and 't="한솔약국"' in lit


def test_an_empty_record_judged_a_skybridge_is_a_raised_deck_and_a_house_stays_a_house():
    long_thin = [list(p) for p in rect(offset(BASE, 0, 0), 40, 4)]
    shed = [list(p) for p in rect(offset(BASE, 0, 60), 40, 4)]
    rows = [building(0, floors_above=None, outline=long_thin), building(1, floors_above=None, outline=shed)]
    note = {"floors_seen": None, "confidence": "low", "height_est_m": 8.0, "wall_color": None, "roof_shape": None, "views_used": [1]}
    est = {"gis:1000": {**note, "note": "elevated pedestrian skybridge over the road"}, "gis:1001": {**note, "note": "a long shed"}}
    plan = B.plan_cell(CELL, rows, [], CFG, est)
    assert plan.counts["items_building"] == 1  # the shed is still a building
    deck = [i for i in plan.items if i.name == "gis:1000#dk0"]
    assert len(deck) == 1 and (deck[0].cy - deck[0].sy / 2) / CFG["studs_per_m"] == pytest.approx(5.5, abs=0.01) and deck[0].collide


def test_a_satellite_tree_on_a_carriageway_is_left_out():
    # 10b, 2026-10-14: trees.py masks roads by its own width, so crowns on a widened road or a junction stood on the asphalt
    frame = layout.Frame.from_cfg(CFG)
    on = layout.to_studs(frame, *offset(CENTER, 10, 5))
    off = layout.to_studs(frame, *offset(CENTER, 10, 45))
    def trees(features):
        plan = B.plan_cell(CELL, [building(0)], features, CFG, sat_trees=[[*on, 6.0], [*off, 6.0]])
        return len(re.findall(r'sat#\d+#tree"', "".join(t for n, t in plan.files.items() if n.endswith(".luau"))))
    assert trees([]) == 2 and trees([street("way:1")]) == 1


def test_an_osm_only_outline_the_photos_show_empty_is_not_built():
    # 16b, 2026-10-14: an OSM building on what is now a fenced empty lot stood as a big box
    empty = {"floors_seen": None, "height_est_m": None, "note": "vacant fenced lot with grass and trees; no building visible"}
    osm, gis = building(0, source="osm"), building(1)
    plan = B.plan_cell(CELL, [osm, gis], [street("way:1")], CFG, estimates={osm["building_id"]: empty, gis["building_id"]: empty})
    assert plan.counts["items_building"] == 1 and any("OSM-only" in w for w in plan.warnings)
    plan = B.plan_cell(CELL, [osm, gis], [street("way:1")], CFG, estimates={osm["building_id"]: {**empty, "floors_seen": 1}})
    assert plan.counts["items_building"] == 2
