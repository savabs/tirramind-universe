"""B6: regenerate the published parquet outputs from snapshots and ledgers.

Everything here is derived. Delete ``data/*.parquet`` and rerun and you get
byte-identical files; the snapshots and ledgers are the record.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pandas as pd

from . import __version__
from .accuracy import accuracy_table
from .diff import events_over_history
from .link import link
from .page import render_weekly
from .ledger import DEFAULT_ROOT as LEDGER_ROOT, read as read_ledger
from .reconcile import CAUSES, reconcile, summary
from .store import DEFAULT_ROOT as SNAP_ROOT, load_snapshot, snapshots_for

OUT = os.path.join(os.getcwd(), "data")


def build(*, snap_root: str = SNAP_ROOT, ledger_root: str = LEDGER_ROOT, out: str = OUT) -> dict:
    os.makedirs(out, exist_ok=True)
    snaps = snapshots_for("tickers", root=snap_root)
    if not snaps:
        raise RuntimeError("no ticker snapshots; run tickers.snapshot_current first")
    latest = load_snapshot(snap_root, snaps[-1]["path"])
    events = events_over_history("tickers", root=snap_root)
    filings = read_ledger("filings", root=ledger_root)
    if filings.empty:
        raise RuntimeError("filings ledger is empty; run filings.backfill first")
    delist = reconcile(events, filings)

    latest.to_parquet(os.path.join(out, "tickers_latest.parquet"), index=False)
    events.to_parquet(os.path.join(out, "events.parquet"), index=False)
    delist.to_parquet(os.path.join(out, "delistings.parquet"), index=False)
    filings.drop(columns=[c for c in ("filed_ts",) if c in filings]).to_parquet(
        os.path.join(out, "filings.parquet"), index=False)

    # Insider ledger: optional until C2 has run at least once.
    f144 = read_ledger("form144", root=ledger_root)
    f4 = read_ledger("form4", root=ledger_root)
    insider = {}
    if not f144.empty and not f4.empty:
        links = link(f144.rename(columns={"accession": "accession"}), f4)
        acc = accuracy_table(links)
        links.to_parquet(os.path.join(out, "form144_links.parquet"), index=False)
        acc.to_parquet(os.path.join(out, "accuracy.parquet"), index=False)
        render_weekly(links, acc, f144, out=os.path.join(os.path.dirname(out), "docs"))
        mm = links["match_method"].value_counts(normalize=True).to_dict()
        insider = {"form144": int(len(f144)), "form4_rows": int(len(f4)),
                   "form4_sales": int((f4["code"] == "S").sum()),
                   "links": int(len(links)), "match_method_shares": {k: round(float(v), 4) for k, v in mm.items()},
                   "p_executed_90d_all": float(acc[(acc.segment == "all") & (acc.horizon_days == 90)]["p_executed"].iloc[0])}

    shares = summary(delist)
    stats = {
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "version": __version__,
        "snapshots": len(snaps),
        "first_snapshot": snaps[0]["captured_at"],
        "latest_snapshot": snaps[-1]["captured_at"],
        "tickers_latest": int(len(latest)),
        "events": int(len(events)),
        "events_by_type": events["event"].value_counts().to_dict(),
        "delistings": int(len(delist)),
        "cause_shares": {c: round(float(shares[c]), 4) for c in CAUSES},
        "filings": int(len(filings)),
        "filings_by_form": filings["form"].value_counts().to_dict(),
        "insider": insider,
    }
    _write_readme(out, stats)
    return stats


def _write_readme(out: str, s: dict) -> None:
    ev = "\n".join(f"| {k} | {v} |" for k, v in sorted(s["events_by_type"].items()))
    causes = "\n".join(f"| {k} | {v:.1%} |" for k, v in s["cause_shares"].items())
    forms = "\n".join(f"| {k} | {v} |" for k, v in sorted(s["filings_by_form"].items()))
    ins = s.get("insider") or {}
    insider = "" if not ins else f"""
## Form 144 → Form 4 ledger
| | |
|---|---|
| Form 144 notices | {ins['form144']} |
| Form 4 transaction rows | {ins['form4_rows']} (sales: {ins['form4_sales']}) |
| linked notices | {ins['links']} |
| match method | {', '.join(f'{k} {v:.0%}' for k, v in ins['match_method_shares'].items())} |
| P(sale within 90d), all | {ins['p_executed_90d_all']:.1%} |

Files: `form144_links.parquet` (one row per notice), `accuracy.parquet`
(rates with cluster-bootstrap CIs and effective n). Weekly page: `docs/index.html`.
"""
    text = f"""# Data

Built {s['built_at']} by tirramind {s['version']}. Derived from SEC public
filings only (sec.gov: `company_tickers.json`, `company_tickers_exchange.json`,
EDGAR full-text search). Licence: CC-BY-4.0, attribution "derived from SEC
public filings". Nothing here is investment advice.

Snapshots before {s['first_snapshot'][:10]}'s own capture come from the
Wayback Machine (roughly monthly); daily resolution starts 2026-09-06.

| file | rows | what |
|---|---|---|
| `tickers_latest.parquet` | {s['tickers_latest']} | current (cik, ticker, name, exchange) |
| `events.parquet` | {s['events']} | every change between consecutive snapshots |
| `delistings.parquet` | {s['delistings']} | DELISTED_FROM_MAP events with a cause and evidence accessions |
| `filings.parquet` | {s['filings']} | Form 25 / 15 and item-filtered 8-K filings, 2015→ |

## Events ({s['snapshots']} snapshots, {s['first_snapshot'][:10]} → {s['latest_snapshot'][:10]})
| event | count |
|---|---|
{ev}

## Delisting causes
`UNKNOWN` means no qualifying filing was found on that CIK within
−180/+30 days of the ticker's disappearance. It is reported, not guessed.
A ticker can also leave the SEC map for housekeeping reasons that are not a
delisting; that share is inside `UNKNOWN`.

| cause | share |
|---|---|
{causes}

## Filings collected
| form | count |
|---|---|
{forms}
{insider}"""
    with open(os.path.join(out, "README.md"), "w", encoding="utf-8") as fh:
        fh.write(text)


if __name__ == "__main__":
    import json
    print(json.dumps(build(), indent=1))
