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
          "VOLUNTARY_DELISTING", "DEREGISTRATION", "EXCHANGE_TRANSFER", "SYMBOL_CHANGED",
          "SUCCESSION", "UNKNOWN"]
NOT_DELISTINGS = {"EXCHANGE_TRANSFER", "SYMBOL_CHANGED", "SUCCESSION"}   # the security lives on
WEAK = {"UNKNOWN", "VOLUNTARY_DELISTING"}                 # the only causes a sibling may override
FORM15 = {"15-12G", "15-12B", "15-15D"}
COLUMNS = ["cik", "ticker", "name", "exchange", "from_captured_at", "to_captured_at",
           "cause", "evidence_forms", "evidence_accessions", "n_filings_in_window",
           # Two different keys, so two columns. superseded_by holds a *ticker*
           # (the same issuer's new symbol); succeeded_by holds a *CIK* (the new
           # registrant behind the same ticker). Overloading one column with
           # both would make the type depend on the row.
           "superseded_by", "succeeded_by"]


def _items(s: str) -> set[str]:
    return set(x for x in str(s).split(",") if x)


def classify(window: pd.DataFrame) -> tuple[str, pd.DataFrame]:
    """Cause for one event given the filings in its window (may be empty).
    Returns (cause, evidence rows)."""
    if window.empty:
        return "UNKNOWN", window
    is_8k = window["form"].eq("8-K")
    items = window["items"].map(_items)
    # Item 1.03 on the *same* 8-K as 2.01 (acquisition completed) and 5.01
    # (change in control) is a going-private filing with a mis-ticked item,
    # not a bankruptcy (Vista Outdoor, 2024-11-27). Real bankruptcies pair
    # 1.03 with 2.04/7.01, never with a completed change of control.
    bankrupt = is_8k & items.map(lambda s: "1.03" in s and not ("2.01" in s and "5.01" in s))
    notice = is_8k & items.map(lambda s: "3.01" in s)
    acquired = is_8k & items.map(lambda s: "2.01" in s)
    f25_exchange = window["form"].eq("25-NSE") & (window["submitter_cik"] != window["subject_cik"])
    f25_issuer = window["form"].isin(["25", "25-NSE"]) & ~f25_exchange
    f15 = window["form"].isin(FORM15)

    if bankrupt.any():
        return "BANKRUPTCY", window[bankrupt | f25_exchange | f25_issuer | f15]
    # Item 2.01 also fires for the *acquirer*; only call it a merger when the
    # registrant also stopped being listed/registered (Form 15, exchange-filed
    # Form 25, or a 3.01 notice). An issuer-filed Form 25 alone is voluntary.
    if acquired.any() and (f15.any() or f25_exchange.any() or notice.any()):
        return "MERGER_ACQUISITION", window[acquired | f25_issuer | f25_exchange | f15 | notice]
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
    # Co-registrants (an LP and its parent REIT) file one 8-K under several
    # CIKs; match on every CIK the filing names, not only the first.
    fx = f.assign(match_cik=f["all_ciks"].fillna("").str.split(",")).explode("match_cik")
    fx = fx[fx.match_cik.ne("")]
    by_cik = {k: g for k, g in fx.groupby("match_cik")}

    out = []
    for r in ev.itertuples(index=False):
        g = by_cik.get(r.cik)
        if g is None:
            w = f.iloc[0:0]
        else:
            lo, hi = r.to_ts - pd.Timedelta(days=days_before), r.to_ts + pd.Timedelta(days=days_after)
            w = g[(g["filed_ts"] >= lo) & (g["filed_ts"] <= hi)]
        cause, evidence = classify(w)
        # A sibling ticker on the same CIK within +/-60 days overrides only a
        # weak cause: a bankruptcy whose stock moves to OTC as XXXQ, or a
        # de-SPAC whose units become common, keep their filing-based cause.
        kind = getattr(r, "superseded_kind", "") or ""
        # SUCCESSION overrides *any* filing-derived cause, and it is the only
        # override that does. The old registrant really did file Form 25 and
        # Form 15, so the filings genuinely read MERGER_ACQUISITION -- that is
        # what makes this class invisible to a filings-only method, and why 53
        # of these carried the one label a reader would most trust.
        if kind == "SUCCESSION":
            cause = "SUCCESSION"
        elif cause in WEAK and kind:
            cause = kind
        # A listing that reappears on another exchange with only an
        # issuer-filed Form 25 behind it is a transfer even if the 8-K also
        # ticked 3.01 (which covers transfers) or 2.01 (as acquirer).
        elif kind == "EXCHANGE_TRANSFER" and cause in ("MERGER_ACQUISITION", "EXCHANGE_DELISTING") \
                and not w["form"].isin(FORM15).any() \
                and not (w["form"].eq("25-NSE") & (w["submitter_cik"] != w["subject_cik"])).any():
            cause = "EXCHANGE_TRANSFER"
        out.append({
            "cik": r.cik, "ticker": r.ticker, "name": r.name, "exchange": r.exchange,
            "from_captured_at": r.from_captured_at, "to_captured_at": r.to_captured_at,
            "cause": cause,
            "evidence_forms": ",".join(sorted(set(evidence["form"]))) if len(evidence) else "",
            "evidence_accessions": ",".join(sorted(evidence["accession"])) if len(evidence) else "",
            "n_filings_in_window": int(len(w)),
            "superseded_by": getattr(r, "superseded_by", "") or "",
            "succeeded_by": getattr(r, "succeeded_by", "") or "",
        })
    return pd.DataFrame(out, columns=COLUMNS)


def summary(rec: pd.DataFrame) -> pd.Series:
    """Cause shares among true delistings (transfers and symbol changes are
    counted separately) — the UNKNOWN rate is published, never hidden."""
    d = rec[~rec["cause"].isin(NOT_DELISTINGS)]
    return d["cause"].value_counts(normalize=True).reindex(CAUSES).fillna(0.0)
