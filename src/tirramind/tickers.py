"""B1: the daily ticker-map snapshot.

sec.gov publishes two current-state files: ``company_tickers.json``
(cik, ticker, title) and ``company_tickers_exchange.json`` (cik, name,
ticker, exchange). Both are overwritten in place. We merge them into one
canonical frame and snapshot it; the diff between snapshots is where
listings, delistings and symbol changes come from.
"""

from __future__ import annotations

import pandas as pd

from .sec import SecClient
from .store import DEFAULT_ROOT, snapshot

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
EXCHANGE_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
COLUMNS = ["cik", "ticker", "name", "exchange"]


def canonical_frame(tickers_json: dict, exchange_json: dict | None) -> pd.DataFrame:
    """Build the canonical (cik, ticker, name, exchange) frame.

    Accepts the raw JSON of both files. ``exchange_json`` may be None (the
    Wayback backfill has only the first file); exchange is then empty.
    """
    rows = [
        {"cik": f"{int(v['cik_str']):010d}", "ticker": str(v["ticker"]).strip().upper(),
         "name": str(v["title"]).strip()}
        for v in tickers_json.values()
    ]
    df = pd.DataFrame(rows, columns=["cik", "ticker", "name"])
    if exchange_json:
        fields = exchange_json["fields"]
        ex = pd.DataFrame(exchange_json["data"], columns=fields)
        ex = ex.rename(columns={"exchange": "exchange"})
        ex["cik"] = ex["cik"].map(lambda c: f"{int(c):010d}")
        ex["ticker"] = ex["ticker"].astype(str).str.strip().str.upper()
        ex["exchange"] = ex["exchange"].fillna("").astype(str)
        df = df.merge(ex[["cik", "ticker", "exchange"]], on=["cik", "ticker"], how="left")
    else:
        df["exchange"] = ""
    df["exchange"] = df["exchange"].fillna("")
    df = df.drop_duplicates(subset=["cik", "ticker"]).sort_values(["cik", "ticker"], kind="stable")
    return df[COLUMNS].reset_index(drop=True)


def fetch_current(client: SecClient) -> pd.DataFrame:
    return canonical_frame(client.get_json(TICKERS_URL), client.get_json(EXCHANGE_URL))


def snapshot_current(client: SecClient, *, root: str = DEFAULT_ROOT):
    df = fetch_current(client)
    if len(df) < 5000:
        raise RuntimeError(f"ticker map suspiciously small: {len(df)} rows")
    path, dg, status = snapshot("tickers", df, root=root)
    print(f"tickers {len(df):>6} rows  {status} ({dg})" + (f" -> {path}" if path else ""))
    return df, status
