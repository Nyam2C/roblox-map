# /// script
# requires-python = ">=3.13"
# dependencies = [
#   "streetlevel==0.12.12", "aiohappyeyeballs==2.7.1", "aiohttp==3.14.5", "aiosignal==1.4.0", "attrs==26.1.0",
#   "bd09convertor==0.0.3", "certifi==2026.7.22", "charset-normalizer==3.5.2", "coordinatesconverter==0.1.5",
#   "frozenlist==1.8.0", "h3==4.5.0", "idna==3.20", "multidict==7.1.0", "numpy==2.5.4", "pillow==12.3.0",
#   "propcache==0.5.4", "protobuf==7.36.2", "pyproj==3.8.0", "requests==2.34.2", "scipy==1.18.1",
#   "urllib3==2.8.0", "yarl==1.25.1", "shapely==2.2.0",
# ]
#
# [tool.uv]
# exclude-dependencies = ["torch", "pyequilib", "pyexiv2", "pytest", "pytest-asyncio", "cython", "pycryptodome", "pyfrpc"]
# ///
"""Ground height of the region from the street-view panoramas already captured (2026-10-15, user: the place is not flat).

Naver gives each panorama the camera altitude in metres; the camera rides a little above the road at about the same height
everywhere, so the differences are the ground's. `collect` asks Naver for the panoramas in `captures` that have no altitude yet
(one request a second, the same safety as capture.py: 403/429 or an odd reply stops the run, never worked around) and keeps
them in regions/<region>/elevation.json (git: positions and heights only). `grid` shows them over the map as a picture.

Usage (repo root):
  uv run src/elevation.py collect --region bucheon-dodang [--limit 600]   # run again to go on where it stopped
  uv run src/elevation.py grid --region bucheon-dodang data/compare/elevation.png
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

import common
import panorama_source

PAUSE_S = 1.0


def path_of(cfg: Mapping[str, Any], region: str) -> Path:
    return common.resolve(cfg["regions_dir"]) / region / "elevation.json"


def load(path: Path) -> dict[str, list[float]]:
    """pano id -> [lat, lon, altitude m]."""
    if not path.exists():
        return {}
    return {k: [float(x) for x in v] for k, v in json.loads(path.read_text(encoding="utf-8"))["points"].items()}


def save(path: Path, points: Mapping[str, Sequence[float]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {"source": "Naver street-view camera altitude (m) of the captured panoramas", "count": len(points),
            "points": {k: [round(v[0], 7), round(v[1], 7), round(v[2], 2)] for k, v in sorted(points.items())}}
    path.write_text(json.dumps(body, ensure_ascii=False, indent=0) + "\n", encoding="utf-8")


def collect(cfg: Mapping[str, Any], region: str, limit: int, source: Any = None) -> tuple[int, str]:
    """Ask for the missing altitudes; returns (new count, stop reason: done | limit | blocked: ...)."""
    path = path_of(cfg, region)
    have = load(path)
    conn = sqlite3.connect(common.resolve(cfg["db_path"]))
    todo = [(p, lat, lon) for p, lat, lon in conn.execute("select pano_id, lat, lon from captures order by pano_id") if p not in have]
    src = source or panorama_source._Streetlevel()
    new, reason = 0, "done"
    for pid, lat, lon in todo:
        if new >= limit:
            reason = "limit"
            break
        try:
            pano = src.by_id(pid)
        except Exception as exc:  # noqa: BLE001 - classified like capture.py, a block stops the run
            err, _ = panorama_source.classify(exc)
            if isinstance(err, panorama_source.BlockedError):
                reason = f"blocked: {err}"
                break
            common.log(logging.WARNING, f"{pid}: {err}")
            time.sleep(PAUSE_S)
            continue
        alt = getattr(pano, "altitude", None) if pano is not None else None
        if isinstance(alt, (int, float)):
            have[pid] = [lat, lon, float(alt)]
            new += 1
            if new % 50 == 0:
                save(path, have)
        time.sleep(PAUSE_S)
    save(path, have)
    return new, reason


def surface(points: Sequence[Sequence[float]], step: float = 12.0):
    """(xs, zs, heights) on a regular stud grid from scattered (x, z, height) points: linear inside the points' hull, the nearest
    point outside it (the cells' edges). Street-view heights are road heights; blocks between roads take the roads around them."""
    import numpy as np
    from scipy.interpolate import griddata
    a = np.asarray(points, dtype=float)
    xs = np.arange(a[:, 0].min() - 200, a[:, 0].max() + 200 + step, step)
    zs = np.arange(a[:, 1].min() - 200, a[:, 1].max() + 200 + step, step)
    gx, gz = np.meshgrid(xs, zs)
    lin = griddata(a[:, :2], a[:, 2], (gx, gz), method="linear")
    near = griddata(a[:, :2], a[:, 2], (gx, gz), method="nearest")
    return xs, zs, np.where(np.isnan(lin), near, lin)


def grid_picture(cfg: Mapping[str, Any], region: str, out: Path) -> Path:
    """The heights as coloured dots over the cells' hexagons (low blue, high red)."""
    import h3
    from PIL import Image, ImageDraw, ImageFont
    import layout
    frame = layout.Frame.from_cfg(cfg)
    pts = [(*layout.to_studs(frame, lat, lon), alt) for lat, lon, alt in load(path_of(cfg, region)).values()]
    lo, hi = min(p[2] for p in pts), max(p[2] for p in pts)
    xs, zs = [p[0] for p in pts], [p[1] for p in pts]
    x0, x1, z0, z1 = min(xs) - 100, max(xs) + 100, min(zs) - 100, max(zs) + 100
    S = 1400 / (x1 - x0)
    img = Image.new("RGB", (1400, int((z1 - z0) * S) + 80), (245, 245, 240))
    d = ImageDraw.Draw(img)
    P = lambda x, z: ((x - x0) * S, (z - z0) * S)
    xs_, zs_, hs = surface(pts, 12.0)
    for j, z in enumerate(zs_):
        for i, x in enumerate(xs_):
            if x0 <= x <= x1 and z0 <= z <= z1:
                t = (hs[j, i] - lo) / max(hi - lo, 1e-6)
                col = (int(150 + 105 * t), int(170 + 40 * (1 - abs(2 * t - 1))), int(255 - 105 * t))
                px, pz = P(x, z)
                d.rectangle((px, pz, px + 12 * S + 1, pz + 12 * S + 1), fill=col)
    with open(common.resolve(cfg["regions_dir"]) / region / "region.toml", "rb") as f:
        import tomllib
        for c in tomllib.load(f)["cells"]:
            d.polygon([P(*layout.to_studs(frame, *q)) for q in h3.cell_to_boundary(c)], outline=(120, 120, 160), width=2)
    for x, z, a in pts:
        t = (a - lo) / max(hi - lo, 1e-6)
        col = (int(40 + 215 * t), int(90 + 60 * (1 - abs(2 * t - 1))), int(255 - 215 * t))
        px, pz = P(x, z)
        d.ellipse((px - 4, pz - 4, px + 4, pz + 4), fill=col)
    fnt = ImageFont.truetype("/System/Library/Fonts/AppleSDGothicNeo.ttc", 22)
    for k in range(6):
        a = lo + (hi - lo) * k / 5
        t = k / 5
        col = (int(40 + 215 * t), int(90 + 60 * (1 - abs(2 * t - 1))), int(255 - 215 * t))
        d.rectangle((20 + k * 150, img.height - 50, 50 + k * 150, img.height - 20), fill=col)
        d.text((56 + k * 150, img.height - 50), f"{a:.1f} m", fill=(20, 20, 20), font=fnt)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    return out


def main(cfg: dict[str, Any]) -> int:
    p = argparse.ArgumentParser(prog="elevation.py", description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect")
    c.add_argument("--region", required=True)
    c.add_argument("--limit", type=int, default=600)
    g = sub.add_parser("grid")
    g.add_argument("--region", required=True)
    g.add_argument("out")
    a = p.parse_args(sys.argv[1:])
    if a.cmd == "collect":
        new, reason = collect(cfg, a.region, a.limit)
        total = len(load(path_of(cfg, a.region)))
        common.log(logging.INFO, f"elevation: {new} new, {total} in all, stopped: {reason}")
        return 0 if not reason.startswith("blocked") else 2
    common.log(logging.INFO, f"written: {grid_picture(cfg, a.region, Path(a.out))}")
    return 0


if __name__ == "__main__":
    common.run_cli(main, "elevation")
