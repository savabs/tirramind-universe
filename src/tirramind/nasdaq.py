"""NASDAQ Trader symbol directories: an independent, exchange-published
listing source. ``nasdaqlisted.txt`` (Nasdaq-listed) and ``otherlisted.txt``
(NYSE/Arca/BATS/etc.) are overwritten daily; Wayback holds ~80 captures back
to 2008. Snapshotting them daily from day 0 makes us the sensor.

The files are pipe-delimited with a trailing "File Creation Time" footer.
"""

from __future__ import annotations

import io
from datetime import datetime, timezone

import pandas as pd
import requests

from .store import DEFAULT_ROOT, snapshot

NASDAQ_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"
UA = "tirramind (github.com/savabs/tirramind-universe)"
_EXCH = {"A": "NYSE MKT", "N": "NYSE", "P": "NYSE ARCA", "Z": "BATS", "V": "IEX"}


def parse_directory(text: str, *, kind: str) -> pd.DataFrame:
    lines = [ln for ln in text.splitlines() if ln and not ln.startswith("File Creation Time")]
    df = pd.read_csv(io.StringIO("\n".join(lines)), sep="|", dtype=str, keep_default_na=False)
    if kind == "nasdaq":
        out = pd.DataFrame({"ticker": df["Symbol"].str.strip().str.upper(), "name": df["Security Name"].str.strip(),
                            "exchange": "Nasdaq", "test_issue": df.get("Test Issue", "N"), "etf": df.get("ETF", "")})
    else:
        sym = df["ACT Symbol"] if "ACT Symbol" in df else df.iloc[:, 0]
        out = pd.DataFrame({"ticker": sym.str.strip().str.upper(), "name": df["Security Name"].str.strip(),
                            "exchange": df["Exchange"].map(_EXCH).fillna(df["Exchange"]),
                            "test_issue": df.get("Test Issue", "N"), "etf": df.get("ETF", "")})
    out = out[out.test_issue.ne("Y")].drop(columns=["test_issue"])
    return out.drop_duplicates("ticker").sort_values("ticker").reset_index(drop=True)


def fetch_current(session: requests.Session | None = None) -> pd.DataFrame:
    s = session or requests.Session()
    s.headers.setdefault("User-Agent", UA)
    a = parse_directory(s.get(NASDAQ_URL, timeout=60).text, kind="nasdaq")
    b = parse_directory(s.get(OTHER_URL, timeout=60).text, kind="other")
    return pd.concat([a, b], ignore_index=True).drop_duplicates("ticker").sort_values("ticker").reset_index(drop=True)


def snapshot_current(*, root: str = DEFAULT_ROOT):
    df = fetch_current()
    if len(df) < 5000:
        raise RuntimeError(f"nasdaq directory suspiciously small: {len(df)}")
    path, dg, status = snapshot("nasdaq_dir", df, root=root)
    print(f"nasdaq_dir {len(df):>6} rows  {status} ({dg})")
    return df, status


def backfill_wayback(*, root: str = DEFAULT_ROOT) -> int:
    """Each Wayback capture of nasdaqlisted.txt becomes a ``nasdaq_dir``
    snapshot (Nasdaq-listed only; otherlisted captures are too sparse to
    pair reliably)."""
    from .wayback import fetch_capture, list_captures
    s = requests.Session(); s.headers["User-Agent"] = UA
    n = 0
    for ts in list_captures(NASDAQ_URL, session=s):
        try:
            r = s.get(f"https://web.archive.org/web/{ts}id_/{NASDAQ_URL}", timeout=120); r.raise_for_status()
            df = parse_directory(r.text, kind="nasdaq")
        except Exception as e:  # noqa: BLE001
            print(f"{ts}  FAIL  {type(e).__name__}: {str(e)[:80]}"); continue
        if len(df) < 2000:
            print(f"{ts}  SKIP  {len(df)} rows"); continue
        when = datetime.strptime(ts, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
        _, dg, status = snapshot("nasdaq_dir", df, root=root, captured_at=when, source="wayback")
        print(f"{ts}  {len(df):>6} rows  {status} ({dg})"); n += status == "new"
    return n
