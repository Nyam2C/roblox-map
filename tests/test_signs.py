"""U5 sign images (SI-1 to SI-9): keys and prompts, the picture finishing, generate with a fake endpoint, record, the command line."""
from __future__ import annotations

import io
import json
import sys

import pytest
from hypothesis import given, settings, strategies as st
from PIL import Image

import build_luau as B
import common
import db
import details_rules as R
import signs as Sg
from generators import SIGN_TEXTS
from layout import Item
from test_u4_db import CELL, brow

BG = [k for k in R.PALETTE_WORDS if k.startswith("sign_")]
INK = [k for k in R.PALETTE_WORDS if k.startswith("ink_")]


def sign_item(name="gis:1#sg0", text="바른치과", bg="sign_blue", ink="ink_white", sx=28.8, sy=3.24, kind="sign"):
    return Item(kind=kind, name=name, group="gis:1", seq=1, cx=0.0, cy=5.0, cz=0.0, sx=sx, sy=sy, sz=0.5, yaw_deg=0.0,
                material="SmoothPlastic", color=R.PALETTE[bg], attrs={"MaxDistance": 300}, owner="gis:1", color_name=bg, text=text, ink=ink, faces="F")


def panel_png(w=600, h=300, margin=40, color=(30, 50, 120)):
    """A synthetic endpoint answer: a colored panel with a white margin around it."""
    img = Image.new("RGB", (w, h), (255, 255, 255))
    for x in range(margin, w - margin):
        for y in range(margin, h - margin):
            img.putpixel((x, y), color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# --- keys, buckets, prompts (SI-2, SI-3) -------------------------------------------------------------------------------

@given(SIGN_TEXTS, st.sampled_from(R.SIGN_IMAGE_TAILS), st.sampled_from(BG), st.sampled_from(INK),
       st.floats(1, 60), st.floats(0.5, 3))
def test_the_key_is_stable_hex_and_changes_with_every_input(text, tail, bg, ink, w, h):
    aspect = R.aspect_bucket(w, h)
    key = R.sign_image_key(text, tail, bg, ink, aspect)
    assert len(key) == 16 and all(c in "0123456789abcdef" for c in key)
    assert key == R.sign_image_key(text, tail, bg, ink, aspect)
    other_tail = "sgf" if tail == "sg" else "sg"
    assert key != R.sign_image_key(text, other_tail, bg, ink, aspect)
    assert key != R.sign_image_key(text + "2" if len(text) < 12 else text[:-1], tail, bg, ink, aspect)


def test_a_known_key_does_not_drift():
    """Pinned: a different hash would make every recorded asset id orphaned (SI-2, SI-9)."""
    assert R.sign_image_key("바른치과", "sg", "sign_blue", "ink_white", "9.0") == "33c37523bca68680"
    assert R.sign_image_key("바른치과", "sg", "sign_blue", "ink_white", "9.0") != R.sign_image_key("바른치과", "sg", "sign_blue", "ink_white", "9.5")


@pytest.mark.parametrize("w, h, want", [(28.8, 3.24, "9.0"), (10, 10, "1.0"), (1, 100, "1.0"), (999, 1, "20.0"), (7.26, 1, "7.5"), (7.24, 1, "7.0")])
def test_the_aspect_bucket_rounds_to_a_half_and_is_clamped(w, h, want):
    assert R.aspect_bucket(w, h) == want


@pytest.mark.parametrize("bad", [("", "sg", "sign_blue", "ink_white", "9.0"), ("바른치과", "sp", "sign_blue", "ink_white", "9.0"),
                                 ("바른치과", "sg", "blue", "ink_white", "9.0"), ("바른치과", "sg", "sign_blue", "ink_white", "9.25"),
                                 ('바른"치과', "sg", "sign_blue", "ink_white", "9.0")])
def test_a_bad_key_input_is_refused(bad):
    with pytest.raises(ValueError):
        R.sign_image_key(*bad)


@given(SIGN_TEXTS, st.sampled_from(BG), st.sampled_from(INK))
def test_the_prompt_carries_the_exact_text_the_colors_and_nothing_secret(text, bg, ink):
    p = R.sign_prompt(text, bg, ink)
    assert f'"{text}"' in p and R.PALETTE_WORDS[bg] in p and R.PALETTE_WORDS[ink] in p
    assert "key" not in p.lower() and "http" not in p and "rbxasset" not in p
    icon = R.sign_icon(text)
    assert (icon in p) if icon else ("icon" not in p)


def test_icons_pick_the_longest_matching_ending():
    assert R.sign_icon("다솜피아노학원") == "a few piano keys" and R.sign_icon("행복수학학원") == "a pencil"
    assert R.sign_icon("바른치과") == "a tooth" and R.sign_icon("나래문구") == "a pencil" and R.sign_icon("하나빌딩") is None


def test_no_sign_name_or_icon_refers_to_alcohol():
    """Roblox moderated the account after a beer-mug sign went up (2026-10-13): no bar names in the pools, no drink icons."""
    for pool in R.POOLS.values():
        assert not any(any(w in word for w in ("호프", "주점", "맥주", "소주", "포차", "바")) for word in pool), pool
    assert not any(any(w in icon for w in ("beer", "wine", "soju", "cocktail", "bottle")) for _, icon in R.SIGN_ICONS)


def test_sign_tail_reads_the_item_name():
    assert R.sign_tail("gis:1#sgf1-0") == "sgf" and R.sign_tail("gis:1#sg0") == "sg" and R.sign_tail("gis:1#sp0") == "sp" and R.sign_tail("Spawn") == ""


# --- targets (SI-1) ------------------------------------------------------------------------------------------------------

def test_targets_take_band_and_floor_signs_once_per_look_and_skip_the_rest():
    items = [sign_item(), sign_item(name="gis:2#sg0"), sign_item(name="gis:1#sgf1-0", text="다솜피아노학원", sx=36, sy=2.88),
             sign_item(name="gis:1#sp0", text="우리카페"), sign_item(name="gis:1#sr0", text="하늘빌딩"), sign_item(name="gis:3#sn0", text="행정복지센터"),
             sign_item(name="gis:4#w0f0-0", kind="facade", text=None)]
    targets = Sg.targets_of(items)
    assert [t["text"] for t in targets] == sorted(["바른치과", "다솜피아노학원"], key=lambda s: R.sign_image_key(s, "sg" if s == "바른치과" else "sgf", "sign_blue", "ink_white", R.aspect_bucket(28.8 if s == "바른치과" else 36, 3.24 if s == "바른치과" else 2.88)))
    band = next(t for t in targets if t["tail"] == "sg")
    assert band["uses"] == 2 and band["first"] == "gis:1#sg0" and band["aspect"] == "9.0"
    assert targets == sorted(targets, key=lambda t: t["key"])


# --- the picture (SI-4) ---------------------------------------------------------------------------------------------------

@settings(max_examples=25)
@given(st.integers(300, 900), st.integers(200, 500), st.integers(10, 60), st.sampled_from(["4.0", "9.0", "15.0", "1.5", "20.0"]))
def test_finishing_crops_the_margin_pads_to_the_aspect_and_scales_to_1024_wide(w, h, margin, aspect):
    out = Sg.finish_image(panel_png(w, h, margin), aspect)
    assert out.size == (1024, max(8, round(1024 / float(aspect))))
    px = out.load()
    for x, y in ((2, out.size[1] // 2), (out.size[0] - 3, out.size[1] // 2), (out.size[0] // 2, 2), (out.size[0] // 2, out.size[1] - 3)):
        assert max(px[x, y]) < Sg.WHITE  # no white margin survives on any edge
    assert px[out.size[0] // 2, out.size[1] // 2] == (30, 50, 120)


def lettered_png(w=1200, h=800, margin=60, bg=(30, 50, 120), ink=(255, 255, 255)):
    """A framed panel with a lettering block (a bar) in its middle third, like the endpoint's answers (thin aluminium frame)."""
    img = Image.new("RGB", (w, h), (255, 255, 255))
    img.paste(Image.new("RGB", (w - 2 * margin, h - 2 * margin), (185, 185, 190)), (margin, margin))  # the frame line
    d = Image.new("RGB", (w - 2 * margin - 8, h - 2 * margin - 8), bg)
    img.paste(d, (margin + 4, margin + 4))
    bar = Image.new("RGB", ((w - 2 * margin) * 6 // 10, (h - 2 * margin) // 4), ink)
    img.paste(bar, (margin + (w - 2 * margin) * 2 // 10, margin + (h - 2 * margin) * 3 // 8))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_finishing_crops_to_the_lettering_so_the_name_fills_the_height():
    out = Sg.finish_image(lettered_png(), "13.5")
    assert out.size == (1024, 76)
    px = out.load()
    bright_cols = [x for x in range(out.size[0]) if max(px[x, out.size[1] // 2]) > 200]
    assert bright_cols and (bright_cols[-1] - bright_cols[0]) >= 0.2 * out.size[0]  # the lettering spans a real share of the width
    assert any(max(px[out.size[0] // 2, y]) > 200 for y in range(out.size[1] // 2 - 6, out.size[1] // 2 + 6))
    rows_with_ink = [y for y in range(out.size[1]) if max(px[out.size[0] // 2, y]) > 200]
    assert 0.5 <= (rows_with_ink[-1] - rows_with_ink[0]) / out.size[1] <= 0.9  # lettering fills most of the height, with a margin
    assert px[3, 3] == (30, 50, 120) and px[out.size[0] - 4, out.size[1] - 4] == (30, 50, 120)


def test_generate_reuses_a_cached_raw_answer_without_calling_the_endpoint(tmp_path):
    targets = Sg.targets_of([sign_item()])
    calls = []

    def fake(prompt):
        calls.append(prompt)
        return lettered_png()

    cache = tmp_path / "signs"
    assert Sg.generate(targets, cache, fake, limit=5, workers=1)["made"] == 1 and len(calls) == 1
    (cache / f"{targets[0]['key']}.png").unlink()  # a new finishing: only the finished file goes
    assert Sg.generate(targets, cache, fake, limit=5, workers=1)["made"] == 1 and len(calls) == 1


def test_a_white_panel_with_black_lettering_keeps_its_white_and_its_lettering():
    out = Sg.finish_image(lettered_png(bg=(246, 246, 243), ink=(20, 20, 20)), "9.0")
    px = out.load()
    assert px[3, 3] == (246, 246, 243) and px[out.size[0] - 4, 3] == (246, 246, 243)
    assert min(min(px[x, out.size[1] // 2]) for x in range(out.size[0])) < 60  # the black bar survived


def test_an_answer_that_cannot_be_finished_is_dropped_so_the_next_run_asks_again(tmp_path):
    targets = Sg.targets_of([sign_item()])
    answers = [Image.new("RGB", (200, 100), (255, 255, 255))]  # first: all white (unusable), then good
    calls = []

    def fake(prompt):
        calls.append(prompt)
        if answers:
            buf = io.BytesIO()
            answers.pop().save(buf, format="PNG")
            return buf.getvalue()
        return lettered_png()

    cache = tmp_path / "signs"
    assert Sg.generate(targets, cache, fake, limit=5, workers=1)["failed"] == 1 and not (cache / "raw" / f"{targets[0]['key']}.png").exists()
    assert Sg.generate(targets, cache, fake, limit=5, workers=1)["made"] == 1 and len(calls) == 2


def test_a_tiny_panel_and_a_pixel_bomb_count_as_failures_not_crashes(tmp_path):
    tiny = Image.new("RGB", (200, 100), (255, 255, 255))
    tiny.paste(Image.new("RGB", (20, 20), (30, 50, 120)), (90, 40))
    tiny.paste(Image.new("RGB", (2, 2), (255, 255, 255)), (99, 49))
    bomb = Image.new("1", (6000, 6000), 1)
    pngs = []
    for im in (tiny, bomb):
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        pngs.append(buf.getvalue())
    assert Sg.finish_image(pngs[0], "9.0").size == (1024, 114)  # a tiny panel is still a picture, never an IndexError
    with pytest.raises(ValueError):
        Sg.finish_image(pngs[1], "9.0")  # too many pixels
    targets = Sg.targets_of([sign_item(), sign_item(name="gis:1#sgf1-0", text="다솜피아노학원", sx=36, sy=2.88), sign_item(name="gis:5#sg0", text="별빛분식")])
    it = iter([pngs[0], lettered_png(), pngs[1]])
    counts = Sg.generate(targets, tmp_path / "signs", lambda prompt: next(it), limit=10, workers=1)
    assert counts["made"] == 2 and counts["failed"] == 1


def test_a_plan_file_whose_key_does_not_match_its_look_is_refused(tmp_path):
    targets = Sg.targets_of([sign_item()])
    root = tmp_path / "build"
    Sg.write_plan_file(root, CELL, targets)
    assert Sg.read_plan_file(root, CELL) == targets
    Sg.write_plan_file(root, CELL, [{**targets[0], "key": "../../evil"}])
    with pytest.raises(ValueError):
        Sg.read_plan_file(root, CELL)
    Sg.write_plan_file(root, CELL, [{**targets[0], "key": "0123456789abcdef"}])
    with pytest.raises(ValueError):
        Sg.read_plan_file(root, CELL)


def test_a_redirect_from_the_endpoint_is_an_error_not_followed(monkeypatch):
    import urllib.request
    client = Sg.api_client("https://x.example/openai/v1", "sk-test", "dep", "1536x1024")
    opener = urllib.request._opener  # installed by api_client
    assert any(isinstance(h, Sg._NoRedirect) for h in opener.handlers)
    assert Sg._NoRedirect().redirect_request(None, None, 302, "Found", {}, "http://evil.example/x") is None


def test_an_all_white_answer_is_refused():
    buf = io.BytesIO()
    Image.new("RGB", (200, 100), (255, 255, 255)).save(buf, format="PNG")
    with pytest.raises(ValueError):
        Sg.finish_image(buf.getvalue(), "9.0")


# --- generate with a fake endpoint (SI-8) ---------------------------------------------------------------------------------

def test_generate_makes_only_the_missing_images_within_the_limit_and_skips_a_failure(tmp_path):
    targets = Sg.targets_of([sign_item(), sign_item(name="gis:1#sgf1-0", text="다솜피아노학원", sx=36, sy=2.88),
                             sign_item(name="gis:5#sg0", text="별빛분식", bg="sign_red", ink="ink_yellow")])
    calls = []

    def fake(prompt):
        calls.append(prompt)
        if "별빛분식" in prompt:
            raise ValueError("boom")
        return panel_png()

    cache = tmp_path / "signs"
    c1 = Sg.generate(targets, cache, fake, limit=1, workers=2)
    assert c1["made"] == 1 and c1["left"] == 2 and len(calls) == 1
    c2 = Sg.generate(targets, cache, fake, limit=10, workers=2)
    assert c2["cached"] == 1 and c2["made"] + c2["failed"] == 2 and c2["failed"] == 1 and c2["left"] == 1
    made = sorted(p.name for p in cache.glob("*.png"))
    assert len(made) == 2 and all(len(n) == 20 for n in made) and (cache / "raw").exists()
    c3 = Sg.generate(targets, cache, fake, limit=10, workers=1)
    assert c3["cached"] == 2 and c3["failed"] == 1 and len(calls) == 4  # only the failed one is tried again


def test_an_unexpected_endpoint_answer_stops_the_run(tmp_path):
    targets = Sg.targets_of([sign_item(), sign_item(name="gis:1#sgf1-0", text="다솜피아노학원", sx=36, sy=2.88)])

    def odd(prompt):
        raise Sg.StopGeneration("no data")

    with pytest.raises(Sg.StopGeneration):
        Sg.generate(targets, tmp_path / "signs", odd, limit=10, workers=2)


def test_the_api_client_parses_b64_and_refuses_other_shapes(monkeypatch):
    import urllib.request

    class Resp:
        def __init__(self, payload):
            self.payload = payload

        def read(self, n=-1):
            return json.dumps(self.payload).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    seen = {}

    def fake_open(req, timeout=0):
        seen["url"] = req.full_url
        seen["auth"] = req.get_header("Authorization")
        seen["body"] = json.loads(req.data)
        return Resp(seen["payload"])

    monkeypatch.setattr(urllib.request, "urlopen", fake_open)
    client = Sg.api_client("https://x.example/openai/v1/", "sk-test", "dep", "1536x1024")
    seen["payload"] = {"data": [{"b64_json": "aGVsbG8="}]}
    assert client("p") == b"hello" and seen["url"] == "https://x.example/openai/v1/images/generations"
    assert seen["auth"] == "Bearer sk-test" and seen["body"] == {"model": "dep", "prompt": "p", "n": 1, "size": "1536x1024"}
    seen["payload"] = {"data": [{"url": "https://cdn"}]}
    with pytest.raises(Sg.StopGeneration):
        client("p")


# --- record (SI-5) and the chunk key (SI-6) ------------------------------------------------------------------------------------

def test_record_merges_asset_ids_by_key_and_refuses_unknown_keys_and_bad_ids(tmp_path):
    targets = Sg.targets_of([sign_item(), sign_item(name="gis:1#sgf1-0", text="다솜피아노학원", sx=36, sy=2.88)])
    k1, k2 = targets[0]["key"], targets[1]["key"]
    path, n = Sg.record(CELL, {f"http://127.0.0.1:8765/{k1}.png": "rbxassetid://123"}, targets, tmp_path / "signs", "2026-10-13T00:00:00+00:00")
    assert n == 1 and path.name == f"{CELL}.json"
    path, n = Sg.record(CELL, {f"{k2}.png": 456}, targets, tmp_path / "signs", "2026-10-13T00:00:01+00:00")
    data = json.loads(path.read_text())
    assert set(data["signs"]) == {k1, k2} and data["signs"][k1]["asset_id"] == 123 and data["signs"][k2]["asset_id"] == 456
    assert data["signs"][k2]["text"] == "다솜피아노학원" and data["version"] == R.SIGN_IMAGE_KEY_VERSION
    assert B.load_sign_assets(path) == {k1: 123, k2: 456}
    with pytest.raises(ValueError):
        Sg.record(CELL, {"0123456789abcdef.png": 1}, targets, tmp_path / "signs", "t")
    with pytest.raises(ValueError):
        Sg.record(CELL, {f"{k1}.png": "rbxassetid://abc"}, targets, tmp_path / "signs", "t")
    with pytest.raises(ValueError):
        Sg.record(CELL, {}, targets, tmp_path / "signs", "t")


def test_load_sign_assets_refuses_a_bad_file_and_takes_no_file_as_empty(tmp_path):
    assert B.load_sign_assets(tmp_path / "none.json") == {}
    bad = tmp_path / "x.json"
    bad.write_text(json.dumps({"signs": {"0123456789abcdef": {"asset_id": -1}}}))
    with pytest.raises(ValueError):
        B.load_sign_assets(bad)
    bad.write_text(json.dumps({"signs": {"zz": {"asset_id": 5}}}))
    with pytest.raises(ValueError):
        B.load_sign_assets(bad)


def test_the_literal_carries_im_only_for_a_mapped_sign_and_keeps_the_text():
    item = sign_item()
    plain = B.item_literal(item, CELL)
    assert "im=" not in plain and 't="바른치과"' in plain
    item.attrs["ImageAsset"] = 987654321
    lit = B.item_literal(item, CELL)
    assert "im=987654321" in lit and 't="바른치과"' in lit and lit.count("x=") == 1
    item.attrs["ImageAsset"] = "987"
    with pytest.raises(ValueError):
        B.item_literal(item, CELL)
    item.attrs["ImageAsset"] = 2 ** 60
    with pytest.raises(ValueError):
        B.item_literal(item, CELL)
    import dataclasses
    two_sided = dataclasses.replace(sign_item(name="gis:1#sp0", text="우리카페"), faces="LR")
    two_sided.attrs["ImageAsset"] = 5
    with pytest.raises(ValueError):
        B.item_literal(two_sided, CELL)


# --- the command line ------------------------------------------------------------------------------------------------------

@pytest.fixture
def world(tmp_path):
    cfg = {**common.DEFAULTS, "db_path": str(tmp_path / "map.db"), "signs_dir": str(tmp_path / "signs"), "assets_dir": str(tmp_path / "assets"),
           "log_dir": str(tmp_path / "logs")}
    conn = db.connect(cfg["db_path"])
    row = {**brow(1, floors=5, height=17.0), "usability_code": "14000", "building_area": 400.0}
    db.replace_cell_rows(conn, CELL, {"buildings": [row]})
    conn.close()
    return cfg, tmp_path


def run_main(monkeypatch, cfg, *argv):
    monkeypatch.setattr(sys, "argv", ["signs.py", *argv])
    return Sg.main(cfg)


def test_plan_status_and_record_through_the_command_line(world, monkeypatch, capsys):
    cfg, tmp = world
    monkeypatch.setattr(B, "BUILD_DIR", str(tmp / "build"))
    assert run_main(monkeypatch, cfg, "plan", "--cells", CELL) == 0
    out = capsys.readouterr().out
    assert "sign looks" in out
    targets = Sg.read_plan_file(common.resolve(B.BUILD_DIR), CELL)
    assert run_main(monkeypatch, cfg, "status", "--cells", CELL) == 0
    assert "0 asset ids recorded" in capsys.readouterr().out
    if targets:
        (tmp / "up.json").write_text(json.dumps({f"{targets[0]['key']}.png": "rbxassetid://42"}))
        assert run_main(monkeypatch, cfg, "record", "--cells", CELL, "--file", str(tmp / "up.json")) == 0
        assert "recorded 1" in capsys.readouterr().out
        assert B.load_sign_assets(tmp / "signs" / f"{CELL}.json") == {targets[0]["key"]: 42}


def test_generate_refuses_without_the_environment(world, monkeypatch, capsys):
    cfg, tmp = world
    monkeypatch.setattr(B, "BUILD_DIR", str(tmp / "build"))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    assert run_main(monkeypatch, cfg, "plan", "--cells", CELL) == 0
    assert run_main(monkeypatch, cfg, "generate", "--cells", CELL) == 1
    assert "OPENAI_BASE_URL" in capsys.readouterr().err


def test_the_command_line_checks_its_arguments():
    with pytest.raises(SystemExit):
        Sg.parse_args([])
    with pytest.raises(SystemExit):
        Sg.parse_args(["plan", "--cells", "nope"])
    with pytest.raises(SystemExit):
        Sg.parse_args(["generate", "--cells", CELL, "--workers", "99"])
    assert Sg.parse_args(["--selftest"]).selftest
