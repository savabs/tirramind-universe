# Data

Built 2026-09-09T22:42:55+00:00 by tirramind 0.1.0. Derived from SEC public
filings only (sec.gov: `company_tickers.json`, `company_tickers_exchange.json`,
EDGAR full-text search). Licence: CC-BY-4.0, attribution "derived from SEC
public filings". Nothing here is investment advice.

Snapshots before 2017-08-28's own capture come from the
Wayback Machine (roughly monthly); daily resolution starts 2026-09-06.

| file | rows | what |
|---|---|---|
| `tickers_latest.parquet` | 10407 | current (cik, ticker, name, exchange) |
| `events.parquet` | 104013 | every change between consecutive snapshots |
| `delistings.parquet` | 14307 | permanent removals (not re-listed, not from a suspect capture) with a cause and evidence accessions |
| `filings.parquet` | 78675 | Form 25 / 15 and item-filtered 8-K filings, 2015→ |

## Events (269 snapshots, 2017-08-28 → 2026-09-09)
| event | count |
|---|---|
| DELISTED_FROM_MAP | 43741 |
| EXCHANGE_CHANGED | 1 |
| LISTED | 47893 |
| NAME_CHANGED | 8983 |
| SYMBOL_CHANGED | 3395 |

## What a "removal" is
`events.parquet` has 43741 raw `DELISTED_FROM_MAP` rows. **50% of
them re-appear later** (`relisted_at`) — the SEC file churns for housekeeping
reasons. Steps that removed ≥1,500 tickers at once are partial or
format-shifted captures and are flagged `suspect`: 2020-06-05, 2021-08-09.
Of the removals that are neither re-listed nor suspect (14307),
those whose CIK gained a *different* ticker within ±60 days **and** have no
stronger filing evidence are two-step symbol changes or exchange transfers,
not delistings (SYMBOL_CHANGED 1420, EXCHANGE_TRANSFER 236, SUCCESSION 190).
They stay in `delistings.parquet` with that cause; the shares below are
over the remaining 12461 true delistings. The raw rows stay in `events.parquet`; nothing is deleted.

## Delisting causes
`UNKNOWN` means no qualifying filing was found on that CIK within
−180/+30 days of the ticker's disappearance. It is reported, not guessed.
A ticker can also leave the SEC map for housekeeping reasons that are not a
delisting; that share is inside `UNKNOWN`.

| cause | share |
|---|---|
| BANKRUPTCY | 3.4% |
| EXCHANGE_DELISTING | 25.9% |
| MERGER_ACQUISITION | 19.9% |
| VOLUNTARY_DELISTING | 0.6% |
| DEREGISTRATION | 1.9% |
| EXCHANGE_TRANSFER | 0.0% |
| SYMBOL_CHANGED | 0.0% |
| SUCCESSION | 0.0% |
| UNKNOWN | 48.2% |

### By exchange, removals since 2022
| exchange | BANKRUPTCY | DEREGISTRATION | EXCHANGE_DELISTING | MERGER_ACQUISITION | UNKNOWN | VOLUNTARY_DELISTING | total | known |
|---|---|---|---|---|---|---|---|---|
| (blank) | 62 | 25 | 117 | 29 | 1107 | 6 | 1346 | 18% |
| CBOE | 0 | 0 | 18 | 0 | 10 | 0 | 28 | 64% |
| NAS | 0 | 1 | 0 | 0 | 0 | 0 | 1 | 100% |
| NYSE | 33 | 4 | 1029 | 536 | 108 | 12 | 1722 | 94% |
| Nasdaq | 103 | 8 | 1399 | 1180 | 206 | 38 | 2934 | 93% |
| OTC | 152 | 159 | 253 | 105 | 2635 | 16 | 3320 | 21% |

Known blind spots: foreign private issuers file 6-K/20-F, not 8-K, so a
going-private of an ADR shows as `EXCHANGE_DELISTING` (Form 25 only) or
`UNKNOWN`. Dormant OTC registrants that simply stop filing are `UNKNOWN`
until a last-filing-date check is added.

## Filings collected
| form | count |
|---|---|
| 15-12B | 2016 |
| 15-12B/A | 32 |
| 15-12G | 3817 |
| 15-12G/A | 112 |
| 15-15D | 2015 |
| 15-15D/A | 34 |
| 25 | 1225 |
| 25-NSE | 10090 |
| 25-NSE/A | 143 |
| 25/A | 15 |
| 8-K | 56817 |
| 8-K/A | 2334 |
| CORRESP | 6 |
| EX-99.1 | 9 |
| EX-99.2 | 7 |
| EX-99.3 | 1 |
| EX-99.4 | 1 |
| EX-99.8 | 1 |
