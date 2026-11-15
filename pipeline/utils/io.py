"""Shared I/O helpers: settings, paths, months, CSV upserts, JSON, logging."""
from __future__ import annotations

import csv
import datetime as dt
import json
import os
import re
import time
import unicodedata
from pathlib import Path
from typing import Iterable

import yaml

ROOT = Path(__file__).resolve().parents[2]
_T0 = time.time()


def step(message: str) -> None:
    """Timestamped progress line."""
    print(f"[{time.time() - _T0:6.0f} s] {message}", flush=True)


def load_env() -> None:
    """Load .env (EARTHDATA_USER, EARTHDATA_PASS, GEE_PROJECT) if python-dotenv is installed."""
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover
        return
    load_dotenv(ROOT / ".env")


def load_settings(path: str | os.PathLike | None = None) -> dict:
    path = Path(path) if path else ROOT / "config" / "settings.yaml"
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    if cfg.get("baseline", {}).get("end") in (None, "auto"):
        cfg["baseline"]["end"] = last_complete_month()
    return cfg


def path(cfg: dict, key: str, *parts: str) -> Path:
    """Absolute path under one of the configured folders, created on demand."""
    p = ROOT / cfg["paths"][key]
    full = p.joinpath(*parts)
    (full if not full.suffix else full.parent).mkdir(parents=True, exist_ok=True)
    return full


def rel(p: os.PathLike) -> str:
    try:
        return str(Path(p).resolve().relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(p)


# ---------------------------------------------------------------------------
# Months
# ---------------------------------------------------------------------------
MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def last_complete_month(today: dt.date | None = None) -> str:
    today = today or dt.date.today()
    first = today.replace(day=1)
    prev = first - dt.timedelta(days=1)
    return prev.strftime("%Y-%m")


def month_range(start: str, end: str) -> list[str]:
    if not (MONTH_RE.match(start) and MONTH_RE.match(end)):
        raise ValueError(f"months must be YYYY-MM, got {start!r} / {end!r}")
    y, m = int(start[:4]), int(start[5:])
    ye, me = int(end[:4]), int(end[5:])
    out = []
    while (y, m) <= (ye, me):
        out.append(f"{y}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def month_bounds(month: str) -> tuple[str, str]:
    """ISO start (inclusive) and end (exclusive) dates of a month."""
    y, m = int(month[:4]), int(month[5:])
    nxt = f"{y + 1}-01-01" if m == 12 else f"{y}-{m + 1:02d}-01"
    return f"{month}-01", nxt


def shift_month(month: str, n: int) -> str:
    y, m = int(month[:4]), int(month[5:])
    k = y * 12 + (m - 1) + n
    return f"{k // 12}-{k % 12 + 1:02d}"


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------
def upsert_csv(file: os.PathLike, rows: Iterable[dict], keys: list[str], columns: list[str]) -> int:
    """Merge rows into a CSV keyed by `keys` (new rows win). Returns the row count."""
    file = Path(file)
    merged: dict[tuple, dict] = {}
    if file.is_file():
        with open(file, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                merged[tuple(r.get(k, "") for k in keys)] = r
    for r in rows:
        merged[tuple(str(r[k]) for k in keys)] = {c: ("" if r.get(c) is None else r.get(c)) for c in columns}
    file.parent.mkdir(parents=True, exist_ok=True)
    with open(file, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore", restval="")
        w.writeheader()
        w.writerows(sorted(merged.values(), key=lambda r: tuple(str(r.get(k, "")) for k in keys)))
    return len(merged)


def write_json(file: os.PathLike, obj, indent: int | None = None) -> None:
    file = Path(file)
    file.parent.mkdir(parents=True, exist_ok=True)
    with open(file, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=indent, separators=None if indent else (",", ":"),
                  allow_nan=False, default=_json_default)
        f.write("\n")


def _json_default(o):
    import numpy as np

    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    raise TypeError(f"not JSON serialisable: {type(o)}")


def read_json(file: os.PathLike, default=None):
    file = Path(file)
    if not file.is_file():
        return default
    with open(file, encoding="utf-8") as f:
        return json.load(f)


def slugify(text: str) -> str:
    t = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", t.lower()).strip("_")


# ---------------------------------------------------------------------------
# Catalog lookups
# ---------------------------------------------------------------------------
def load_catalog(cfg: dict) -> dict:
    file = path(cfg, "processed", "reservoirs.geojson")
    data = read_json(file)
    if not data:
        raise SystemExit(f"{rel(file)} not found: run pipeline/01_build_catalog.py first.")
    return data


def resolve_reservoirs(cfg: dict, selector: str | None, default: str = "priority") -> list[dict]:
    """Features selected by --reservoir: an ID (MAR_0002), a name slug (al_massira), a
    comma list, or the keywords 'priority', 'demo', 'all'."""
    feats = load_catalog(cfg)["features"]
    sel = (selector or default).strip()
    if sel == "all":
        return feats
    if sel == "priority":
        return [f for f in feats if f["properties"].get("priority")]
    if sel == "demo":
        return [f for f in feats if f["properties"].get("demo")]
    out = []
    for token in [s.strip() for s in sel.split(",") if s.strip()]:
        hits = [f for f in feats if f["properties"]["reservoir_id"] == token.upper()]
        if not hits:
            slug = slugify(token)
            hits = [f for f in feats if f["properties"].get("slug") == slug]
            if not hits:
                hits = [f for f in feats if slug and slug in f["properties"].get("slug", "")]
        if not hits:
            raise SystemExit(f"Unknown reservoir {token!r} (use an ID like MAR_0001 or a name like al_massira).")
        out.append(hits[0])
    return out
