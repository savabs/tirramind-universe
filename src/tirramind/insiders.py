"""C2: Form 144 and Form 4 collection.

Form 4 history comes from the SEC's bulk quarterly *Insider Transactions
Data Sets* (one zip per quarter, every Form 3/4/5 transaction as TSV) —
1.4M per-filing XML fetches would take 39 hours; the zips take minutes.
The current quarter, which the dataset does not yet cover, is filled by
EFTS + per-filing XML through ``parse_form4``.

Form 144 has no bulk dataset (the SEC's free sets cover 3/4/5 only). Each
notice is one EFTS hit plus one XML fetch. That gap is the product.
"""

from __future__ import annotations

import io
import zipfile
from datetime import date, datetime

import pandas as pd

from .filings import EFTS, PAGE, search
from .forms import parse_form4, parse_form144
from .ledger import DEFAULT_ROOT as LEDGER_ROOT, append, keys
from .sec import SecClient

ARCHIVES = "https://www.sec.gov/Archives/edgar/data"
DATASET = "https://www.sec.gov/files/structureddata/data/insider-transactions-data-sets/{y}q{q}_form345.zip"
F4_COLUMNS = ["accession", "filing_date", "issuer_cik", "issuer_ticker", "issuer_name", "owner_cik",
              "owner_name", "owner_relationship", "transaction_date", "code", "acquired_disposed",
              "shares", "price", "shares_after", "source"]
F144_COLUMNS = ["accession", "filed_at", "issuer_cik", "owner_cik", "issuer_name", "insider_name",
                "relationship", "shares_to_sell", "dollar_value", "shares_outstanding", "approx_sale_date",
                "exchange", "broker", "notice_date", "has_10b5_1_plan", "gift_only"]


# -- Form 4: bulk quarterly dataset ------------------------------------------
def _tsv(z: zipfile.ZipFile, name: str, usecols: list[str]) -> pd.DataFrame:
    return pd.read_csv(io.BytesIO(z.read(name)), sep="\t", usecols=usecols, dtype=str,
                       keep_default_na=False, low_memory=False, encoding="utf-8", on_bad_lines="skip")


def _sec_date(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, format="%d-%b-%Y", errors="coerce").dt.strftime("%Y-%m-%d").fillna("")


def form4_from_dataset(zip_bytes: bytes, quarter_label: str) -> pd.DataFrame:
    """Every non-derivative transaction in one quarterly zip, one row per
    (transaction, reporting owner)."""
    z = zipfile.ZipFile(io.BytesIO(zip_bytes))
    sub = _tsv(z, "SUBMISSION.tsv", ["ACCESSION_NUMBER", "FILING_DATE", "DOCUMENT_TYPE", "ISSUERCIK",
                                     "ISSUERNAME", "ISSUERTRADINGSYMBOL"])
    own = _tsv(z, "REPORTINGOWNER.tsv", ["ACCESSION_NUMBER", "RPTOWNERCIK", "RPTOWNERNAME", "RPTOWNER_RELATIONSHIP"])
    tr = _tsv(z, "NONDERIV_TRANS.tsv", ["ACCESSION_NUMBER", "TRANS_DATE", "TRANS_CODE", "TRANS_SHARES",
                                        "TRANS_PRICEPERSHARE", "TRANS_ACQUIRED_DISP_CD", "SHRS_OWND_FOLWNG_TRANS"])
    df = tr.merge(sub, on="ACCESSION_NUMBER", how="inner").merge(own, on="ACCESSION_NUMBER", how="inner")
    out = pd.DataFrame({
        "accession": df["ACCESSION_NUMBER"],
        "filing_date": _sec_date(df["FILING_DATE"]),
        "issuer_cik": df["ISSUERCIK"].str.zfill(10),
        "issuer_ticker": df["ISSUERTRADINGSYMBOL"].str.upper(),
        "issuer_name": df["ISSUERNAME"],
        "owner_cik": df["RPTOWNERCIK"].str.zfill(10),
        "owner_name": df["RPTOWNERNAME"],
        "owner_relationship": df["RPTOWNER_RELATIONSHIP"],
        "transaction_date": _sec_date(df["TRANS_DATE"]),
        "code": df["TRANS_CODE"],
        "acquired_disposed": df["TRANS_ACQUIRED_DISP_CD"],
        "shares": pd.to_numeric(df["TRANS_SHARES"], errors="coerce").fillna(0.0),
        "price": pd.to_numeric(df["TRANS_PRICEPERSHARE"], errors="coerce").fillna(0.0),
        "shares_after": pd.to_numeric(df["SHRS_OWND_FOLWNG_TRANS"], errors="coerce").fillna(0.0),
        "source": f"dataset:{quarter_label}",
    })
    return out[F4_COLUMNS]


def backfill_form4(client: SecClient, quarters: list[tuple[int, int]], *, root: str = LEDGER_ROOT) -> None:
    for y, q in quarters:
        label = f"{y}q{q}"
        try:
            b = client.get(DATASET.format(y=y, q=q), cache=True)
        except Exception as e:  # noqa: BLE001
            print(f"form4 {label}  FAIL  {type(e).__name__}: {str(e)[:80]}")
            continue
        df = form4_from_dataset(b, label)
        df["key"] = df["accession"] + ":" + df["owner_cik"] + ":" + df.groupby(["accession", "owner_cik"]).cumcount().astype(str)
        added = append("form4", df.to_dict("records"), "key", root=root)
        print(f"form4 {label}  rows={len(df)}  sales={int((df.code == 'S').sum())}  added={added}")


# -- Form 4: current quarter via EFTS + XML -----------------------------------
def collect_form4_recent(client: SecClient, start: date, end: date, *, root: str = LEDGER_ROOT) -> int:
    hits = search(client, forms="4", start=start, end=end)
    have = keys("form4", "key", root=root)
    rows = []
    for h in hits:
        acc = h["_source"]["adsh"]
        if any(k.startswith(acc + ":") for k in have):
            continue
        doc = h["_id"].split(":", 1)[1] if ":" in h["_id"] else ""
        cik = h["_source"]["ciks"][0] if h["_source"].get("ciks") else ""
        if not doc.endswith(".xml") or not cik:
            continue
        try:
            xml = client.get(f"{ARCHIVES}/{int(cik)}/{acc.replace('-', '')}/{doc}", cache=True).decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            continue
        for i, r in enumerate(parse_form4(xml)):
            rows.append({"accession": acc, "filing_date": h["_source"]["file_date"], "issuer_cik": r["issuer_cik"],
                         "issuer_ticker": r["issuer_ticker"], "issuer_name": r["issuer_name"],
                         "owner_cik": r["owner_cik"], "owner_name": r["owner_name"],
                         "owner_relationship": ("Officer" if r["is_officer"] else "Director" if r["is_director"] else "TenPercentOwner" if r["is_ten_pct"] else "Other"),
                         "transaction_date": r["transaction_date"], "code": r["code"],
                         "acquired_disposed": r["acquired_disposed"], "shares": r["shares"], "price": r["price"],
                         "shares_after": r["shares_after"], "source": "efts", "key": f"{acc}:{r['owner_cik']}:{i}"})
    added = append("form4", rows, "key", root=root)
    print(f"form4 efts {start}..{end}  hits={len(hits)}  rows={len(rows)}  added={added}")
    return added


# -- Form 144 ---------------------------------------------------------------
def _split_144_ciks(hit: dict) -> tuple[str, str]:
    """A Form 144 hit lists the filer (the person) and the issuer. The
    submitter prefix of the accession is usually the filer; the issuer is
    the other CIK. When only one CIK is present it is the issuer."""
    s = hit["_source"]
    ciks = [f"{int(c):010d}" for c in s.get("ciks", [])]
    if len(ciks) == 1:
        return ciks[0], ""
    sub = f"{int(s['adsh'].split('-')[0]):010d}"
    others = [c for c in ciks if c != sub]
    if sub in ciks and others:
        return others[0], sub
    return ciks[0], ciks[1]


def collect_form144(client: SecClient, start: date, end: date, *, root: str = LEDGER_ROOT) -> int:
    hits = search(client, forms="144", start=start, end=end)
    have = keys("form144", "accession", root=root)
    rows, skipped = [], 0
    for h in hits:
        acc = h["_source"]["adsh"]
        if acc in have:
            continue
        doc = h["_id"].split(":", 1)[1] if ":" in h["_id"] else ""
        if not doc.endswith(".xml"):
            skipped += 1        # pre-April-2023 paper/PDF notices
            continue
        issuer_cik, owner_cik = _split_144_ciks(h)
        fetch_cik = h["_source"]["ciks"][0]
        try:
            xml = client.get(f"{ARCHIVES}/{int(fetch_cik)}/{acc.replace('-', '')}/{doc}", cache=True).decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            skipped += 1
            continue
        r = parse_form144(xml)
        if r is None:
            skipped += 1
            continue
        rows.append({"accession": acc, "filed_at": h["_source"]["file_date"], "issuer_cik": issuer_cik,
                     "owner_cik": owner_cik, **r})
    added = append("form144", rows, "accession", root=root)
    print(f"form144 {start}..{end}  hits={len(hits)}  parsed={len(rows)}  skipped={skipped}  added={added}")
    return added
