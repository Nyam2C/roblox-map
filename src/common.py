"""Shared infrastructure for the U1 scripts: config, secrets, logging, retrying HTTP GET, CLI runner.

Standard library only. Design: aidlc-docs/construction/u1-data-foundation/nfr-design/
"""
from __future__ import annotations

import json
import logging
import os
import re
import socket
import sys
import time
import tomllib
import traceback
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

ROOT = Path(__file__).resolve().parent.parent

DEFAULTS: dict[str, Any] = {
    "h3_res": 9,
    "overlap_threshold": 0.5,
    "buffer_m": 150,
    "overpass_pause_s": 1,
    "vworld_pause_s": 0.5,
    "vworld_page_size": 1000,
    "retry_waits_s": [10, 30, 60],
    "db_path": "data/map.db",
    "log_dir": "data/logs",
    "backup_dir": "data/backups",
    "backup_keep": 5,
}

RETRY_CODES = {429, 502, 504}
MASK = "<KEY>"


# --- config ------------------------------------------------------------------------

def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """Read config.toml, fill missing keys with DEFAULTS and check types and ranges."""
    cfg = dict(DEFAULTS)
    p = Path(path) if path is not None else ROOT / "config.toml"
    if p.exists():
        with p.open("rb") as f:
            data = tomllib.load(f)
        unknown = sorted(set(data) - set(DEFAULTS))
        if unknown:
            raise ValueError(f"config: unknown keys {unknown}")
        cfg.update(data)
    errors = []
    if not (isinstance(cfg["h3_res"], int) and not isinstance(cfg["h3_res"], bool) and 0 <= cfg["h3_res"] <= 15):
        errors.append("h3_res must be an integer from 0 to 15")
    if not (_is_number(cfg["overlap_threshold"]) and 0 < cfg["overlap_threshold"] <= 1):
        errors.append("overlap_threshold must be in (0, 1]")
    if not (_is_number(cfg["buffer_m"]) and 0 < cfg["buffer_m"] <= 2000):
        errors.append("buffer_m must be in (0, 2000]")
    for k in ("overpass_pause_s", "vworld_pause_s"):
        if not (_is_number(cfg[k]) and cfg[k] >= 0):
            errors.append(f"{k} must be a number >= 0")
    size = cfg["vworld_page_size"]
    if not (isinstance(size, int) and not isinstance(size, bool) and 1 <= size <= 1000):
        errors.append("vworld_page_size must be an integer from 1 to 1000")
    waits = cfg["retry_waits_s"]
    if not (isinstance(waits, list) and all(_is_number(w) and w >= 0 for w in waits)):
        errors.append("retry_waits_s must be a list of numbers >= 0")
    for k in ("db_path", "log_dir", "backup_dir"):
        if not (isinstance(cfg[k], str) and cfg[k].strip()):
            errors.append(f"{k} must be a non-empty string")
    keep = cfg["backup_keep"]
    if not (isinstance(keep, int) and not isinstance(keep, bool) and keep >= 0):
        errors.append("backup_keep must be an integer >= 0")
    if errors:
        raise ValueError("config: " + "; ".join(errors))
    return cfg


def resolve(path: str | Path) -> Path:
    """Relative paths in the config are relative to the repository root."""
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


# --- secrets and masking ------------------------------------------------------------

class MissingSecretError(RuntimeError):
    pass


_SECRETS: set[str] = set()
_KEY_PARAM = re.compile(r"(?i)\b(key|servicekey|apikey)=[^&\s\"']+")


def get_secret(name: str, environ: Mapping[str, str] | None = None) -> str:
    """Read a secret from the environment, trimming surrounding whitespace (BR-7.5)."""
    env = os.environ if environ is None else environ
    value = (env.get(name) or "").strip()
    if not value:
        raise MissingSecretError(f"environment variable {name} is not set (see .env.example)")
    _SECRETS.add(value)
    _SECRETS.add(urllib.parse.quote(value, safe=""))
    return value


def mask(text: str) -> str:
    """Hide known secret values and key= query values."""
    for secret in sorted(_SECRETS, key=len, reverse=True):
        text = text.replace(secret, MASK)
    return _KEY_PARAM.sub(lambda m: m.group(0).split("=", 1)[0] + "=" + MASK, text)


# --- logging ------------------------------------------------------------------------

class _JsonFormatter(logging.Formatter):
    def __init__(self, script: str) -> None:
        super().__init__()
        self.script = script

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="seconds"),
            "level": record.levelname,
            "script": self.script,
            "cell_id": getattr(record, "cell_id", None),
            "msg": record.getMessage(),
        }
        extra = getattr(record, "fields", None)
        if extra:
            entry["extra"] = extra
        if record.exc_info:
            entry["traceback"] = "".join(traceback.format_exception(*record.exc_info))
        return mask(json.dumps(entry, ensure_ascii=False, default=str))


class _ConsoleFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        t = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
        cell = getattr(record, "cell_id", None)
        where = f" [{cell}]" if cell else ""
        fields = getattr(record, "fields", None)
        tail = " " + " ".join(f"{k}={v}" for k, v in fields.items()) if fields else ""
        return mask(f"{t} {record.levelname}{where} {record.getMessage()}{tail}")


def setup_logging(script: str, log_dir: str | Path, console_stream: Any = None) -> logging.Logger:
    """JSON lines in log_dir/<script>-<date>.jsonl, a readable summary on the console. Idempotent."""
    logger = logging.getLogger("roblox_map")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    for h in list(logger.handlers):
        logger.removeHandler(h)
        h.close()
    d = Path(log_dir)
    d.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(d / f"{script}-{datetime.now().strftime('%Y%m%d')}.jsonl", encoding="utf-8")
    file_handler.setFormatter(_JsonFormatter(script))
    console = logging.StreamHandler(console_stream or sys.stderr)
    console.setFormatter(_ConsoleFormatter())
    logger.addHandler(file_handler)
    logger.addHandler(console)
    return logger


def log(level: int, msg: str, cell_id: str | None = None, **fields: Any) -> None:
    logging.getLogger("roblox_map").log(level, msg, extra={"cell_id": cell_id, "fields": fields or None})


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --- HTTP ---------------------------------------------------------------------------

class HttpError(RuntimeError):
    def __init__(self, status: int | None, message: str) -> None:
        super().__init__(message)
        self.status = status


def http_get_json(url: str, params: Mapping[str, Any] | None = None, *,
                  waits: list[float] | None = None, pause_s: float = 0.0, timeout: float = 90.0,
                  headers: Mapping[str, str] | None = None,
                  opener: Callable[..., Any] = urllib.request.urlopen,
                  sleep: Callable[[float], None] = time.sleep) -> Any:
    """GET a JSON document over HTTPS.

    Retries 429/502/504 and timeouts after each wait in `waits` (BR-7.3), nothing else.
    Certificate verification is never disabled. Errors never contain the key (BR-7.5).
    """
    full = url + ("?" + urllib.parse.urlencode(params) if params else "")
    if not full.lower().startswith("https://"):
        raise ValueError("only https:// URLs are allowed")
    schedule: list[float | None] = list(DEFAULTS["retry_waits_s"] if waits is None else waits) + [None]
    request_headers = {"User-Agent": "roblox-map/0", **(headers or {})}
    body: bytes | None = None
    for wait in schedule:
        try:
            req = urllib.request.Request(full, headers=request_headers)
            with opener(req, timeout=timeout) as resp:
                body = resp.read()
            break
        except urllib.error.HTTPError as e:
            if e.code not in RETRY_CODES or wait is None:
                raise HttpError(e.code, mask(f"HTTP {e.code} from {full}")) from None
            log(logging.WARNING, f"HTTP {e.code}, retrying in {wait}s")
        except (TimeoutError, socket.timeout) as e:
            if wait is None:
                raise HttpError(None, mask(f"timeout from {full}")) from None
            log(logging.WARNING, f"timeout, retrying in {wait}s")
        except urllib.error.URLError as e:
            if isinstance(e.reason, (TimeoutError, socket.timeout)) and wait is not None:
                log(logging.WARNING, f"timeout, retrying in {wait}s")
            else:
                raise HttpError(None, mask(f"request failed ({type(e.reason).__name__}) for {full}")) from None
        sleep(wait)  # only reached when a retry follows
    if pause_s:
        sleep(pause_s)
    try:
        return json.loads(body.decode("utf-8"))  # JSON only, never pickle or eval (SECURITY-13)
    except (UnicodeDecodeError, ValueError):
        raise ValueError(mask(f"response from {full} is not valid JSON")) from None


# --- CLI runner ---------------------------------------------------------------------

def run(main: Callable[[dict[str, Any]], int | None], script: str, cfg: dict[str, Any] | None = None) -> int:
    """Run main(cfg) with logging and a top-level error handler. Returns the exit code.

    Unhandled errors are logged with secrets masked and end with code 1; Ctrl-C ends with 130.
    """
    try:
        cfg = cfg or load_config()
        setup_logging(script, resolve(cfg["log_dir"]))
    except Exception as e:  # config or log directory problems: nothing to log to yet
        print(mask(f"startup error: {type(e).__name__}: {e}"), file=sys.stderr)
        return 1
    try:
        return int(main(cfg) or 0)
    except KeyboardInterrupt:
        log(logging.WARNING, "interrupted")
        return 130
    except SystemExit as e:  # argparse usage errors and explicit exits
        return e.code if isinstance(e.code, int) else 1
    except Exception as e:
        logging.getLogger("roblox_map").error(f"{type(e).__name__}: {e}", exc_info=True)
        return 1


def run_cli(main: Callable[[dict[str, Any]], int | None], script: str) -> None:
    sys.exit(run(main, script))
