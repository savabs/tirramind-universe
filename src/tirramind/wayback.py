"""B3: backfill the ticker map from the Wayback Machine (2017 -> day 0).

Wayback captured ``company_tickers.json`` roughly monthly. Each distinct
capture becomes a snapshot stamped with the Wayback timestamp and
``source="wayback"`` so it is never confused with our own daily captures.
The exchange file is not reliably archived; those rows carry exchange="".
"""

from __future__ import annotations

from datetime import datetime, timezone

import requests

from .store import DEFAULT_ROOT, snapshot
from .tickers import TICKERS_URL, canonical_frame

CDX = "https://web.archive.org/cdx/search/cdx"


def list_captures(url: str = TICKERS_URL, session: requests.Session | None = None) -> list[str]:
    """Wayback timestamps (YYYYmmddHHMMSS) of 200-status captures, deduped by digest."""
    s = session or requests.Session()
    r = s.get(CDX, params={
        "url": url, "output": "json", "filter": "statuscode:200",
        "collapse": "digest", "fl": "timestamp,digest",
    }, timeout=60)
    r.raise_for_status()
    rows = r.json()
    return [row[0] for row in rows[1:]] if rows else []


def fetch_capture(ts: str, url: str = TICKERS_URL, session: requests.Session | None = None) -> dict:
    s = session or requests.Session()
    r = s.get(f"https://web.archive.org/web/{ts}id_/{url}", timeout=120)
    r.raise_for_status()
    return r.json()


def backfill(*, root: str = DEFAULT_ROOT, session: requests.Session | None = None,
             limit: int | None = None) -> list[tuple[str, str, int]]:
    s = session or requests.Session()
    s.headers.setdefault("User-Agent", "tirramind-backfill (github.com/savabs/tirramind-universe)")
    stamps = list_captures(session=s)
    if limit:
        stamps = stamps[:limit]
    print(f"wayback: {len(stamps)} distinct captures")
    written = []
    for ts in stamps:
        try:
            data = fetch_capture(ts, session=s)
            df = canonical_frame(data, None)
        except Exception as e:  # noqa: BLE001
            print(f"{ts}  FAIL  {type(e).__name__}: {str(e)[:80]}")
            continue
        if len(df) < 3000:
            print(f"{ts}  SKIP  {len(df)} rows (truncated capture)")
            continue
        when = datetime.strptime(ts, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
        path, dg, status = snapshot("tickers", df, root=root, captured_at=when, source="wayback")
        print(f"{ts}  {len(df):>6} rows  {status} ({dg})")
        written.append((ts, status, len(df)))
    return written


# -- exchange file ------------------------------------------------------------
from .tickers import EXCHANGE_URL  # noqa: E402


def backfill_exchange(*, root: str = DEFAULT_ROOT, session: requests.Session | None = None) -> int:
    """Wayback captures of company_tickers_exchange.json (2021-07 ->) stored as
    ``exchange`` snapshots so historical events can be labelled with the
    exchange they were on at the time."""
    import pandas as pd
    s = session or requests.Session()
    s.headers.setdefault("User-Agent", "tirramind-backfill (github.com/savabs/tirramind-universe)")
    n = 0
    for ts in list_captures(EXCHANGE_URL, session=s):
        try:
            data = fetch_capture(ts, EXCHANGE_URL, session=s)
            df = pd.DataFrame(data["data"], columns=data["fields"])
        except Exception as e:  # noqa: BLE001
            print(f"{ts}  FAIL  {type(e).__name__}: {str(e)[:80]}")
            continue
        df["cik"] = df["cik"].map(lambda c: f"{int(c):010d}")
        df["ticker"] = df["ticker"].astype(str).str.strip().str.upper()
        df["exchange"] = df["exchange"].fillna("").astype(str)
        df = df[["cik", "ticker", "exchange"]].drop_duplicates(["cik", "ticker"]).sort_values(["cik", "ticker"])
        if len(df) < 3000:
            print(f"{ts}  SKIP  {len(df)} rows"); continue
        when = datetime.strptime(ts, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
        _, dg, status = snapshot("exchange", df, root=root, captured_at=when, source="wayback")
        print(f"{ts}  {len(df):>6} rows  {status} ({dg})")
        n += status == "new"
    return n
