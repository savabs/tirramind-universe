"""C5: the weekly page. Static HTML from parquet, no frameworks, every row
linked to its filing on sec.gov so a reader can check it by hand."""

from __future__ import annotations

import html
import os
from datetime import datetime, timedelta, timezone

import pandas as pd

OUT = os.path.join(os.getcwd(), "docs")
CSS = """body{font:15px/1.5 -apple-system,system-ui,sans-serif;max-width:1100px;margin:0 auto;padding:24px 16px;color:#111}
table{border-collapse:collapse;width:100%;font-size:13px;margin:8px 0 24px}th,td{border-bottom:1px solid #ddd;padding:4px 6px;text-align:left;vertical-align:top}
th{background:#f4f4f4}td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}.muted{color:#666}code{background:#f4f4f4;padding:1px 4px}"""


def _acc_url(cik: str, accession: str) -> str:
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/"


def _table(df: pd.DataFrame, cols: list[tuple[str, str, bool]], link_col: str | None = None) -> str:
    head = "".join(f'<th class="{"num" if num else ""}">{html.escape(h)}</th>' for _, h, num in cols)
    rows = []
    for r in df.itertuples(index=False):
        cells = []
        for key, _, num in cols:
            v = getattr(r, key)
            s = f"{v:,.0f}" if isinstance(v, float) and num and abs(v) >= 100 else (f"{v:.2f}" if isinstance(v, float) else str(v))
            s = html.escape(s)
            if key == link_col:
                s = f'<a href="{_acc_url(r.issuer_cik, v)}">{s}</a>'
            cells.append(f'<td class="{"num" if num else ""}">{s}</td>')
        rows.append("<tr>" + "".join(cells) + "</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table>"


def render_weekly(links: pd.DataFrame, acc: pd.DataFrame, f144: pd.DataFrame, *, out: str = OUT,
                  now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    week_ago = (now - timedelta(days=7)).strftime("%Y-%m-%d")
    filed = f144[f144["notice_date"] >= week_ago].sort_values("dollar_value", ascending=False)
    executed = links[(links["first_sale_date"] >= week_ago)].sort_values("shares_sold", ascending=False)

    parts = [f"<style>{CSS}</style><title>tirramind — insider sale notices this week</title>",
             f"<h1>Form 144 → Form 4 ledger</h1><p class='muted'>Generated {now:%Y-%m-%d %H:%M} UTC from SEC public filings. "
             f"Every row links to the filing. Code and data: <a href='https://github.com/savabs/tirramind-universe'>github.com/savabs/tirramind-universe</a>.</p>",
             f"<h2>Planned insider sales filed since {week_ago} ({len(filed)})</h2>",
             _table(filed.head(200), [("accession", "Form 144", False), ("issuer_name", "Issuer", False),
                                      ("insider_name", "Insider", False), ("relationship", "Role", False),
                                      ("notice_date", "Notice", False), ("shares_to_sell", "Shares", True),
                                      ("dollar_value", "USD", True)], link_col="accession"),
             f"<h2>Prior notices that executed since {week_ago} ({len(executed)})</h2>",
             _table(executed.head(200), [("accession_144", "Form 144", False), ("insider_name", "Insider", False),
                                         ("notice_date", "Notice", False), ("first_sale_date", "First sale", False),
                                         ("days_to_first_sale", "Days", True), ("shares_planned", "Planned", True),
                                         ("shares_sold", "Sold", True), ("executed_fraction", "Fraction", True),
                                         ("match_method", "Match", False)], link_col="accession_144"),
             "<h2>How often does a notice become a sale?</h2>",
             "<p class='muted'>P(any Form 4 sale within horizon). CI = 90% cluster bootstrap over issuer-weeks. "
             "n_eff = design-effect effective sample size; it is smaller than n because notices cluster.</p>",
             _table(acc, [("segment", "Segment", False), ("horizon_days", "Horizon", True), ("p_executed", "P(executed)", True),
                          ("ci_lo", "CI lo", True), ("ci_hi", "CI hi", True), ("n", "n", True),
                          ("n_clusters", "issuer-weeks", True), ("n_eff", "n_eff", True),
                          ("median_executed_fraction", "median fraction", True)]),
             "<p class='muted'>Match: <code>cik</code> exact owner CIK; <code>name</code> normalised-name fallback; "
             "<code>none</code> no Form 4 sale found in [−3, +90] days — counted as not executed, not as missing.</p>"]
    doc = "\n".join(parts)
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(doc)
    return doc
