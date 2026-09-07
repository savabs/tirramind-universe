# Data

Built 2026-09-07T05:05:58+00:00 by tirramind 0.1.0. Derived from SEC public
filings only (sec.gov: `company_tickers.json`, `company_tickers_exchange.json`,
EDGAR full-text search). Licence: CC-BY-4.0, attribution "derived from SEC
public filings". Nothing here is investment advice.

Snapshots before 2017-08-28's own capture come from the
Wayback Machine (roughly monthly); daily resolution starts 2026-09-06.

| file | rows | what |
|---|---|---|
| `tickers_latest.parquet` | 10415 | current (cik, ticker, name, exchange) |
| `events.parquet` | 103902 | every change between consecutive snapshots |
| `delistings.parquet` | 14284 | permanent removals (not re-listed, not from a suspect capture) with a cause and evidence accessions |
| `filings.parquet` | 78635 | Form 25 / 15 and item-filtered 8-K filings, 2015→ |

## Events (267 snapshots, 2017-08-28 → 2026-09-06)
| event | count |
|---|---|
| DELISTED_FROM_MAP | 43693 |
| LISTED | 47853 |
| NAME_CHANGED | 8963 |
| SYMBOL_CHANGED | 3393 |

## What a "removal" is
`events.parquet` has 43693 raw `DELISTED_FROM_MAP` rows. **50% of
them re-appear later** (`relisted_at`) — the SEC file churns for housekeeping
reasons. Steps that removed ≥1,500 tickers at once are partial or
format-shifted captures and are flagged `suspect`: 2020-06-05, 2021-08-09.
Of the removals that are neither re-listed nor suspect (14284),
those whose CIK gained a *different* ticker within ±60 days **and** have no
stronger filing evidence are two-step symbol changes or exchange transfers,
not delistings (SYMBOL_CHANGED 1413, EXCHANGE_TRANSFER 234).
They stay in `delistings.parquet` with that cause; the shares below are
over the remaining 12637 true delistings. The raw rows stay in `events.parquet`; nothing is deleted.

## Delisting causes
`UNKNOWN` means no qualifying filing was found on that CIK within
−180/+30 days of the ticker's disappearance. It is reported, not guessed.
A ticker can also leave the SEC map for housekeeping reasons that are not a
delisting; that share is inside `UNKNOWN`.

| cause | share |
|---|---|
| BANKRUPTCY | 3.3% |
| EXCHANGE_DELISTING | 25.8% |
| MERGER_ACQUISITION | 20.0% |
| VOLUNTARY_DELISTING | 0.6% |
| DEREGISTRATION | 2.0% |
| EXCHANGE_TRANSFER | 0.0% |
| SYMBOL_CHANGED | 0.0% |
| UNKNOWN | 48.3% |

### By exchange, removals since 2022
| exchange | BANKRUPTCY | DEREGISTRATION | EXCHANGE_DELISTING | MERGER_ACQUISITION | UNKNOWN | VOLUNTARY_DELISTING | total | known |
|---|---|---|---|---|---|---|---|---|
| (blank) | 62 | 26 | 117 | 30 | 1112 | 6 | 1353 | 18% |
| CBOE | 0 | 0 | 18 | 0 | 10 | 0 | 28 | 64% |
| NAS | 0 | 1 | 0 | 0 | 0 | 0 | 1 | 100% |
| NYSE | 33 | 4 | 1040 | 547 | 110 | 12 | 1746 | 94% |
| Nasdaq | 103 | 17 | 1401 | 1193 | 207 | 38 | 2959 | 93% |
| OTC | 152 | 159 | 253 | 110 | 2638 | 16 | 3328 | 21% |

Known blind spots: foreign private issuers file 6-K/20-F, not 8-K, so a
going-private of an ADR shows as `EXCHANGE_DELISTING` (Form 25 only) or
`UNKNOWN`. Dormant OTC registrants that simply stop filing are `UNKNOWN`
until a last-filing-date check is added.

## Filings collected
| form | count |
|---|---|
| 15-12B | 2016 |
| 15-12B/A | 32 |
| 15-12G | 3810 |
| 15-12G/A | 112 |
| 15-15D | 2011 |
| 15-15D/A | 34 |
| 25 | 1222 |
| 25-NSE | 10082 |
| 25-NSE/A | 143 |
| 25/A | 15 |
| 8-K | 56799 |
| 8-K/A | 2334 |
| CORRESP | 6 |
| EX-99.1 | 9 |
| EX-99.2 | 7 |
| EX-99.3 | 1 |
| EX-99.4 | 1 |
| EX-99.8 | 1 |

## Form 144 → Form 4 ledger
| | |
|---|---|
| Form 144 notices | 37651 |
| Form 4 transaction rows | 1144483 (sales: 345045) |
| linked notices | 37651 |
| match method | cik 83%, none 17%, name 0% |
| P(sale within 90d), all | 43.1% |

Files: `form144_links.parquet` (one row per notice), `accuracy.parquet`
(rates with cluster-bootstrap CIs and effective n). Weekly page: `docs/index.html`.
