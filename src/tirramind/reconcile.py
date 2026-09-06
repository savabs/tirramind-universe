"""B5: assign a cause to every DELISTED_FROM_MAP event from the filings ledger.

A ticker leaving ``company_tickers.json`` is evidence of *something*, not
proof of a delisting: the SEC also drops tickers for housekeeping reasons.
So every event is matched to filings on the same CIK inside a window and
assigned one cause from a fixed taxonomy. ``UNKNOWN`` is a real outcome
that gets reported, never papered over. Every contributing accession is
recorded so any row can be checked against sec.gov by hand.
"""

from __future__ import annotations

import pandas as pd

CAUSES = ["BANKRUPTCY", "EXCHANGE_DELISTING", "MERGER_ACQUISITION",
          "VOLUNTARY_DELISTING", "DEREGISTRATION", "UNKNOWN"]
FORM15 = {"15-12G", "15-12B", "15-15D"}
COLUMNS = ["cik", "ticker", "name", "exchange", "from_captured_at", "to_captured_at",
           "cause", "evidence_forms", "evidence_accessions", "n_filings_in_window"]


def _items(s: str) -> set[str]:
    return set(x for x in str(s).split(",") if x)


def classify(window: pd.DataFrame) -> tuple[str, pd.DataFrame]:
    """Cause for one event given the filings in its window (may be empty).
    Returns (cause, evidence rows)."""
    if window.empty:
        return "UNKNOWN", window
    is_8k = window["form"].eq("8-K")
    items = window["items"].map(_items)
    bankrupt = is_8k & items.map(lambda s: "1.03" in s)
    notice = is_8k & items.map(lambda s: "3.01" in s)
    acquired = is_8k & items.map(lambda s: "2.01" in s)
    f25_exchange = window["form"].eq("25-NSE") & (window["submitter_cik"] != window["subject_cik"])
    f25_issuer = window["form"].isin(["25", "25-NSE"]) & ~f25_exchange
    f15 = window["form"].isin(FORM15)

    if bankrupt.any():
        return "BANKRUPTCY", window[bankrupt | f25_exchange | f25_issuer | f15]
    if acquired.any() and (f25_issuer.any() or f25_exchange.any() or f15.any()):
        return "MERGER_ACQUISITION", window[acquired | f25_issuer | f25_exchange | f15]
    if notice.any() or f25_exchange.any():
        return "EXCHANGE_DELISTING", window[notice | f25_exchange | f15]
    if f25_issuer.any():
        return "VOLUNTARY_DELISTING", window[f25_issuer | f15]
    if f15.any():
        return "DEREGISTRATION", window[f15]
    return "UNKNOWN", window.iloc[0:0]


def reconcile(events: pd.DataFrame, filings: pd.DataFrame, *,
              days_before: int = 180, days_after: int = 30) -> pd.DataFrame:
    """Join DELISTED_FROM_MAP events to filings on subject_cik within
    [to_captured_at - days_before, to_captured_at + days_after]."""
    ev = events[events["event"].eq("DELISTED_FROM_MAP")].copy()
    if ev.empty:
        return pd.DataFrame(columns=COLUMNS)
    ev["to_ts"] = pd.to_datetime(ev["to_captured_at"], utc=True).dt.tz_localize(None).dt.normalize()
    f = filings.copy()
    f["filed_ts"] = pd.to_datetime(f["filed_at"])
    by_cik = {k: g for k, g in f.groupby("subject_cik")}

    out = []
    for r in ev.itertuples(index=False):
        g = by_cik.get(r.cik)
        if g is None:
            w = f.iloc[0:0]
        else:
            lo, hi = r.to_ts - pd.Timedelta(days=days_before), r.to_ts + pd.Timedelta(days=days_after)
            w = g[(g["filed_ts"] >= lo) & (g["filed_ts"] <= hi)]
        cause, evidence = classify(w)
        out.append({
            "cik": r.cik, "ticker": r.ticker, "name": r.name, "exchange": r.exchange,
            "from_captured_at": r.from_captured_at, "to_captured_at": r.to_captured_at,
            "cause": cause,
            "evidence_forms": ",".join(sorted(set(evidence["form"]))) if len(evidence) else "",
            "evidence_accessions": ",".join(sorted(evidence["accession"])) if len(evidence) else "",
            "n_filings_in_window": int(len(w)),
        })
    return pd.DataFrame(out, columns=COLUMNS)


def summary(rec: pd.DataFrame) -> pd.Series:
    """Cause shares — the UNKNOWN rate is printed and published, never hidden."""
    return rec["cause"].value_counts(normalize=True).reindex(CAUSES).fillna(0.0)
