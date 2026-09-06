"""C3: link every Form 144 (intent to sell) to the Form 4 sales that executed it.

Rule 144 notices are good for three months, so the execution window is
[notice - 3d, notice + 90d]. Match first on (issuer_cik, owner_cik) — exact
and cheap — and fall back to a normalised name match, which is recorded in
``match_method`` so the accuracy table can be split by it. A 144 with no
matching sale is a real observation (``executed_fraction = 0``), not a
missing value.
"""

from __future__ import annotations

import re

import pandas as pd

WINDOW_BEFORE = 3
WINDOW_AFTER = 90
LINK_COLUMNS = [
    "accession_144", "issuer_cik", "owner_cik", "insider_name", "relationship", "notice_date",
    "shares_planned", "dollar_value_planned", "match_method", "n_sales", "shares_sold",
    "executed_fraction", "first_sale_date", "days_to_first_sale", "vwap_sold", "window_complete",
]
_SUFFIX = re.compile(r"\b(jr|sr|ii|iii|iv|mr|mrs|ms|dr)\b\.?")


def normalise_name(s: str) -> str:
    """'COOK TIMOTHY D' and 'Timothy D. Cook' -> same sorted-token key."""
    s = _SUFFIX.sub(" ", str(s).lower())
    toks = [t for t in re.split(r"[^a-z]+", s) if len(t) > 1]
    return " ".join(sorted(toks))


def link(f144: pd.DataFrame, f4: pd.DataFrame, *, coverage_end: str | None = None) -> pd.DataFrame:
    """``f144`` columns: accession, issuer_cik, owner_cik ('' if unknown),
    insider_name, relationship, notice_date, shares_to_sell, dollar_value.
    ``f4`` columns: issuer_cik, owner_cik, owner_name, transaction_date, code,
    shares, price. Only code 'S' rows are used."""
    sales = f4[f4["code"].eq("S") & (f4["shares"] > 0)].copy()
    sales["t"] = pd.to_datetime(sales["transaction_date"], errors="coerce")
    sales = sales.dropna(subset=["t"])
    # Form 4 coverage ends where dense data ends; a notice whose 90-day window
    # runs past that cannot be judged and must not count as "not executed".
    cov_end = pd.to_datetime(coverage_end) if coverage_end else sales["t"].max()
    sales["name_key"] = sales["owner_name"].map(normalise_name)
    by_cik = {k: g for k, g in sales.groupby(["issuer_cik", "owner_cik"])}
    by_name = {k: g for k, g in sales.groupby(["issuer_cik", "name_key"])}

    out = []
    for r in f144.itertuples(index=False):
        notice = pd.to_datetime(r.notice_date, errors="coerce")
        if pd.isna(notice):
            continue
        lo, hi = notice - pd.Timedelta(days=WINDOW_BEFORE), notice + pd.Timedelta(days=WINDOW_AFTER)
        method, cand = "none", None
        if r.owner_cik and (r.issuer_cik, r.owner_cik) in by_cik:
            method, cand = "cik", by_cik[(r.issuer_cik, r.owner_cik)]
        elif (r.issuer_cik, normalise_name(r.insider_name)) in by_name:
            method, cand = "name", by_name[(r.issuer_cik, normalise_name(r.insider_name))]
        w = cand[(cand["t"] >= lo) & (cand["t"] <= hi)] if cand is not None else sales.iloc[0:0]
        if w.empty:
            method = "none" if cand is None else method
        sold = float(w["shares"].sum())
        planned = float(r.shares_to_sell) if r.shares_to_sell else 0.0
        first = w["t"].min() if len(w) else pd.NaT
        out.append({
            "accession_144": r.accession, "issuer_cik": r.issuer_cik, "owner_cik": r.owner_cik,
            "insider_name": r.insider_name, "relationship": r.relationship,
            "notice_date": notice.strftime("%Y-%m-%d"),
            "shares_planned": planned, "dollar_value_planned": float(r.dollar_value or 0.0),
            "match_method": method, "n_sales": int(len(w)), "shares_sold": sold,
            "executed_fraction": (min(sold / planned, 5.0) if planned > 0 else float("nan")),
            "first_sale_date": first.strftime("%Y-%m-%d") if not pd.isna(first) else "",
            "days_to_first_sale": int((first - notice).days) if not pd.isna(first) else -1,
            "vwap_sold": float((w["shares"] * w["price"]).sum() / sold) if sold > 0 else float("nan"),
            "window_complete": bool(hi <= cov_end),
        })
    return pd.DataFrame(out, columns=LINK_COLUMNS)
