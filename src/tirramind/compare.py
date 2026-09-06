"""The disagreement ledger: SEC ticker map vs NASDAQ's own directory.

For every ``nasdaq_dir`` snapshot, find the nearest SEC ``tickers`` snapshot
within 14 days and list the Nasdaq-listed common tickers each source has
that the other lacks. Neither source is the truth; the disagreement is the
finding, and every row is checkable.
"""

from __future__ import annotations

import pandas as pd

from .store import DEFAULT_ROOT, load_snapshot, snapshots_for

COLUMNS = ["nasdaq_captured_at", "sec_captured_at", "gap_days", "ticker", "name", "only_in"]


def disagreements(*, root: str = DEFAULT_ROOT, max_gap_days: int = 14) -> pd.DataFrame:
    nd = snapshots_for("nasdaq_dir", root=root)
    sec = snapshots_for("tickers", root=root)
    if not nd or not sec:
        return pd.DataFrame(columns=COLUMNS)
    sec_ts = pd.to_datetime([r["captured_at"] for r in sec], utc=True)
    out = []
    for r in nd:
        t = pd.to_datetime(r["captured_at"], utc=True)
        i = int((sec_ts - t).map(abs).argmin())
        gap = abs((sec_ts[i] - t).days)
        if gap > max_gap_days:
            continue
        n = load_snapshot(root, r["path"])
        n = n[n.exchange.eq("Nasdaq") & n.etf.ne("Y")] if "etf" in n else n[n.exchange.eq("Nasdaq")]
        s = load_snapshot(root, sec[i]["path"])
        s_nas = s[s.exchange.eq("Nasdaq")] if s.exchange.ne("").any() else s
        nset, sset = set(n.ticker), set(s_nas.ticker)
        for tk in sorted(nset - set(s.ticker)):
            out.append([r["captured_at"], sec[i]["captured_at"], gap, tk, n[n.ticker.eq(tk)].name.iloc[0], "nasdaq_directory"])
        if s.exchange.ne("").any():
            for tk in sorted(sset - nset):
                out.append([r["captured_at"], sec[i]["captured_at"], gap, tk, s_nas[s_nas.ticker.eq(tk)].name.iloc[0], "sec_map"])
    return pd.DataFrame(out, columns=COLUMNS)
