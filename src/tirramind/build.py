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
from .diff import annotate, events_over_history, fill_exchange, permanent_removals
from .link import link
from .page import render_weekly
from .ledger import DEFAULT_ROOT as LEDGER_ROOT, read as read_ledger
from .reconcile import CAUSES, NOT_DELISTINGS, reconcile, summary
from .store import DEFAULT_ROOT as SNAP_ROOT, load_snapshot, snapshots_for

OUT = os.path.join(os.getcwd(), "data")


def build(*, snap_root: str = SNAP_ROOT, ledger_root: str = LEDGER_ROOT, out: str = OUT) -> dict:
    os.makedirs(out, exist_ok=True)
    snaps = snapshots_for("tickers", root=snap_root)
    if not snaps:
        raise RuntimeError("no ticker snapshots; run tickers.snapshot_current first")
    latest = load_snapshot(snap_root, snaps[-1]["path"])
    events = annotate(fill_exchange(events_over_history("tickers", root=snap_root), root=snap_root))
    filings = read_ledger("filings", root=ledger_root)
    if filings.empty:
        raise RuntimeError("filings ledger is empty; run filings.backfill first")
    delist = reconcile(permanent_removals(events), filings)

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
        # dense coverage = bulk-dataset rows; EFTS rows after that are sparse until the fill completes
        ds = f4[f4["source"].str.startswith("dataset")] if "source" in f4 else f4
        cov_ts = pd.to_datetime(ds["transaction_date"], format="%Y-%m-%d", errors="coerce").max()
        cov = cov_ts.strftime("%Y-%m-%d") if pd.notna(cov_ts) else None
        links = link(f144, f4, coverage_end=cov)
        acc = accuracy_table(links)
        links.to_parquet(os.path.join(out, "form144_links.parquet"), index=False)
        acc.to_parquet(os.path.join(out, "accuracy.parquet"), index=False)
        render_weekly(links, acc, f144, out=os.path.join(os.path.dirname(out), "docs"))
        mm = links["match_method"].value_counts(normalize=True).to_dict()
        insider = {"form144": int(len(f144)), "form4_rows": int(len(f4)), "form4_coverage_end": str(cov),
                   "window_complete": int(links["window_complete"].sum()),
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
        "suspect_steps": sorted(set(events.loc[events.suspect, "to_captured_at"].str[:10])),
        "raw_removals": int(events.event.eq("DELISTED_FROM_MAP").sum()),
        "superseded": delist.loc[delist.cause.isin(NOT_DELISTINGS), "cause"].value_counts().to_dict(),
        "true_delistings": int((~delist.cause.isin(NOT_DELISTINGS)).sum()),
        "cause_by_exchange_2022": pd.crosstab(delist[(delist.to_captured_at >= "2022") & ~delist.cause.isin(NOT_DELISTINGS)].exchange.replace("", "(blank)"),
                                              delist[(delist.to_captured_at >= "2022") & ~delist.cause.isin(NOT_DELISTINGS)].cause).to_dict(),
        "relisted_share": round(float((events.event.eq("DELISTED_FROM_MAP") & events.relisted_at.ne("")).sum()
                                      / max(1, events.event.eq("DELISTED_FROM_MAP").sum())), 4),
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
    bx = pd.DataFrame(s["cause_by_exchange_2022"]).fillna(0).astype(int)
    if len(bx):
        bx["total"] = bx.sum(axis=1)
        bx["known"] = (1 - bx.get("UNKNOWN", 0) / bx["total"]).map(lambda v: f"{v:.0%}")
        by_ex = "| exchange | " + " | ".join(bx.columns) + " |\n|---|" + "---|" * len(bx.columns) + "\n" + \
            "\n".join(f"| {i} | " + " | ".join(str(v) for v in r) + " |" for i, r in bx.iterrows())
    else:
        by_ex = "(no rows)"
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
| `delistings.parquet` | {s['delistings']} | permanent removals (not re-listed, not from a suspect capture) with a cause and evidence accessions |
| `filings.parquet` | {s['filings']} | Form 25 / 15 and item-filtered 8-K filings, 2015→ |

## Events ({s['snapshots']} snapshots, {s['first_snapshot'][:10]} → {s['latest_snapshot'][:10]})
| event | count |
|---|---|
{ev}

## What a "removal" is
`events.parquet` has {s['raw_removals']} raw `DELISTED_FROM_MAP` rows. **{s['relisted_share']:.0%} of
them re-appear later** (`relisted_at`) — the SEC file churns for housekeeping
reasons. Steps that removed ≥1,500 tickers at once are partial or
format-shifted captures and are flagged `suspect`: {', '.join(s['suspect_steps']) or 'none'}.
Of the removals that are neither re-listed nor suspect ({s['delistings']}),
those whose CIK gained a *different* ticker within ±60 days **and** have no
stronger filing evidence are two-step symbol changes or exchange transfers,
not delistings ({', '.join(f'{k} {v}' for k, v in s['superseded'].items()) or 'none'}).
They stay in `delistings.parquet` with that cause; the shares below are
over the remaining {s['true_delistings']} true delistings. The raw rows stay in `events.parquet`; nothing is deleted.

## Delisting causes
`UNKNOWN` means no qualifying filing was found on that CIK within
−180/+30 days of the ticker's disappearance. It is reported, not guessed.
A ticker can also leave the SEC map for housekeeping reasons that are not a
delisting; that share is inside `UNKNOWN`.

| cause | share |
|---|---|
{causes}

### By exchange, removals since 2022
{by_ex}

Known blind spots: foreign private issuers file 6-K/20-F, not 8-K, so a
going-private of an ADR shows as `EXCHANGE_DELISTING` (Form 25 only) or
`UNKNOWN`. Dormant OTC registrants that simply stop filing are `UNKNOWN`
until a last-filing-date check is added.

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
