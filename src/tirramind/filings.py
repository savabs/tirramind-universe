"""B4: delisting-relevant filings from EDGAR full-text search (EFTS).

EFTS returns structured hits: accession (``adsh``), form, filing date, the
CIKs involved, and for 8-Ks the ``items`` array. That is all we need — no
document parsing at this stage. Form 25-NSE is filed by the *exchange*
against the issuer, so the hit lists two CIKs; the subject is the one that
is not an exchange. The accession prefix is the *submitter* (often a filing
agent such as Toppan Merrill), never assumed to be the issuer.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

from .ledger import DEFAULT_ROOT as LEDGER_ROOT, append
from .sec import SecClient

EFTS = "https://efts.sec.gov/LATEST/search-index"
PAGE = 100
EFTS_CAP = 10_000

# Forms that mark a removal from listing or registration.
DELISTING_FORMS = ["25", "25-NSE", "15-12G", "15-12B", "15-15D"]
# 8-K items: 1.03 bankruptcy, 3.01 delisting notice, 5.03 charter amendment.
EIGHT_K_ITEMS = ["1.03", "3.01", "5.03"]

_EXCHANGE_RE = re.compile(r"exchange|nasdaq|nyse|cboe|bats|iex|miax|memx|ltse", re.I)
LEDGER = "filings"
COLUMNS = ["accession", "form", "items", "submitter_cik", "subject_cik", "all_ciks",
           "display_names", "filed_at", "period_ending", "primary_doc"]


def _subject_cik(ciks: list[str], names: list[str]) -> str:
    if len(ciks) == 1:
        return ciks[0]
    non_exchange = [c for c, n in zip(ciks, names) if not _EXCHANGE_RE.search(n)]
    return non_exchange[0] if non_exchange else ciks[0]


def hit_to_row(hit: dict) -> dict:
    s = hit["_source"]
    ciks = [f"{int(c):010d}" for c in s.get("ciks", [])]
    names = s.get("display_names", [])
    acc = s["adsh"]
    return {
        "accession": acc,
        "form": s["file_type"],
        "items": ",".join(s.get("items") or []),
        "submitter_cik": f"{int(acc.split('-')[0]):010d}",
        "subject_cik": _subject_cik(ciks, names),
        "all_ciks": ",".join(ciks),
        "display_names": " | ".join(names),
        "filed_at": s["file_date"],
        "period_ending": s.get("period_ending") or "",
        "primary_doc": hit["_id"].split(":", 1)[1] if ":" in hit["_id"] else "",
    }


def search(client: SecClient, *, forms: str, start: date, end: date, q: str | None = None) -> list[dict]:
    """All EFTS hits for ``forms`` in [start, end]; splits the window when
    it would exceed the 10,000-hit cap."""
    params = {"forms": forms, "dateRange": "custom", "startdt": str(start), "enddt": str(end),
              "from": "0", "size": str(PAGE)}
    if q:
        params["q"] = q
    first = client.get_json(EFTS, params=params)
    total = first["hits"]["total"]["value"]
    if total > EFTS_CAP and (end - start).days >= 1:
        mid = start + (end - start) / 2
        return search(client, forms=forms, start=start, end=mid, q=q) + \
            search(client, forms=forms, start=mid + timedelta(days=1), end=end, q=q)
    hits = list(first["hits"]["hits"])
    offset = PAGE
    while offset < total:
        page = client.get_json(EFTS, params={**params, "from": str(offset)})
        got = page["hits"]["hits"]
        if not got:
            break
        hits.extend(got)
        offset += PAGE
    return hits


def collect(client: SecClient, start: date, end: date, *, root: str = LEDGER_ROOT) -> dict[str, int]:
    """Collect delisting forms and item-filtered 8-Ks for [start, end] into
    the filings ledger. Returns counts found per query and rows added."""
    counts: dict[str, int] = {}
    rows: list[dict] = []
    for form in DELISTING_FORMS:
        hits = search(client, forms=form, start=start, end=end)
        counts[form] = len(hits)
        rows.extend(hit_to_row(h) for h in hits)
    for item in EIGHT_K_ITEMS:
        hits = search(client, forms="8-K", start=start, end=end, q=f'"Item {item}"')
        kept = [h for h in hits if item in (h["_source"].get("items") or [])]
        counts[f"8-K:{item}"] = len(kept)
        rows.extend(hit_to_row(h) for h in kept)
    added = append(LEDGER, rows, "accession", root=root)
    counts["added"] = added
    return counts


def backfill(client: SecClient, start: date, end: date, *, root: str = LEDGER_ROOT) -> None:
    """Month by month so a failure loses at most one month."""
    cur = start
    while cur <= end:
        nxt = (cur.replace(day=1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        nxt = min(nxt, end)
        try:
            c = collect(client, cur, nxt, root=root)
            print(f"{cur:%Y-%m}  " + "  ".join(f"{k}={v}" for k, v in c.items()))
        except Exception as e:  # noqa: BLE001
            print(f"{cur:%Y-%m}  FAIL  {type(e).__name__}: {str(e)[:100]}")
        cur = nxt + timedelta(days=1)
