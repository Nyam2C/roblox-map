"""U3 adapter: Naver street-view panoramas through the `streetlevel` library. The only place that talks to Naver.

Pacing, retries and error classification live here so capture.py only sees four outcomes:
  - BlockedError    403/429 that survive the retries, or a reply that is not the expected shape: stop, never work around
  - TransientError  timeouts and server errors that survive the retries
  - SourceError     anything else for one panorama (404, wrong image size)
  - SourceUnavailable  the library cannot be imported: do not start (BR-5.3)
Layout and heading facts: aidlc-docs/construction/u3-street-view-capture/code/layout-notes.md
Rules: business-rules.md BR-2.1, 2.5, 3.3, 3.5, 5.1-5.4 and the U3 NFR (SEC3, SEC5, SEC6)
"""
from __future__ import annotations

import logging
import math
import sys
import time
import types
from dataclasses import dataclass
from typing import Any, Callable, Sequence

from PIL import Image

import common
import projection

# SEC3: Pillow's decompression-bomb guard stays on with an explicit limit. A zoom-1 strip is 6144x1024 = 6.3 MP.
MAX_IMAGE_PIXELS = 8_000_000
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS

ZOOM = 1
STRIP_SIZE = (6144, 1024)  # zoom 1: six 1024 px faces side by side (BR-3.5)
REQUEST_TIMEOUT_S = 30
MAX_DISTANCE_M = 1000.0  # BR-5.4: a reply further than this from the request point is discarded
MESH_PANORAMA_TYPE = 15  # by-id replies of type 15 were the only ones whose heading was verified (+180 degrees)

# streetlevel and its HTTP libraries raise these; matched by class name so this module imports without them
_TRANSIENT = {"Timeout", "ReadTimeout", "ConnectTimeout", "ServerTimeoutError", "ConnectionError",
              "ClientConnectionError", "ClientOSError", "ServerDisconnectedError", "ChunkedEncodingError"}
_BAD_FORMAT = {"JSONDecodeError", "UnidentifiedImageError", "DecompressionBombError", "DecompressionBombWarning",
               "KeyError", "TypeError", "ValueError", "IndexError", "AttributeError"}


class SourceError(RuntimeError):
    pass


class BlockedError(SourceError):
    pass


class TransientError(SourceError):
    pass


class SourceUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class Candidate:
    pano_id: str
    lat: float
    lon: float


@dataclass(frozen=True)
class PanoMeta:
    pano_id: str
    lat: float
    lon: float
    heading_deg: float  # direction the front face looks, north 0, clockwise
    captured_at: str | None  # as Naver reports it (time zone not stated)
    is_latest: bool
    max_zoom: int


def classify(exc: BaseException) -> tuple[SourceError, bool]:
    """Turn a library or network exception into (error, retry?). Fail closed: unknown shapes count as blocked."""
    names = {c.__name__ for c in type(exc).__mro__}
    status = getattr(exc, "status", None) or getattr(getattr(exc, "response", None), "status_code", None)
    label = f"{type(exc).__name__}" + (f" (HTTP {status})" if status else "")
    if status in (403, 429):
        return BlockedError(f"blocked: {label}"), True  # retried after the waits, blocked if it persists (BR-5.2)
    if status is not None and status >= 500:
        return TransientError(f"server error: {label}"), True
    if names & _TRANSIENT or isinstance(exc, TimeoutError):
        return TransientError(f"transient: {label}"), True
    if names & _BAD_FORMAT:
        return BlockedError(f"unexpected reply format: {label}"), False
    return SourceError(f"request failed: {label}"), False


def _valid_position(lat: Any, lon: Any, around: tuple[float, float]) -> bool:
    ok = all(isinstance(v, (int, float)) and math.isfinite(v) for v in (lat, lon))
    return ok and -90 <= lat <= 90 and -180 <= lon <= 180 and projection.distance_m(around, (lat, lon)) <= MAX_DISTANCE_M


class _Streetlevel:
    """Thin wrapper over streetlevel's Naver module. Imports late; tests pass a fake with the same three methods."""

    def __init__(self) -> None:
        # streetlevel imports pyexiv2 to write EXIF, which we never do, and the real package needs a system
        # library. It is only named in a type annotation, so a stub is enough (checked for streetlevel 0.12.12).
        sys.modules.setdefault("pyexiv2", types.SimpleNamespace(ImageData=object))
        try:
            import requests
            from streetlevel import naver
            from streetlevel.naver.panorama import NaverPanorama
            from streetlevel.util import CubemapStitchingMethod
        except ImportError as e:
            raise SourceUnavailable(
                f"streetlevel is not installed ({e}); run through `uv run src/capture.py` so the inline "
                "dependencies are installed") from None
        self._naver, self._panorama_cls, self._row = naver, NaverPanorama, CubemapStitchingMethod.ROW

        class _Session(requests.Session):  # streetlevel sets no timeout and never checks the status code
            def request(self, *args: Any, **kwargs: Any) -> Any:
                kwargs.setdefault("timeout", REQUEST_TIMEOUT_S)
                response = super().request(*args, **kwargs)
                response.raise_for_status()
                return response

        self._session = _Session()

    def nearby(self, lat: float, lon: float) -> Any:
        return self._naver.find_panorama(lat, lon, neighbors=True, historical=False, session=self._session)

    def by_id(self, pano_id: str) -> Any:
        return self._naver.find_panorama_by_id(pano_id, neighbors=False, historical=False, session=self._session)

    def strip(self, pano_id: str) -> Image.Image:
        # zoom 1 needs only the id. ponytail: tile downloads use aiohttp's own default timeout (5 min), no override
        pano = self._panorama_cls(id=pano_id, lat=0.0, lon=0.0)
        return self._naver.get_panorama(pano, zoom=ZOOM, stitching_method=self._row)


class PanoramaSource:
    def __init__(self, *, pause_s: float, waits: Sequence[float], lib: Any = None,
                 sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic) -> None:
        self._lib = lib if lib is not None else _Streetlevel()  # fails here, before any work starts (BR-5.3)
        self._pause_s, self._waits, self._sleep, self._clock = pause_s, list(waits), sleep, clock
        self._last: float | None = None
        self.rejected = 0  # replies discarded by the BR-5.4 checks, counted as failures by the caller

    def _request(self, fn: Callable[[], Any]) -> Any:
        """One paced call (BR-3.3) with the retry waits (BR-5.1); raises the classified error."""
        for wait in [*self._waits, None]:
            if self._last is not None:
                self._sleep(max(0.0, self._pause_s - (self._clock() - self._last)))
            try:
                return fn()
            except Exception as e:
                error, retry = classify(e)
            finally:
                self._last = self._clock()
            if not retry or wait is None:
                raise error from None  # no chained traceback: library errors can carry URLs
            common.log(logging.WARNING, f"{error}, retrying in {wait}s")
            self._sleep(wait)
        raise AssertionError("unreachable")

    def find_nearby(self, lat: float, lon: float) -> list[Candidate]:
        """The nearest panorama plus its street neighbors, without the `other` kinds (BR-2.1). Heading is not known yet."""
        found = self._request(lambda: self._lib.nearby(lat, lon))
        if found is None:
            return []
        raw = [found, *(found.neighbors.street if found.neighbors else [])]
        candidates: dict[str, Candidate] = {}
        for p in raw:
            if isinstance(p.id, str) and p.id and _valid_position(p.lat, p.lon, (lat, lon)):
                candidates.setdefault(p.id, Candidate(p.id, float(p.lat), float(p.lon)))
            else:
                self.rejected += 1
        return list(candidates.values())

    def get_metadata(self, pano_id: str) -> PanoMeta | None:
        """Heading, date and size for one panorama, or None when it cannot be used (BR-2.5, D-U3-1).

        Unusable: unknown id, not the latest shot, no zoom 1, or not the 3D kind whose heading was verified.
        The by-id heading is 180 degrees off the front face for those (layout-notes.md), so it is turned here.
        """
        p = self._request(lambda: self._lib.by_id(pano_id))
        if p is None or p.id != pano_id:
            return None
        if not _valid_position(p.lat, p.lon, (p.lat, p.lon)):
            self.rejected += 1
            return None
        if not p.is_latest or not p.max_zoom or p.max_zoom < ZOOM or int(p.panorama_type) != MESH_PANORAMA_TYPE \
                or p.heading is None:
            return None
        heading = (math.degrees(p.heading) + 180.0) % 360.0
        return PanoMeta(pano_id, float(p.lat), float(p.lon), 0.0 if heading >= 360.0 else heading,
                        p.date.isoformat() if p.date else None, True, int(p.max_zoom))

    def download_strip(self, pano_id: str) -> Image.Image:
        """The zoom-1 cube-map strip (6144x1024 RGB), checked before anyone writes it to disk (BR-3.5, SEC3)."""
        strip = self._request(lambda: self._lib.strip(pano_id))
        if not isinstance(strip, Image.Image) or strip.size != STRIP_SIZE or strip.mode != "RGB":
            raise SourceError(f"unexpected panorama image {getattr(strip, 'size', None)}, expected {STRIP_SIZE}")
        return strip
