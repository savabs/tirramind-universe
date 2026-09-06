# Every US delisting since 2017, reconciled from SEC filings — and where the lists disagree

*Draft, 2026-09-06. Numbers regenerate from `data/` with `python -m tirramind.build`; the insider-ledger section is filled in once Form 144 collection completes.*

## The claim

If you backtest on the companies that exist today, you have already thrown
out every one that died. Vendors sell "delisted" lists to fix that, at
$20–630 a year, and they disagree with each other, and none of them tells
you *why* a company left. The SEC publishes every one of these events as a
filing, for free, forever. This repo reads them every day and keeps a
ledger where every row links to the filing that proves it.

## What is in the ledger

267 daily-or-better snapshots of the SEC's ticker map from 2017-08-28 to
today (Wayback Machine until day 0, our own resolver since 2026-09-06),
26 snapshots of the SEC's exchange file, 79 snapshots of NASDAQ's own
symbol directory back to 2008, and 78,000 delisting-related filings since
2015: every Form 25 and Form 15, and every 8-K carrying Item 1.03
(bankruptcy), 2.01 (acquisition completed), 3.01 (delisting notice) or
5.03 (charter amendment).

## What the SEC ticker file actually is

This is the part the vendors do not tell you. `company_tickers.json` is
overwritten in place and churns for reasons that have nothing to do with
the market:

- **Half of all "removals" come back.** 43,693 tickers left the file
  between 2017 and today; 50% re-appeared later. Each removal carries
  `relisted_at` so you can see it.
- **Two captures were partial files.** 2020-06-05 and 2021-08-09 each
  dropped thousands of tickers that returned a week later. They are flagged
  `suspect` and excluded; nothing is deleted.
- **In September 2019 the file doubled** (6,255 → 13,633 rows) and every
  name was re-cased. 4,220 of 8,963 "name changes" are cosmetic and flagged.
- **A ticker that leaves and a new one that arrives on the same CIK within
  60 days is a symbol change or an exchange transfer, not a delisting.**
  1,413 and 234 of them respectively. CSW Industrials did not get acquired
  in June 2025; it moved from Nasdaq to NYSE as CSW, and its 8-K carried
  Item 2.01 because *it* had acquired something.

After all of that, **12,637 true delistings** remain, 9,415 of them since
2022.

## Why each one happened

Every true delisting is matched to filings on the same CIK — including
co-registrants, because an LP's 8-K is filed under its parent — within
−180/+30 days, and given one cause. `UNKNOWN` is reported, never guessed.

| exchange (2022→) | bankruptcy | exchange-initiated | merger / going private | voluntary | deregistration | unknown | **known** |
|---|---|---|---|---|---|---|---|
| NYSE | 34 | 1,040 | 546 | 12 | 4 | 110 | **94%** |
| Nasdaq | 103 | 1,401 | 1,193 | 38 | 17 | 207 | **93%** |
| OTC | 154 | 253 | 108 | 16 | 159 | 2,638 | 21% |

On the two national exchanges, 93–94% of delistings have a filing-backed
cause. On OTC the figure is 21%, and that is honest: most OTC names leave
the SEC map because the registrant simply stopped filing. There is no Form
25 for going dormant. A last-filing-date check is the next step and will
turn most of those into a `DORMANT` label with its own evidence.

A hand check of 30 random 2024+ removals against EDGAR
(`data/samples/handcheck_30.csv`, every row with its URL) scored 29/30.
The miss is OneConnect, a foreign private issuer taken private by Ping An:
foreign issuers file 6-K/20-F rather than 8-K, so their going-privates
show as plain exchange delistings. That blind spot is documented in the
data README rather than papered over.

Known bankruptcies on NYSE/Nasdaq by year, each with its Item 1.03 filing:
2022: 18 · 2023: 62 · 2024: 41 · 2025: 12 · 2026 (to Sep): 3.

## Where the lists disagree

The SEC map and NASDAQ's own symbol directory were compared at 30 matched
dates (`data/disagreements_nasdaq.parquet`). Today the SEC still labels
**55 tickers as Nasdaq-listed that Nasdaq no longer carries**; 31 of them
have a delisting filing since June — the SEC file lags the exchange by
weeks. In the other direction, Nasdaq lists seven banks (First Bank,
Hingham Institution for Savings, Northeast Bank, Towne Bank, …) that the
SEC map has never contained, because they register with their banking
regulator, not the SEC. Any "survivorship-bias-free" universe built from
the SEC file alone is missing them.

## The insider ledger

*(filled in when Form 144 collection completes)* — Form 144 notices of
intent to sell, linked to the Form 4 sales that executed them, with
execution rates by horizon, cluster-bootstrap intervals and effective
sample sizes. The SEC's free insider datasets cover Forms 3/4/5 only;
nobody publishes this linkage.

## Use it

```
pip install tirramind
import tirramind
tirramind.delistings(since="2024-01-01", cause="BANKRUPTCY")
tirramind.events(event="SYMBOL_CHANGED")
```

Parquet files are in `data/`; the daily job commits new snapshots at
22:40 UTC; the weekly insider page is at savabs.github.io/tirramind-universe.
Code Apache-2.0, data CC-BY-4.0. If a row is wrong, the filing it links to
will show it — open an issue with the accession number.
