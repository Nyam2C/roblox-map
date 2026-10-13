# /// script
# requires-python = ">=3.11"
# dependencies = ["pillow==12.3.0", "h3==4.5.0", "shapely==2.2.0"]
# ///
"""U5 sign images: band and floor sign pictures, generated once per look, cached, uploaded by Studio, recorded per cell (SI-1 to SI-9).

Usage:
  uv run src/signs.py plan --cells 8930e0af13bffff                                   # targets -> data/build/<cell>/signs-plan.json
  uv run --env-file .env src/signs.py generate --cells 8930e0af13bffff [--limit 200] [--workers 4]
                                                                                     # missing images -> assets/signs/<key>.png
  uv run src/signs.py record --cells 8930e0af13bffff --file upload.json              # {url or path: "rbxassetid://N"} -> signs/<cell>.json
  uv run src/signs.py status --cells 8930e0af13bffff
  uv run src/signs.py --selftest                                                     # import check only

The images are made by an OpenAI-compatible image endpoint (OPENAI_BASE_URL, OPENAI_API_KEY from .env, never written anywhere).
Claude uploads the cached files with the Studio MCP upload_image tool (served from 127.0.0.1) and records the asset ids here;
build_luau.py then puts `im=<asset id>` on the matching sign items. Without a record the signs stay text (SI-9).
Rules: aidlc-docs/construction/u5-details/sign-images/plan.md
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import common
import db
import details_rules

MAX_FILE_BYTES = 2_000_000
WHITE = 240          # a pixel whose darkest channel is at least this bright is margin, not panel (SI-4)
RETRY_WAITS_S = (5.0, 15.0, 30.0)


class StopGeneration(RuntimeError):
    """The endpoint answered in a shape we do not understand: stop instead of guessing (SI-8)."""


# --- targets (SI-1, SI-2) --------------------------------------------------------------------------------------------

def targets_of(items: Sequence[Any]) -> list[dict[str, Any]]:
    """The distinct sign looks of a plan's items that get an image, by key: band and floor signs with a text and colors."""
    out: dict[str, dict[str, Any]] = {}
    for i in items:
        if getattr(i, "kind", None) != "sign" or not i.text or not i.color_name or not i.ink:
            continue
        tail = details_rules.sign_tail(i.name)
        if tail not in details_rules.SIGN_IMAGE_TAILS:
            continue
        aspect = details_rules.aspect_bucket(i.sx, i.sy)
        key = details_rules.sign_image_key(i.text, tail, i.color_name, i.ink, aspect)
        if key not in out:
            out[key] = {"key": key, "text": i.text, "tail": tail, "bg": i.color_name, "ink": i.ink, "aspect": aspect, "first": i.name, "uses": 0}
        out[key]["uses"] += 1
    return [out[k] for k in sorted(out)]


def plan_path(root: Path, cell_id: str) -> Path:
    return root / cell_id / "signs-plan.json"


def write_plan_file(root: Path, cell_id: str, targets: Sequence[Mapping[str, Any]]) -> Path:
    path = plan_path(root, cell_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"cell_id": cell_id, "version": details_rules.SIGN_IMAGE_KEY_VERSION, "targets": list(targets)},
                               ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return path


def read_plan_file(root: Path, cell_id: str) -> list[dict[str, Any]]:
    path = plan_path(root, cell_id)
    if not path.exists():
        raise ValueError(f"no sign plan for {cell_id}: run `signs.py plan` first")
    data = json.loads(path.read_text(encoding="utf-8"))
    targets = data.get("targets") if isinstance(data, dict) else None
    if not isinstance(targets, list):
        raise ValueError(f"{path.name}: not a sign plan")
    for t in targets:
        details_rules.sign_image_key(t["text"], t["tail"], t["bg"], t["ink"], t["aspect"])  # refuses a tampered file
    return targets


# --- the picture (SI-4) ------------------------------------------------------------------------------------------------

INK_DISTANCE = 150  # a pixel this far (sum of channel differences, 0..765) from the panel color is lettering or icon (SI-4)
INK_ROW_SHARE = 0.01  # a row or column counts as lettering when at least this share of its pixels is ink (photo grain is sparser)
INK_MARGIN = (0.12, 0.08)  # of the lettering block's height, added above/below and left/right before padding


def finish_image(png: bytes, aspect: str):
    """Crop the white margin, then crop to the lettering block (so the name fills the sign's height instead of sitting in a
    small 3:2 panel), pad to the sign's aspect with the panel color, scale to 1024 px wide (SI-4)."""
    from PIL import Image
    img = Image.open(io.BytesIO(png)).convert("RGB")
    box = img.convert("L").point(lambda v: 255 if v < WHITE else 0).getbbox()
    if box is None or box[2] - box[0] < 16 or box[3] - box[1] < 16:
        raise ValueError("the image has no panel (all white)")
    panel = img.crop(box)
    panel = _ink_block(panel)
    ratio = float(aspect)
    w, h = panel.size
    if w / h < ratio:  # pad the sides
        new_w = int(round(h * ratio))
        edge = _edge_color(panel, "lr")
        out = Image.new("RGB", (new_w, h), edge)
        out.paste(panel, ((new_w - w) // 2, 0))
    else:  # pad top and bottom
        new_h = int(round(w / ratio))
        edge = _edge_color(panel, "tb")
        out = Image.new("RGB", (w, new_h), edge)
        out.paste(panel, (0, (new_h - h) // 2))
    width = details_rules.SIGN_IMAGE_WIDTH
    height = max(8, int(round(width / ratio)))
    return out.resize((width, height), Image.LANCZOS)


def _ink_block(panel):
    """The lettering and icon of a panel with a margin around it; the whole panel when nothing stands out from its color."""
    from PIL import Image
    w, h = panel.size
    bg = _edge_color(panel, "lr")
    border = max(2, int(min(w, h) * 0.06))  # the thin frame line along the edges is not lettering
    inner = panel.crop((border, border, w - border, h - border))
    r, g, b = inner.split()
    dist = Image.merge("RGB", (r.point(lambda v: abs(v - bg[0])), g.point(lambda v: abs(v - bg[1])), b.point(lambda v: abs(v - bg[2]))))
    far = dist.convert("L", (1, 1, 1, 0)).point(lambda v: 255 if v >= INK_DISTANCE else 0)  # the sum of the three differences
    iw, ih = inner.size
    rows, cols = far.resize((1, ih), Image.BOX).load(), far.resize((iw, 1), Image.BOX).load()  # mean ink per row / column
    ry = [y for y in range(ih) if rows[0, y] >= 255 * INK_ROW_SHARE]
    cx = [x for x in range(iw) if cols[x, 0] >= 255 * INK_ROW_SHARE]
    if not ry or not cx or cx[-1] - cx[0] < w * 0.05 or ry[-1] - ry[0] < h * 0.05:
        return panel
    x0, y0, x1, y1 = cx[0] + border, ry[0] + border, cx[-1] + 1 + border, ry[-1] + 1 + border
    bh = y1 - y0
    my, mx = int(bh * INK_MARGIN[0]), int(bh * INK_MARGIN[1])
    return panel.crop((max(0, x0 - mx), max(0, y0 - my), min(w, x1 + mx), min(h, y1 + my)))


def _edge_color(panel, sides: str) -> tuple[int, int, int]:
    """The average color of the panel's outer columns (lr) or rows (tb), a few pixels in so the frame line does not dominate."""
    w, h = panel.size
    inset = max(2, min(w, h) // 25)
    px = panel.load()
    samples = []
    if sides == "lr":
        for y in range(0, h, max(1, h // 64)):
            samples += [px[inset, y], px[w - 1 - inset, y]]
    else:
        for x in range(0, w, max(1, w // 64)):
            samples += [px[x, inset], px[x, h - 1 - inset]]
    n = max(1, len(samples))
    return tuple(int(sum(s[c] for s in samples) / n) for c in range(3))  # type: ignore[return-value]


# --- the endpoint (SI-8) ----------------------------------------------------------------------------------------------

def api_client(base_url: str, api_key: str, model: str, size: str, timeout_s: float = 180.0) -> Callable[[str], bytes]:
    """A function prompt -> PNG bytes against an OpenAI-compatible images endpoint. Retries 429, 5xx and timeouts three times."""
    url = base_url.rstrip("/") + "/images/generations"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}", "api-key": api_key, "User-Agent": "roblox-map"}

    def make(prompt: str) -> bytes:
        body = json.dumps({"model": model, "prompt": prompt, "n": 1, "size": size}).encode("utf-8")
        last: Exception | None = None
        for attempt in range(len(RETRY_WAITS_S) + 1):
            try:
                with urllib.request.urlopen(urllib.request.Request(url, data=body, headers=headers, method="POST"), timeout=timeout_s) as r:
                    data = json.loads(r.read(20_000_000).decode("utf-8"))
                break
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503, 504) and attempt < len(RETRY_WAITS_S):
                    last = e
                    time.sleep(RETRY_WAITS_S[attempt])
                    continue
                raise
            except (TimeoutError, urllib.error.URLError, OSError) as e:
                if attempt < len(RETRY_WAITS_S):
                    last = e
                    time.sleep(RETRY_WAITS_S[attempt])
                    continue
                raise
        else:  # pragma: no cover - the loop always breaks or raises
            raise RuntimeError(str(last))
        try:
            b64 = data["data"][0]["b64_json"]
        except (KeyError, IndexError, TypeError):
            raise StopGeneration("the image endpoint answered without data[0].b64_json") from None
        if not isinstance(b64, str):
            raise StopGeneration("b64_json is not a string")
        return base64.b64decode(b64)

    return make


def client_from_env(cfg: Mapping[str, Any]) -> Callable[[str], bytes]:
    base, key = os.environ.get("OPENAI_BASE_URL", "").strip(), os.environ.get("OPENAI_API_KEY", "").strip()
    if not base.startswith("https://") or not key:
        raise ValueError("OPENAI_BASE_URL (https) and OPENAI_API_KEY are needed: run with `uv run --env-file .env`")
    return api_client(base, key, str(cfg["sign_image_model"]), str(cfg["sign_image_size"]))


# --- generate (SI-3, SI-4, SI-8) --------------------------------------------------------------------------------------

def generate(targets: Sequence[Mapping[str, Any]], cache_dir: Path, client: Callable[[str], bytes], limit: int, workers: int,
             cell_id: str | None = None) -> dict[str, int]:
    """Make the images that are not in the cache yet, at most `limit`, `workers` at a time. One failure skips that key."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "raw").mkdir(exist_ok=True)
    todo = [t for t in targets if not (cache_dir / f"{t['key']}.png").exists()][:limit]
    counts = {"targets": len(targets), "cached": len(targets) - sum(1 for t in targets if not (cache_dir / f"{t['key']}.png").exists()),
              "made": 0, "failed": 0, "left": 0}
    stop: list[BaseException] = []

    def one(t: Mapping[str, Any]) -> bool:
        if stop:
            return False
        prompt = details_rules.sign_prompt(t["text"], t["bg"], t["ink"])
        raw_path = cache_dir / "raw" / f"{t['key']}.png"
        try:
            if raw_path.exists():  # the endpoint's answer is kept: a new finishing never costs a call
                raw = raw_path.read_bytes()
            else:
                raw = client(prompt)
                if len(raw) > 30_000_000:
                    raise ValueError("image response too large")
                raw_path.write_bytes(raw)
            img = finish_image(raw, t["aspect"])
            tmp = cache_dir / f"{t['key']}.png.tmp"
            img.save(tmp, format="PNG", optimize=True)
            os.replace(tmp, cache_dir / f"{t['key']}.png")
            common.log(logging.INFO, "sign image made", cell_id, key=t["key"], tail=t["tail"], aspect=t["aspect"])
            return True
        except StopGeneration as e:
            stop.append(e)
            return False
        except (ValueError, OSError, urllib.error.URLError, TimeoutError) as e:
            common.log(logging.WARNING, f"sign image failed: {common.mask(f'{type(e).__name__}: {e}')}", cell_id, key=t["key"])
            return False

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        results = list(pool.map(one, todo))
    if stop:
        raise stop[0]
    counts["made"] = sum(1 for r in results if r)
    counts["failed"] = sum(1 for r in results if not r)
    counts["left"] = sum(1 for t in targets if not (cache_dir / f"{t['key']}.png").exists())
    return counts


# --- record (SI-5) ----------------------------------------------------------------------------------------------------

def parse_asset_id(value: Any) -> int:
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    if isinstance(value, str):
        digits = value.strip()
        for prefix in ("rbxassetid://", "http://www.roblox.com/asset/?id=", "https://www.roblox.com/asset/?id="):
            if digits.startswith(prefix):
                digits = digits[len(prefix):]
        if digits.isdigit() and int(digits) > 0:
            return int(digits)
    raise ValueError(f"not a Roblox asset id: {str(value)[:40]!r}")


def key_of_path(path: str) -> str:
    name = path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    if name.endswith(".png"):
        name = name[:-4]
    if not details_rules.SIGN_TEXT.fullmatch(name) and not (len(name) == 16 and all(c in "0123456789abcdef" for c in name)):
        raise ValueError(f"not a sign image file name: {name[:40]!r}")
    return name


def record(cell_id: str, mapping: Mapping[str, Any], targets: Sequence[Mapping[str, Any]], signs_dir: Path, now: str) -> tuple[Path, int]:
    """Merge {image path or url: asset id} into signs/<cell>.json for the keys of this cell's plan. Unknown keys refuse the call."""
    by_key = {t["key"]: t for t in targets}
    rows: dict[str, dict[str, Any]] = {}
    for path, value in mapping.items():
        key = key_of_path(str(path))
        if key not in by_key:
            raise ValueError(f"{key} is not in the sign plan of {cell_id}")
        t = by_key[key]
        rows[key] = {"asset_id": parse_asset_id(value), "text": t["text"], "tail": t["tail"], "bg": t["bg"], "ink": t["ink"],
                     "aspect": t["aspect"], "recorded_at": now}
    if not rows:
        raise ValueError("nothing to record")
    signs_dir.mkdir(parents=True, exist_ok=True)
    path = signs_dir / f"{cell_id}.json"
    existing: dict[str, Any] = {}
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        existing = data.get("signs") if isinstance(data, dict) and isinstance(data.get("signs"), dict) else {}
    merged = {**existing, **rows}
    text = json.dumps({"cell_id": cell_id, "version": details_rules.SIGN_IMAGE_KEY_VERSION, "signs": dict(sorted(merged.items()))},
                      ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
    return path, len(rows)


def read_mapping(path: str) -> dict[str, Any]:
    raw = sys.stdin.read(MAX_FILE_BYTES + 1) if path == "-" else Path(path).read_text(encoding="utf-8")
    if len(raw.encode("utf-8")) > MAX_FILE_BYTES:
        raise ValueError("upload file is too large")
    try:
        data = json.loads(raw)
    except ValueError as e:
        raise ValueError(f"upload file is not JSON: {e}") from None
    if not isinstance(data, dict):
        raise ValueError("upload file must be an object {path: asset id}")
    return data


# --- command line ------------------------------------------------------------------------------------------------------

def cell_arg(value: str) -> str:
    import h3
    if not (h3.is_valid_cell(value) and h3.get_resolution(value) == common.DEFAULTS["h3_res"]):
        raise argparse.ArgumentTypeError(f"not a resolution-{common.DEFAULTS['h3_res']} H3 cell id: {value}")
    return value


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="signs.py", description=__doc__.split("\n")[0])
    parser.add_argument("--selftest", action="store_true", help="check that the modules import; touches nothing")
    sub = parser.add_subparsers(dest="command")
    for name, text in (("plan", "list the sign looks of a cell"), ("status", "how many are made and recorded")):
        c = sub.add_parser(name, help=text)
        c.add_argument("--cells", nargs="+", required=True, type=cell_arg, metavar="ID")
    g = sub.add_parser("generate", help="make the missing images (needs OPENAI_BASE_URL and OPENAI_API_KEY)")
    g.add_argument("--cells", nargs="+", required=True, type=cell_arg, metavar="ID")
    g.add_argument("--limit", type=int, default=200)
    g.add_argument("--workers", type=int, default=None)
    r = sub.add_parser("record", help="store the asset ids Studio returned for uploaded images")
    r.add_argument("--cells", nargs=1, required=True, type=cell_arg, metavar="ID")
    r.add_argument("--file", required=True, help="JSON {path or url: 'rbxassetid://N'}, or - for standard input")
    ns = parser.parse_args(list(argv))
    if not ns.selftest and not ns.command:
        parser.error("a command is required (plan, generate, record, status) or --selftest")
    if ns.command == "generate":
        if not 1 <= ns.limit <= 2000:
            parser.error("--limit must be from 1 to 2000")
        if ns.workers is not None and not 1 <= ns.workers <= 16:
            parser.error("--workers must be from 1 to 16")
    return ns


def run_command(conn, cfg: Mapping[str, Any], args: argparse.Namespace, client: Callable[[str], bytes] | None = None) -> dict[str, int]:
    import build_luau
    root = common.resolve(build_luau.BUILD_DIR)
    cache = common.resolve(cfg["assets_dir"])
    signs_dir = common.resolve(cfg["signs_dir"])
    if args.command == "plan":
        total = 0
        for cell in args.cells:
            buildings, features, estimates, overrides, details = build_luau.load_cell_inputs(conn, cell)
            plan = build_luau.plan_cell(cell, buildings, features, cfg, estimates, overrides, details)
            targets = targets_of(plan.items)
            path = write_plan_file(root, cell, targets)
            total += len(targets)
            print(f"{cell}: {len(targets)} sign looks -> {path}")
        return {"targets": total}
    if args.command == "generate":
        client = client or client_from_env(cfg)
        counts: dict[str, int] = {}
        for cell in args.cells:
            c = generate(read_plan_file(root, cell), cache, client, args.limit, args.workers or int(cfg["sign_image_workers"]), cell)
            print(f"{cell}: made {c['made']}, failed {c['failed']}, cached before {c['cached']}, left {c['left']} of {c['targets']}")
            for k, v in c.items():
                counts[k] = counts.get(k, 0) + v
        return counts
    if args.command == "record":
        cell = args.cells[0]
        path, n = record(cell, read_mapping(args.file), read_plan_file(root, cell), signs_dir, common.now_iso())
        print(f"{cell}: recorded {n} asset ids -> {path}")
        return {"recorded": n}
    total_t = total_c = total_r = 0
    for cell in args.cells:
        targets = read_plan_file(root, cell)
        cached = sum(1 for t in targets if (cache / f"{t['key']}.png").exists())
        recorded = len(build_luau.load_sign_assets(signs_dir / f"{cell}.json"))
        print(f"{cell}: {len(targets)} looks, {cached} images in the cache, {recorded} asset ids recorded")
        total_t, total_c, total_r = total_t + len(targets), total_c + cached, total_r + recorded
    return {"targets": total_t, "cached": total_c, "recorded": total_r}


def main(cfg: dict[str, Any]) -> int:
    args = parse_args(sys.argv[1:])
    if args.selftest:
        print("selftest ok: common, db, details_rules and pillow import")
        return 0
    conn = db.connect(common.resolve(cfg["db_path"]))
    started = common.now_iso()
    cell = args.cells[0] if getattr(args, "cells", None) else None
    try:
        counts = run_command(conn, cfg, args)
    except (ValueError, OSError, StopGeneration, urllib.error.URLError) as e:  # a refused or stopped call: say why, masked
        message = common.mask(f"{type(e).__name__}: {e}")
        common.log(logging.ERROR, f"refused: {message}", cell)
        print(f"refused: {message}", file=sys.stderr)
        return 1
    db.record_run(conn, cell_id=cell, unit="C8", started_at=started, finished_at=common.now_iso(), status="ok",
                  counts={"command": args.command, **counts})
    common.log(logging.INFO, f"{args.command} done", cell, **counts)
    return 0


if __name__ == "__main__":
    import PIL  # noqa: F401  (the selftest proves the pin resolves)
    common.run_cli(main, "signs")
