"""D2: read the published ledger without cloning the repo.

    import tirramind
    tirramind.load("delistings")           # DataFrame
    tirramind.events(since="2025-01-01")
    tirramind.form144(since="2025-06-01")

Files are fetched from the repo's raw URL and cached locally by ETag-less
content hash for ``ttl`` seconds. Point ``TIRRAMIND_DATA`` at a local
``data/`` directory to read a checkout instead.
"""

from __future__ import annotations

import hashlib
import os
import time

import pandas as pd

RAW = "https://raw.githubusercontent.com/savabs/tirramind-universe/main/data/"
TABLES = {"tickers": "tickers_latest.parquet", "events": "events.parquet",
          "delistings": "delistings.parquet", "filings": "filings.parquet",
          "form144": "form144_links.parquet", "form144_raw": "form144.parquet",
          "form4_sales": "form4_sales.parquet", "accuracy": "accuracy.parquet",
          "disagreements": "disagreements_nasdaq.parquet"}
CACHE = os.path.join(os.path.expanduser("~"), ".cache", "tirramind")


def _local_dir() -> str | None:
    return os.environ.get("TIRRAMIND_DATA") or None


def _fetch(name: str, ttl: int) -> str:
    fname = TABLES[name]
    local = _local_dir()
    if local:
        return os.path.join(local, fname)
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, fname)
    if os.path.exists(path) and time.time() - os.path.getmtime(path) < ttl:
        return path
    import requests
    r = requests.get(RAW + fname, timeout=120)
    r.raise_for_status()
    tmp = path + f".{hashlib.md5(r.content).hexdigest()[:8]}.tmp"
    with open(tmp, "wb") as fh:
        fh.write(r.content)
    os.replace(tmp, path)
    return path


def load(name: str, *, ttl: int = 3600) -> pd.DataFrame:
    if name not in TABLES:
        raise KeyError(f"unknown table {name!r}; one of {sorted(TABLES)}")
    return pd.read_parquet(_fetch(name, ttl))


def events(*, since: str | None = None, event: str | None = None, **kw) -> pd.DataFrame:
    df = load("events", **kw)
    if since:
        df = df[df["to_captured_at"] >= since]
    if event:
        df = df[df["event"].eq(event)]
    return df.reset_index(drop=True)


def delistings(*, since: str | None = None, cause: str | None = None, **kw) -> pd.DataFrame:
    df = load("delistings", **kw)
    if since:
        df = df[df["to_captured_at"] >= since]
    if cause:
        df = df[df["cause"].eq(cause)]
    return df.reset_index(drop=True)


def form144(*, since: str | None = None, **kw) -> pd.DataFrame:
    df = load("form144", **kw)
    if since:
        df = df[df["notice_date"] >= since]
    return df.reset_index(drop=True)
