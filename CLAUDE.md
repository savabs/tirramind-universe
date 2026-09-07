# tirramind — working notes for agents

A survivorship-bias-free ledger of every US listed security, with the **cause**
of each delisting and the SEC filing that proves it, reconciled daily from SEC
public filings only. Plus a Form 144 → Form 4 insider ledger.

Read this before changing anything. Most of what follows is not derivable from
the code, and several rules exist because breaking them already cost real work.

---

## What this repo is for

As of September 2026 this is **the product**, not a side project: point-in-time
US securities reference data with filing-level provenance, sold as an API and
bulk snapshots. The thesis in one line:

> Everyone sells *that* a company delisted. Almost nobody sells *why*, and
> nobody under $500/month sells the filing that proves it.

The competitive position is narrow and specific. CRSP does this properly and is
enterprise-priced under Morningstar. Norgate ($630/yr) and Sharadar give you
delisted tickers with no cause and no audit trail. The gap is **cheap and
auditable**, and it is the only gap here — do not let the pitch drift to
"survivorship-bias-free data", which four vendors already sell.

### The rule that makes this buildable

**Never add price data.** Prices drag in exchange licensing (CTA/UTP/OPRA),
which runs from $32 to $20,000+ per exchange per month plus per-user reporting
and audits. Corporate actions, delistings, identifiers and share counts come
from SEC filings, which are US Government works and uncopyrightable under
17 U.S.C. §105 — free to build on, sell, and redistribute.

That asymmetry is the whole business. A licensed vendor cannot easily undercut
someone who never took the licence. Adding a price column would end it.

### Licensing, and why it constrains the product

Code Apache-2.0. **Data CC-BY-4.0** — anyone may redistribute the published
corpus commercially with attribution. So the sellable asset is not the archive;
it is the **live daily reconciliation and the API**. Keep publishing history
free (it is the credibility and the marketing), sell the pipe. Do not
retroactively relicense anything already released.

### The clock that cannot be restarted

`company_tickers.json` is **overwritten in place** by the SEC. No history, no
archive. Wayback caught it roughly monthly until 2026-09-06; this repo catches
it daily since. **A missed day is a day of diff resolution nobody can ever
recover.** If the daily job is broken, fixing it is the highest priority task in
the repo — higher than any feature.

---

## Architecture

Staged, and the docstrings carry the stage letters:

```
B1  tickers.py    daily snapshot of company_tickers{,_exchange}.json
B2  diff.py       events between consecutive snapshots (derived, never stored)
B3  wayback.py    backfill 2017 → day 0 from the Wayback Machine
B4  filings.py    Form 25 / 15 / item-filtered 8-K from EDGAR full-text search
B5  reconcile.py  assign a cause to every DELISTED_FROM_MAP event
B6  build.py      regenerate every published parquet from snapshots + ledgers

C1  forms.py      Form 4 / 144 XML parsers
C2  insiders.py   Form 144 + Form 4 collection
C3  link.py       144 (intent) → 4 (execution), 90-day window
C4  accuracy.py   the accuracy table, with issuer-week cluster bootstrap CIs
C5  page.py       static weekly HTML, every row linked to sec.gov

D1  daily.py      the job; prints row counts so the log is evidence
D2  client.py     read the published ledger without cloning

    store.py      append-only content-addressed snapshots
    ledger.py     append-only JSONL, re-appending a key is a no-op
    sec.py        rate-limited sec.gov client
    verify.py     THE GATE
    nasdaq.py     independent exchange-published listing source
    compare.py    SEC map vs NASDAQ directory disagreements
```

**Everything below `build.py` is derived.** Delete `data/*.parquet`, rerun, and
you get byte-identical output. That is deliberate: a bug in `diff.py` or
`reconcile.py` is fixed by editing the file and rebuilding, never by patching
data. Never hand-edit a parquet.

---

## Invariants — do not break these

1. **`UNKNOWN` is a real answer.** Never guess a cause to raise the known-cause
   rate. The published UNKNOWN share (currently 48% overall, 21% on OTC) is a
   feature: it is why the other 52% is believable.
2. **Every row links to its evidence.** `evidence_accessions` must let a reader
   check the row by hand on sec.gov. A cause with no accession behind it is a
   bug unless the cause is `UNKNOWN`.
3. **Nothing is deleted.** Suspect captures (2020-06-05, 2021-08-09 — partial
   files that dropped thousands of tickers) are *flagged*, not removed. Raw
   removals stay in `events.parquet` even when reclassified.
4. **Append-only storage.** `store.py` and `ledger.py` never edit a row. Daily
   runs overlap by design; re-appending an existing key is a no-op.
5. **`verify.py` is the gate, not exit codes.** A run that captured nothing on a
   business day fails red. Green-with-zero-rows has bitten this owner four
   separate times. Never weaken this check to make CI pass.
6. **SEC fair access.** At most 10 requests/second, and every request must carry
   a User-Agent naming a real contact (`TIRRAMIND_CONTACT`). `sec.py` enforces
   it; do not bypass it.

---

## The cause taxonomy

Assigned in `reconcile.py` from filings on the same CIK in a −180/+30 day
window, including co-registrants (an LP's 8-K is filed under its parent).

| cause | meaning |
|---|---|
| `BANKRUPTCY` | 8-K Item 1.03 |
| `EXCHANGE_DELISTING` | exchange-initiated, Form 25-NSE filed by the exchange |
| `MERGER_ACQUISITION` | acquired or taken private |
| `VOLUNTARY_DELISTING` | issuer-filed Form 25 |
| `DEREGISTRATION` | Form 15, registration withdrawn |
| `EXCHANGE_TRANSFER` | **not a delisting** — moved venue (CSWI Nasdaq → CSW NYSE) |
| `SYMBOL_CHANGED` | **not a delisting** — two-step ticker change (DIGP → FUNI) |
| `SUCCESSION` | **not a delisting** — new registrant, same business |
| `UNKNOWN` | no qualifying filing found |

`NOT_DELISTINGS` in `reconcile.py` holds the three that are not delistings.
True-delisting counts and cause shares are computed over the remainder
(currently 12,452 of 14,288 resolved removals).

### Two override mechanisms, easily confused

They are mirror images and they use **different keys**:

- `superseded_by` holds a **ticker** — the same CIK gained a *different* symbol
  within ±60 days. A symbol change or an exchange transfer.
- `succeeded_by` holds a **CIK** — the same ticker gained a *different*
  registrant within ±120 days, with the business name carrying over. A holding
  company interposed (Xerox Corporation → Xerox Holdings Corp) or a redomicile
  (Marvell Technology Group Ltd, Bermuda → Marvell Technology, Inc., Delaware).

Keep them in separate columns. They were briefly folded into one, which made the
column hold a ticker on some rows and a CIK on others — the type depending on
the row, which is exactly the defect class `pipelie` exists to catch.

**`SUCCESSION` is the only cause that overrides a filing-derived cause**, and it
must. The old registrant really does file Form 25 and Form 15, so a filings-only
method reads a merger. Of the 190 rows reclassified when this was added, **55
had carried `MERGER_ACQUISITION`** — the label a reader would most trust — plus
82 `UNKNOWN`, 35 `EXCHANGE_DELISTING`, 13 `DEREGISTRATION`, 4 `SYMBOL_CHANGED`
and one `BANKRUPTCY`. Disney, Xerox, Cigna, Dow, Johnson Controls and Marvell
were all in that bucket. Nobody was bought out; the security never stopped
trading.

The name-overlap requirement is load-bearing. Without it, ticker recycling gets
swallowed: American Greetings genuinely died and Antero Midstream picked up `AM`
years later. That one **is** a delisting.

---

## Known blind spots — documented, not hidden

- **Foreign private issuers** file 6-K/20-F rather than 8-K, so an ADR
  going private shows as `EXCHANGE_DELISTING` or `UNKNOWN`. Found by hand-check
  (OneConnect / Ping An); scored 29/30 on 30 random 2024+ removals.
- **OTC dormancy.** Most OTC names leave the map because the registrant simply
  stopped filing. There is no Form 25 for going dormant, so OTC known-cause is
  21% against 93–94% on the national exchanges. A last-filing-date check would
  turn most of these into a `DORMANT` label with its own evidence. Not built.
- **Bank holding companies.** NASDAQ lists banks (First Bank, Hingham, Northeast
  Bank, Towne Bank) the SEC map has never contained, because they register with
  their banking regulator. Any universe built from the SEC file alone is missing
  them — see `compare.py` and `data/disagreements_nasdaq.parquet`.
- **SEC file lags the exchange** by weeks. Currently 55 tickers the SEC still
  calls Nasdaq-listed that Nasdaq no longer carries.

---

## Commands

```bash
.venv/bin/python -m pytest -q              # 42 tests, all must pass
.venv/bin/python -m tirramind.build        # regenerate every parquet from source
.venv/bin/python -m tirramind.daily        # the full daily job
.venv/bin/python -m tirramind.verify       # the gate; exits non-zero on a bad run
```

The daily GitHub Action runs at 22:40 UTC on weekdays (after EDGAR closes at
17:30 ET), commits new snapshots, and runs `verify` as its final step.

---

## Gotchas learned the hard way

- **`df[[]]` selects zero *columns*, not zero rows.** A boolean mask built as a
  bare list breaks when the match set is empty. Use a `pd.Series` with an index.
- **Cause counts move when `diff.py` changes**, because causes are derived. Any
  PR touching classification must state the before/after true-delisting count.
  It went 12,637 → 12,452 when `SUCCESSION` was added.
- **`WRITEUP.md` hardcodes numbers.** It is a draft narrative, not generated.
  After a classification change, its figures are stale until updated by hand.
- **Half of all raw removals reappear.** 43,706 `DELISTED_FROM_MAP` events
  resolve to 14,288 permanent removals. Anything reasoning over raw events
  rather than `delistings.parquet` is almost certainly wrong.

---

## Sibling repos

- `../voltorch` — differentiable option pricing, live arbitrage-free Deribit
  surfaces refit every 30 min. **Second product**, same shape of moat: a
  point-in-time archive nobody can backfill. Its archive started 2026-09-07.
- `../pipelie` — the data-quality library (on PyPI). Its checks map to bugs that
  actually shipped in these repos. Worth running over any new output table.
- `../queue_attrition` — interconnection queue attrition; the snapshot/diff
  pattern in `store.py` was ported from it.
