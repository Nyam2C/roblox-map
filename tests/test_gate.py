"""U8 gate.py: placement over chunk items (G1), the Studio check's answer, satellite tiles (G2), the frame rate and the summary."""
from __future__ import annotations

import json

import pytest
from hypothesis import given, settings, strategies as st

import build_luau as B
import gate as G
import kits
import layout
import streets
from generators import offset
from test_build_luau import CELL, CENTER, CFG, building, street

GATE = G.load_gate()  # the repository's gate.toml: the tests hold the thresholds the gate really uses
S = float(CFG["studs_per_m"])
NEXT = "8930e0af12bffff"  # a neighbour of CELL


def road(n="way:1#0", x=0.0, z=0.0, length=200.0, width=24.0, r=0.0, lift=0.0, top=0.2):
    return {"k": "road", "n": n, "x": x, "y": lift + top / 2, "z": z, "w": length, "h": top, "d": width, "r": r}


def box(k, n, x, z, w, d, h, bottom=0.0, r=0.0, **extra):
    return {"k": k, "n": n, "x": x, "y": bottom + h / 2, "z": z, "w": w, "h": h, "d": d, "r": r, **extra}


def post(n, x, z, height=25.0, dia=0.8):
    """A standing cylinder as the chunks hold it: X is its height (BR-14.3)."""
    return {"k": "prop", "n": n, "x": x, "y": height / 2, "z": z, "w": height, "h": dia, "d": dia, "r": 0.0, "p": "Cylinder"}


def as_chunk(i: layout.Item) -> dict:
    d = {"k": i.kind, "n": i.name, "x": i.cx, "y": i.cy, "z": i.cz, "w": i.sx, "h": i.sy, "d": i.sz, "r": i.yaw_deg}
    if i.kit:
        d["kt"] = i.kit
    if i.shape != "Block":
        d["p"] = i.shape
    return d


def check(items, around=(), allow=None):
    return G.placement(items, list(around), GATE["g1"], S, allow)


def failing(out):
    return {k: out["checks"][k]["n"] for k in out["fail"]}


# --- G1 placement ------------------------------------------------------------------------------------------

def test_a_tidy_street_passes():
    items = [road(), box("sidewalk", "way:1#0L.0", 0, 16.5, 200, 9, 0.4), box("sidewalk", "way:1#0R.0", 0, -16.5, 200, 9, 0.4),
             post("way:1#0#lamp0", 10, 14.5), post("sat#0#tree", -30, 20, 9, 1.4), box("prop", "way:1#0#cl0", 0, 0, 190, 0.5, 0.05, 0.2),
             box("prop", "j:1#cw0-0", 50, 0, 2, 10, 0.05, 0.2), box("prop", "way:1#0#lhead0", 10, 10, 2, 1, 0.5, 25)]
    out = check(items)
    assert out["pass"] and out["fail"] == [], failing(out)
    assert all(out["checks"][k]["n"] == 0 for k in G.G1_CHECKS)


def test_a_building_on_the_carriageway_fails_and_a_corner_touch_does_not():
    on = box("building", "gis:1", 0, 0, 72, 54, 40)
    touch = box("building", "gis:2", 60, 12 + 27 - 1, 2, 54, 40)  # 2 x 1 studs over the edge: 0.15 m²
    out = check([road(), on, touch])
    assert out["fail"] == ["buildings_on_road"]
    assert [f["id"] for f in out["checks"]["buildings_on_road"]["items"]] == ["gis:1"]
    assert check([road(), touch])["pass"]


def test_one_small_overlap_is_allowed_and_two_are_not():
    def nick(n, x):  # 1 stud deep, 6.5 studs along: 0.5 m² of carriageway
        return box("building", n, x, 12 + 20 - 1, 6.5, 40, 30)
    assert check([road(), nick("gis:1", 0)])["pass"]
    out = check([road(), nick("gis:1", 0), nick("gis:2", 40)])
    assert out["fail"] == ["buildings_on_road"] and out["checks"]["buildings_on_road"]["n"] == 2


def test_boxes_of_one_building_count_as_that_building():
    out = check([road(), box("building", "gis:7#b0", 0, 0, 20, 20, 30, i="gis:7"), box("building", "gis:7#b1", 40, 0, 20, 20, 30, i="gis:7")])
    assert [f["id"] for f in out["checks"]["buildings_on_road"]["items"]] == ["gis:7"]


def test_an_overpass_passes_over_a_low_building_but_not_through_a_tall_one():
    deck = road(lift=30.0)
    assert check([deck, box("building", "gis:1", 0, 0, 40, 40, 20)])["pass"]
    assert check([deck, box("building", "gis:1", 0, 0, 40, 40, 60)])["fail"] == ["buildings_on_road"]


def test_a_trunk_on_the_carriageway_fails_and_one_in_the_edge_band_passes():
    assert check([road(), post("sat#3#tree", 0, 0, 9, 1.4)])["fail"] == ["trees_on_road"]
    assert check([road(), post("sat#3#tree", 0, 12 - 0.5, 9, 1.4)])["pass"]  # half a stud inside the edge: inside edge_m
    assert check([road(), post("way:1#0#treeL2", 0, 5, 9, 1.4)])["fail"] == ["trees_on_road"]


def test_a_crown_over_the_road_is_not_a_tree_on_the_road():
    crown = box("prop", "sat#3#crown", 0, 8, 20, 20, 14, 7, kt="crown-a")
    assert check([road(), crown, post("sat#3#tree", 0, 20, 9, 1.4)])["pass"]


@settings(max_examples=60)
@given(st.floats(-2000, 2000), st.floats(-2000, 2000), st.floats(1.0, 14.0))
def test_trunk_finds_where_a_satellite_tree_stands(x, z, dia):
    frame = layout.Frame.from_cfg(CFG)
    items = [as_chunk(i) for i in streets.tree_items(frame, [[x, z, dia]])]
    trunks = [i for i in items if G.TREE.match(G.tail(i["n"]))]
    assert len(trunks) == 1
    tx, tz = G.trunk(trunks[0], S)
    assert tx == pytest.approx(x, abs=0.05) and tz == pytest.approx(z, abs=0.05)


def test_whole_tree_kits_are_what_the_trunk_math_undoes():
    assert all(t in kits.MESH_IDS for t in kits.TREES)  # tree_items makes whole-tree kits only when every one is uploaded


def test_posts_on_the_carriageway_fail_and_what_belongs_there_does_not():
    out = check([road(), post("way:1#0#lamp0", 0, 0), post("j:1#bol0-1", 30, 3, 3, 0.6)])
    assert out["fail"] == ["props_on_road"] and out["checks"]["props_on_road"]["n"] == 2
    belongs = [box("prop", "way:1#0#cl0", 0, 0, 190, 0.5, 0.05, 0.2), box("prop", "way:1#0#dash3", 0, 3, 10, 0.5, 0.05, 0.2),
               box("prop", "way:1#0#rampup", 20, 0, 4, 8, 1.5, 0.2), box("prop", "way:1#0#larm0", 0, 0, 1, 5, 0.3, 25),
               box("prop", "way:1#0#deck", 0, 0, 200, 26, 4, -4), box("prop", "way:1#0#pier2", 0, 0, 4, 10, 30, -4),
               box("prop", "j:1#sl0", 0, 0, 1, 12, 0.05, 0.2), box("prop", "way:1#wire0-1", 0, 0, 100, 0.1, 0.1, 22)]
    assert check([road(), *belongs])["pass"]


def test_a_sidewalk_on_another_roads_carriageway_fails_and_its_own_bend_is_a_warning():
    cross = road("way:2#0", r=90.0)
    walk = box("sidewalk", "way:1#0L.0", 0, 16.5, 200, 9, 0.4)
    out = check([road(), cross, walk])
    assert out["fail"] == ["sidewalks_on_road"]
    assert out["checks"]["sidewalks_on_road"]["items"][0]["roads"] == ["way:2"]
    bend = box("sidewalk", "way:1#1L.0", 0, 9, 60, 9, 0.4)  # half of it lies on its own road's carriageway
    out = check([road(), bend])
    assert out["pass"] and out["warn"]["own_road_sidewalks_n"] == 1


def test_a_curb_counts_like_a_sidewalk_and_a_path_on_the_road_fails():
    cross = road("way:2#0", r=90.0)
    assert check([road(), cross, box("prop", "way:1#0#curbL0", 0, 12.3, 200, 0.6, 0.5)])["fail"] == ["sidewalks_on_road"]
    assert check([road(), box("path", "way:9.0#0", 0, 0, 40, 7, 0.3)])["fail"] == ["paths_on_road"]


def test_a_sidewalk_under_an_overpass_is_not_on_it():
    deck = road("way:2#0", r=90.0, lift=30.0)
    assert check([road(), deck, box("sidewalk", "way:1#0L.0", 0, 16.5, 200, 9, 0.4)])["pass"]


def test_crosswalk_stripes_off_the_road_and_two_crosswalks_on_each_other_fail():
    out = check([road(), box("prop", "j:1#cw0-0", 0, 40, 2, 10, 0.05, 0.2)])
    assert out["fail"] == ["crosswalks_off_road"] and out["checks"]["crosswalks_off_road"]["items"][0]["id"] == "j:1#cw0"
    one = [box("prop", f"j:1#cw0-{k}", 4 * k, 0, 2, 10, 0.05, 0.2) for k in range(3)]  # one crosswalk: stripes side by side
    assert check([road(), *one])["pass"]
    out = check([road(), *one, box("prop", "j:2#cw1-0", 0, 0, 2, 10, 0.05, 0.2)])
    assert out["fail"] == ["crosswalks_double"] and out["checks"]["crosswalks_double"]["items"][0]["id"] == "j:1#cw0|j:2#cw1"


def test_neighbour_roads_count_but_their_things_are_theirs():
    theirs = road("way:5#0", z=200)
    out = check([post("sat#1#tree", 0, 200, 9, 1.4)], around=[theirs])
    assert out["fail"] == ["trees_on_road"]
    assert check([road()], around=[post("sat#1#tree", 0, 0, 9, 1.4)])["pass"]


def test_the_same_road_must_keep_its_width_across_a_cell_edge():
    out = check([road("way:1#0")], around=[road("way:1#1", x=200, width=30.0)])
    assert out["fail"] == ["seam_widths"] and out["checks"]["seam_widths"]["items"][0]["id"] == "way:1"
    assert check([road("way:1#0")], around=[road("way:1#1", x=200)])["pass"]


def test_listed_exceptions_pass_and_are_reported():
    out = check([road(), post("sat#0#tree", 0, 0, 9, 1.4)], allow={"trees_on_road": ["sat#0#tree"]})
    assert out["pass"] and out["checks"]["trees_on_road"]["allowed"] == ["sat#0#tree"]


def test_a_width_jump_is_shown_and_never_fails():
    out = check([road("way:1#0", x=-100, length=200), road("way:2#0", x=100, length=200, width=48.0)])
    assert out["pass"] and out["warn"]["width_jumps"][0]["roads"] == ["way:1", "way:2"]
    halves = check([road("way:1#0", z=-15), road("way:2#0", z=15, width=48.0)])  # two halves of a divided road side by side
    assert halves["warn"]["width_jumps"] == []


def test_a_built_cell_passes_and_a_building_on_its_street_fails(monkeypatch):
    import layout_details
    monkeypatch.setattr(layout_details, "CLIP_SHIFT_M", 0.0)  # the box stays where the trim leaves it (it would move off since 6c3)
    clear = B.plan_cell(CELL, [building(0, center=offset(CENTER, 0, 60))], [street("way:11", "tertiary")], CFG)
    items = [i for ch in json.loads(clear.files["chunks.json"])["chunks"] for i in ch["items"]]
    out = check(items)
    assert out["pass"], failing(out)
    on = B.plan_cell(CELL, [building(0, center=offset(CENTER, 0, 5))], [street("way:11", "tertiary")], CFG)
    items = [i for ch in json.loads(on.files["chunks.json"])["chunks"] for i in ch["items"]]
    assert "buildings_on_road" in check(items)["fail"]


# --- the Studio check, G2 tiles, frame rate, summary ---------------------------------------------------------

def test_studio_hits_are_grouped_by_owner_over_the_threshold():
    raw = {"roads": 10, "parts": 500, "hits": [
        {"owner": "manual:Facilities/park", "m2": 2.0, "part": "Workspace.Manual.Facilities.park.Wall", "road": "way:1#0", "at": [1, 2]},
        {"owner": "manual:Facilities/park", "m2": 5.0, "part": "Workspace.Manual.Facilities.park.Gate", "road": "way:1#0", "at": [3, 4]},
        {"owner": "auto:gis:9", "m2": 0.1, "part": "x", "road": "way:1#0", "at": [0, 0]}]}
    out = G.studio_result(raw, GATE["g1"])
    assert not out["pass"] and out["checks"]["on_road"]["items"] == [
        {"id": "manual:Facilities/park", "m2": 5.0, "part": "Workspace.Manual.Facilities.park.Gate", "road": "way:1#0", "at": [3, 4]}]
    assert G.studio_result(raw, GATE["g1"], ["manual:Facilities/park"])["pass"]


@given(st.integers(3, 4000), st.integers(3, 4000))
def test_tiles_cover_the_image_once(w, h):
    boxes = G.tile_boxes(w, h)
    assert sorted(boxes) == [f"{r}{c}" for r in "ABC" for c in "123"]
    assert sum((b[2] - b[0]) * (b[3] - b[1]) for b in boxes.values()) == w * h
    assert min(b[0] for b in boxes.values()) == 0 and max(b[2] for b in boxes.values()) == w


def test_make_tiles_writes_nine_side_by_side_sheets(tmp_path):
    from PIL import Image
    Image.new("RGB", (300, 240), (10, 20, 30)).save(tmp_path / "sat.jpg")
    Image.new("RGB", (300, 240), (200, 20, 30)).save(tmp_path / "cap.jpg")
    paths = G.make_tiles(tmp_path / "sat.jpg", tmp_path / "cap.jpg", tmp_path / "g2")
    assert [p.name for p in paths] == [f"{r}{c}.jpg" for r in "ABC" for c in "123"]
    assert Image.open(paths[0]).width >= 2 * 640
    Image.new("RGB", (100, 100)).save(tmp_path / "small.jpg")
    with pytest.raises(ValueError, match="_satellite.jpg"):
        G.make_tiles(tmp_path / "sat.jpg", tmp_path / "small.jpg", tmp_path / "g2")


def tiles(**issues):
    return {"tiles": [{"tile": f"{r}{c}", "issues": issues.get(f"{r}{c}", [])} for r in "ABC" for c in "123"]}


def test_g2_needs_every_tile_and_fails_on_a_major_issue():
    assert G.g2_result(tiles(), GATE["g2"])["pass"]
    out = G.g2_result(tiles(B2=[{"type": "tree_on_road", "severity": "major", "note": "row of trees on 길주로"}],
                            A1=[{"type": "road_width", "severity": "minor"}]), GATE["g2"])
    assert not out["pass"] and out["major"][0]["id"] == "B2:tree_on_road" and out["minor"][0]["id"] == "A1:road_width"
    with pytest.raises(ValueError, match="expected"):
        G.g2_result({"tiles": tiles()["tiles"][:8]}, GATE["g2"])
    with pytest.raises(ValueError, match="issue type"):
        G.g2_result(tiles(A1=[{"type": "ugly", "severity": "major"}]), GATE["g2"])


def test_fps_and_what_a_cell_needs():
    assert G.fps_result(60, 57, GATE["fps"])["pass"] and G.fps_result(59.9, 55, GATE["fps"])["pass"]
    assert G.fps_result(50, 40, GATE["fps"])["fail"] == ["avg", "low"]
    assert G.needed(1, False) == ["g1", "g1_studio", "g2"] and G.needed(2, True) == ["g1", "g1_studio", "g2", "fps"]


def test_summary_fails_on_a_missing_or_failed_part():
    ok = {"pass": True, "fail": []}
    out = G.summary({"g1": ok, "g1_studio": ok, "g2": {"pass": False, "fail": ["major_issues"]}, "trace": None, "fps": None},
                    G.needed(1, False, traced=True))
    assert not out["pass"] and out["fail"] == ["g2:major_issues", "trace:missing"]
    assert G.summary({"g1": ok, "g1_studio": ok, "g2": ok, "g3": ok, "fps": None}, G.needed(1, False))["pass"]


def test_gate_toml_has_every_threshold_the_code_reads():
    for key in ("building_m2", "building_max_m2", "buildings_allowed", "edge_m", "clear_low_m", "clear_high_m", "prop_m2",
                "sidewalk_m2", "path_m2", "crosswalk_double", "seam_width_m", "studio_m2"):
        assert key in GATE["g1"]
    assert {"major_allowed"} <= set(GATE["g2"]) and {"every_cells", "min_avg", "min_low"} <= set(GATE["fps"])
    assert len(G.gate_digest()) == 12


def test_the_command_line_writes_g1_and_the_summary(tmp_path, monkeypatch, capsys):
    build, out = tmp_path / "build", tmp_path / "gate"
    monkeypatch.setattr(G, "BUILD_DIR", str(build))
    monkeypatch.setattr(G, "GATE_DIR", str(out))
    plan = B.plan_cell(CELL, [building(0, center=offset(CENTER, 0, 60))], [street("way:11", "tertiary")], CFG)
    (build / CELL).mkdir(parents=True)
    (build / CELL / "chunks.json").write_text(plan.files["chunks.json"], encoding="utf-8")
    assert G.main(CFG, ["g1", "--cells", CELL]) == 0
    g1 = json.loads((out / CELL / "g1.json").read_text(encoding="utf-8"))
    assert g1["pass"] and g1["gate"] == G.gate_digest() and g1["neighbours"] == []
    assert G.main(CFG, ["summary", "--cells", CELL]) == 1  # the Studio check, satellite and look-alike are still missing
    summary = json.loads((out / CELL / "gate.json").read_text(encoding="utf-8"))
    assert "g1_studio:missing" in summary["fail"] and summary["parts"]["g1"]["pass"]
    with pytest.raises(FileNotFoundError):
        G.run_g1(CFG, NEXT, G.load_gate(), "x")
