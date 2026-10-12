# /// script
# requires-python = ">=3.13"
# dependencies = [
#   "streetlevel==0.12.12", "aiohappyeyeballs==2.7.1", "aiohttp==3.14.5", "aiosignal==1.4.0", "attrs==26.1.0",
#   "bd09convertor==0.0.3", "certifi==2026.7.22", "charset-normalizer==3.5.2", "coordinatesconverter==0.1.5",
#   "frozenlist==1.8.0", "h3==4.5.0", "idna==3.20", "multidict==7.1.0", "numpy==2.5.4", "pillow==12.3.0",
#   "propcache==0.5.4", "protobuf==7.36.2", "pyproj==3.8.0", "requests==2.34.2", "scipy==1.18.1",
#   "urllib3==2.8.0", "yarl==1.25.1",
# ]
#
# [tool.uv]
# exclude-dependencies = ["torch", "pyequilib", "pyexiv2", "pytest", "pytest-asyncio", "cython", "pycryptodome", "pyfrpc"]
# ///
"""C3: street-view panoramas and one crop per building for the buildings of a cell.

Usage:
  uv run src/capture.py --cells 8930e0af13bffff [...]            # plan, download and crop what is missing
  uv run src/capture.py --cells 8930e0af13bffff --replan         # forget the cell's building views and start over
  uv run src/capture.py --selftest                               # import check only, no network (used by CI)

Needs buildings in data/map.db first (cells.py, register.py). Pictures go to captures/ (git-ignored, they
can show faces and plates). Stops without working around it when Naver blocks (BR-5.2).
Rules: aidlc-docs/construction/u3-street-view-capture/functional-design/business-rules.md
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import h3
from PIL import Image

import common
import db
import panorama_source as ps
import projection

PANO_QUALITY = 90  # JPEG quality of the stored panorama strip
STREAK_LIMIT = 3  # BR-5.2: this many failures of one kind in a row stop the run
LatLon = tuple[float, float]
COUNT_KEYS = ("buildings", "planned", "no_photo", "panos_found", "panos_skipped", "new_downloads", "panos_reused", "crops",
              "crops_kept", "failures", "bytes")


# --- paths (BR-3.2, BR-4.4, P3-8) -------------------------------------------------------------------

_UNSAFE = re.compile(r"[^A-Za-z0-9_.-]")


def safe_name(name: str) -> str:
    """A file name made only of letters, digits and _ . - ; colons become underscores (building ids)."""
    s = name.replace(":", "_")
    clean = _UNSAFE.sub("_", s)
    if not clean or clean != s or clean.startswith("."):  # no "..", no hidden files; the digest keeps names apart
        clean = f"{clean.lstrip('.')}-{hashlib.sha1(name.encode('utf-8', 'surrogatepass')).hexdigest()[:8]}"
    return clean


def pano_file(cell_id: str, pano_id: str) -> str:
    """Relative to captures/: the cell of the panorama's own position."""
    return f"{safe_name(cell_id)}/{safe_name(pano_id)}/zoom1.jpg"


def crop_file(cell_id: str, building_id: str, pano_id: str) -> str:
    """Relative to captures/: the cell the building belongs to."""
    return f"{safe_name(cell_id)}/crops/{safe_name(building_id)}__{safe_name(pano_id)}.jpg"


def _inside(root: Path, rel: str) -> Path:
    path = (root / rel).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f"path leaves the captures folder: {rel!r}")
    return path


def write_image(path: Path, img: Image.Image, quality: int) -> int:
    """Save through a temporary name so a half-written file is never taken for a finished one (BR-3.5)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        img.save(tmp, "JPEG", quality=quality)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    return path.stat().st_size


# --- choosing panoramas (BR-2.4, P3-3) ------------------------------------------------------------------

@dataclass(frozen=True)
class Pick:
    pano_id: str
    lat: float
    lon: float
    distance_m: float
    bearing_deg: float  # from the panorama to the building center


def _angle_gap(a: float, b: float) -> float:
    d = abs(a - b) % 360
    return min(d, 360 - d)


def select_panoramas(cands: Sequence[ps.Candidate], origin: LatLon, *, limit_m: float, separation_deg: float,
                     max_views: int, usable: Callable[[str], bool]) -> list[Pick]:
    """Nearest first (ties by id), at least `separation_deg` apart in bearing, at most `max_views`.

    `usable` (metadata check, BR-2.5) is only asked about candidates that pass the distance and bearing tests.
    The result does not depend on the order of `cands`.
    """
    near = []
    for c in cands:
        pos = (c.lat, c.lon)
        distance = projection.distance_m(pos, origin)
        if distance <= limit_m:
            near.append(Pick(c.pano_id, c.lat, c.lon, distance, projection.bearing_deg(pos, origin)))
    near.sort(key=lambda p: (p.distance_m, p.pano_id))
    picked: list[Pick] = []
    for p in near:
        if len(picked) == max_views:
            break
        if any(q.pano_id == p.pano_id or _angle_gap(p.bearing_deg, q.bearing_deg) < separation_deg for q in picked):
            continue
        if usable(p.pano_id):
            picked.append(p)
    return picked


def view_params(building: Mapping[str, Any], pano: Mapping[str, Any], cfg: Mapping[str, Any]) -> dict[str, float]:
    """Direction and crop settings of one building seen from one panorama (BR-2.3, 4.1-4.3)."""
    pos, center = (pano["lat"], pano["lon"]), tuple(building["centroid"])
    distance = projection.distance_m(pos, center)
    bearing = projection.bearing_deg(pos, center)
    extent = projection.building_extent_deg([tuple(p) for p in building["outline"]], pos)
    height = projection.building_height_m(building["height_m"], building["floors_above"], cfg)
    wall = projection.nearest_wall_m([tuple(p) for p in building["outline"]], pos)
    fov, pitch = projection.crop_params(extent, wall, height, cfg)
    return {"distance_m": distance, "bearing_deg": bearing, "yaw_deg": projection.yaw_deg(bearing, pano["heading_deg"]),
            "fov_deg": fov, "pitch_deg": pitch}


# --- the run ------------------------------------------------------------------------------------------------

class Stop(Exception):
    """Ends the whole run now. reason: cap (not an error), blocked or failures."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


class Capture:
    def __init__(self, conn, cfg: Mapping[str, Any], source: Any, root: Path | None = None) -> None:
        self.conn, self.cfg, self.source = conn, cfg, source
        self.root = Path(root) if root is not None else common.resolve(cfg["captures_dir"])
        self.panos: dict[str, dict[str, Any]] = {r["pano_id"]: r for r in db.all_captures(conn)}
        self.persisted = set(self.panos)  # panoramas whose row is in the database
        self.unusable: set[str] = set()  # metadata said no (not latest, no zoom 1, unverified heading)
        self.failed_panos: set[str] = set()  # download failed in this run: not tried again before the next run
        self.new_downloads = 0  # download attempts over the whole run, against max_new_panos
        self.streak, self.streak_kind = 0, None
        self.counts: dict[str, Any] = {}

    # failures ---------------------------------------------------------------------------------------------
    def _fail(self, kind: str, message: str, cell_id: str) -> None:
        self.counts["failures"] += 1
        common.log(logging.WARNING, f"{kind}: {message}", cell_id)
        self.streak = self.streak + 1 if kind == self.streak_kind else 1
        self.streak_kind = kind
        if self.streak >= STREAK_LIMIT:
            raise Stop("failures", f"{STREAK_LIMIT} {kind} failures in a row")

    def _ok(self) -> None:
        self.streak, self.streak_kind = 0, None

    # one cell -----------------------------------------------------------------------------------------------
    def run_cell(self, cell_id: str, replan: bool = False) -> dict[str, Any]:
        self.counts = counts = {**dict.fromkeys(COUNT_KEYS, 0), "stopped_reason": "done"}
        buildings = [b for b in db.rows_in_cells(self.conn, "buildings", [cell_id]) if b["status"] == "ok"]
        if not buildings:
            raise ValueError("no buildings stored for this cell: run register.py first")
        counts["buildings"] = len(buildings)
        if replan:
            db.backup(self.conn, common.resolve(self.cfg["backup_dir"]), self.cfg["backup_keep"])
            for rel in db.delete_views_for_cell(self.conn, cell_id):
                _inside(self.root, rel).unlink(missing_ok=True)
        rejected_before = self.source.rejected
        try:
            self._plan(cell_id, buildings)
            self._fulfil(cell_id, buildings)
        except Stop as stop:
            counts["stopped_reason"] = stop.reason
            raise
        finally:
            counts["failures"] += self.source.rejected - rejected_before  # BR-5.4: discarded replies count as failures
        return counts

    def _plan(self, cell_id: str, buildings: Sequence[Mapping[str, Any]]) -> None:
        """Buildings without any view row get their panoramas chosen and stored as `planned` (BR-1.2)."""
        have = {v["building_id"] for v in db.views_for_cell(self.conn, cell_id)}
        todo = [b for b in buildings if b["building_id"] not in have]
        for i, b in enumerate(todo, 1):
            self._attempt(cell_id, lambda b=b: self._plan_building(b), "lookup")
            if i % 10 == 0 or i == len(todo):
                common.log(logging.INFO, f"planned {i}/{len(todo)} buildings", cell_id,
                           panos_found=self.counts["panos_found"], no_photo=self.counts["no_photo"])

    def _attempt(self, cell_id: str, fn: Callable[[], Any], kind: str) -> None:
        try:
            fn()
        except ps.BlockedError as e:
            raise Stop("blocked", str(e)) from None
        except ps.SourceError as e:  # includes TransientError; this building is tried again next run
            self._fail(f"{kind} {type(e).__name__}", str(e), cell_id)
        else:
            self._ok()

    def _plan_building(self, b: Mapping[str, Any]) -> None:
        origin: LatLon = tuple(b["centroid"])
        cands = self.source.find_nearby(*origin)

        def usable(pano_id: str) -> bool:
            if pano_id in self.unusable:
                return False
            if pano_id in self.panos:
                return True
            meta = self.source.get_metadata(pano_id)
            if meta is None:
                self.unusable.add(pano_id)
                self.counts["panos_skipped"] += 1
                return False
            self.panos[pano_id] = {
                "pano_id": pano_id, "cell_id": h3.latlng_to_cell(meta.lat, meta.lon, self.cfg["h3_res"]),
                "lat": meta.lat, "lon": meta.lon, "heading_deg": meta.heading_deg, "captured_at": meta.captured_at,
                "is_latest": 1 if meta.is_latest else 0, "zoom": None, "width": None, "height": None,
                "file_path": None, "status": "found", "downloaded_at": None}
            self.counts["panos_found"] += 1
            return True

        picks = select_panoramas(cands, origin, limit_m=self.cfg["pano_limit_m"],
                                 separation_deg=self.cfg["pano_separation_deg"], max_views=self.cfg["pano_max_views"],
                                 usable=usable)
        if picks:
            views = [{"building_id": b["building_id"], "rank": rank, "pano_id": p.pano_id,
                      **view_params(b, self.panos[p.pano_id], self.cfg), "crop_path": None, "status": "planned"}
                     for rank, p in enumerate(picks, 1)]
        else:  # one row, so the next run does not look this building up again (BR-2.6)
            views = [{"building_id": b["building_id"], "rank": 1, "pano_id": None, "distance_m": None,
                      "bearing_deg": None, "yaw_deg": None, "fov_deg": None, "pitch_deg": None, "crop_path": None,
                      "status": "no_photo"}]
            self.counts["no_photo"] += 1
        new = [self.panos[p.pano_id] for p in picks if p.pano_id not in self.persisted]
        db.upsert_captures(self.conn, new)
        self.persisted.update(r["pano_id"] for r in new)
        db.upsert_building_views(self.conn, views)
        self.counts["planned"] += len(picks)

    def _fulfil(self, cell_id: str, buildings: Sequence[Mapping[str, Any]]) -> None:
        by_id = {b["building_id"]: b for b in buildings}
        views = [v for v in db.views_for_cell(self.conn, cell_id) if v["pano_id"] and v["building_id"] in by_id]
        for i, v in enumerate(views, 1):
            self._fulfil_view(cell_id, by_id[v["building_id"]], v)
            if i % 25 == 0 or i == len(views):
                c = self.counts
                common.log(logging.INFO, f"views {i}/{len(views)}", cell_id, new_panos=f"{self.new_downloads}/{self.cfg['max_new_panos']}",
                           crops=c["crops"], kept=c["crops_kept"], failures=c["failures"])

    def _fulfil_view(self, cell_id: str, b: Mapping[str, Any], v: dict[str, Any]) -> None:
        pano = self.panos.get(v["pano_id"])
        if pano is None or v["pano_id"] in self.failed_panos:
            return
        params = view_params(b, pano, self.cfg)
        rel = crop_file(b["cell_id"], b["building_id"], v["pano_id"])
        if (v["status"] == "cropped" and v["crop_path"] == rel and _inside(self.root, rel).is_file()
                and all(math.isclose(v[k], params[k], abs_tol=1e-6) for k in params)):
            self.counts["crops_kept"] += 1  # BR-4.5
            return
        reused = bool(pano["file_path"]) and _inside(self.root, pano["file_path"]).is_file()
        strip_path = self._ensure_pano(cell_id, pano)
        if strip_path is None:
            return
        self.counts["panos_reused"] += reused
        try:
            with Image.open(strip_path) as strip:
                faces = projection.split_faces(strip)
            img = projection.render_crop(faces, params["yaw_deg"], params["pitch_deg"], params["fov_deg"],
                                         (self.cfg["crop_width"], self.cfg["crop_height"]))
            size = write_image(_inside(self.root, rel), img, self.cfg["crop_quality"])
        except Exception as e:  # BR-4.6: one bad crop does not stop the others
            db.upsert_building_views(self.conn, [{**v, **params, "crop_path": None, "status": "failed"}])
            self._fail("crop", f"{b['building_id']}: {type(e).__name__}: {e}", cell_id)
            return
        db.upsert_building_views(self.conn, [{**v, **params, "crop_path": rel, "status": "cropped"}])
        self.counts["crops"] += 1
        self.counts["bytes"] += size
        self._ok()

    def _ensure_pano(self, cell_id: str, pano: dict[str, Any]) -> Path | None:
        """The stored strip of this panorama, downloading it if it is missing (BR-3.1). None if that failed."""
        pano_id = pano["pano_id"]
        if pano["file_path"] and _inside(self.root, pano["file_path"]).is_file():
            return _inside(self.root, pano["file_path"])
        if pano_id in self.failed_panos:
            return None
        if self.new_downloads >= self.cfg["max_new_panos"]:
            raise Stop("cap", f"{self.cfg['max_new_panos']} new panoramas downloaded; run again to continue")
        self.new_downloads += 1  # attempts count: each one is a call to Naver
        try:
            strip = self.source.download_strip(pano_id)
        except ps.BlockedError as e:
            raise Stop("blocked", str(e)) from None
        except ps.SourceError as e:
            self.failed_panos.add(pano_id)
            self.panos[pano_id] = {**pano, "status": "failed"}
            db.upsert_captures(self.conn, [self.panos[pano_id]])
            self._fail(f"download {type(e).__name__}", f"{pano_id}: {e}", cell_id)
            return None
        rel = pano_file(pano["cell_id"], pano_id)
        size = write_image(_inside(self.root, rel), strip, PANO_QUALITY)
        row = {**pano, "zoom": ps.ZOOM, "width": strip.width, "height": strip.height, "file_path": rel,
               "status": "downloaded", "downloaded_at": common.now_iso()}
        (_inside(self.root, rel).parent / "meta.json").write_text(json.dumps(row, ensure_ascii=False, indent=1), encoding="utf-8")
        db.upsert_captures(self.conn, [row])
        self.panos[pano_id] = row
        self.persisted.add(pano_id)
        self.counts["new_downloads"] += 1
        self.counts["bytes"] += size
        self._ok()
        return _inside(self.root, rel)


# --- command line ---------------------------------------------------------------------------------------------

def parse_args(argv: Sequence[str], res: int) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="capture.py", description=__doc__.split("\n")[0])
    parser.add_argument("--cells", nargs="+", metavar="ID", help="H3 cell IDs to process")
    parser.add_argument("--replan", action="store_true", help="forget the cells' building views and plan again")
    parser.add_argument("--selftest", action="store_true", help="check that the libraries import; no network")
    ns = parser.parse_args(list(argv))
    if ns.selftest:
        return ns
    if not ns.cells:
        parser.error("--cells is required (or use --selftest)")
    bad = [c for c in ns.cells if not (h3.is_valid_cell(c) and h3.get_resolution(c) == res)]
    if bad:
        parser.error(f"not valid resolution-{res} H3 cell IDs: {bad}")
    return ns


def main(cfg: dict[str, Any]) -> int:
    args = parse_args(sys.argv[1:], cfg["h3_res"])
    try:
        source = ps.PanoramaSource(pause_s=cfg["pano_pause_s"], waits=cfg["retry_waits_s"])
    except ps.SourceUnavailable as e:  # BR-5.3: do not start; switching to Playwright would be a new task
        common.log(logging.ERROR, str(e))
        return 1
    if args.selftest:
        print("selftest ok: streetlevel, numpy, pillow and h3 import")
        return 0
    conn = db.connect(common.resolve(cfg["db_path"]))
    capture = Capture(conn, cfg, source)
    failed = 0
    for cell_id in args.cells:
        started = common.now_iso()
        try:
            counts = capture.run_cell(cell_id, args.replan)
            db.record_run(conn, cell_id=cell_id, unit="C3", started_at=started, finished_at=common.now_iso(),
                          status="ok", counts=counts)
            common.log(logging.INFO, "cell done", cell_id, **counts)
        except Stop as stop:
            error = None if stop.reason == "cap" else common.mask(str(stop))
            db.record_run(conn, cell_id=cell_id, unit="C3", started_at=started, finished_at=common.now_iso(),
                          status="ok" if stop.reason == "cap" else "stopped", counts=capture.counts, error=error)
            common.log(logging.WARNING if stop.reason == "cap" else logging.ERROR, f"stopped ({stop.reason}): {stop}",
                       cell_id, **capture.counts)
            failed += 0 if stop.reason == "cap" else 1
            break  # the remaining cells wait for the next run
        except Exception as e:  # keep what was stored and carry on with the next cell
            failed += 1
            message = common.mask(f"{type(e).__name__}: {e}")
            common.log(logging.ERROR, f"cell failed: {message}", cell_id)
            db.record_run(conn, cell_id=cell_id, unit="C3", started_at=started, finished_at=common.now_iso(),
                          status="failed", counts=capture.counts or None, error=message)
    for building_id in db.orphan_views(conn):
        common.log(logging.WARNING, f"orphan: building_views row for missing building {building_id}")
    return 1 if failed else 0


if __name__ == "__main__":
    common.run_cli(main, "capture")
