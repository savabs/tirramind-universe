"""C1: Form 4 and Form 144 XML parsers.

Extracted from tirramind's collectors and stripped of storage coupling. The
original Form 4 parser kept only open-market purchases (code ``P``); the
144 -> 4 linkage needs sales, so this one returns every non-derivative
transaction and lets the caller filter by ``code``.

Transaction codes that matter here: ``S`` open-market sale, ``P`` open-market
purchase, ``F`` tax-withholding disposition, ``M`` option exercise.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime

FORM4_COLUMNS = [
    "issuer_cik", "issuer_ticker", "issuer_name", "owner_cik", "owner_name",
    "is_director", "is_officer", "is_ten_pct", "officer_title",
    "transaction_date", "code", "acquired_disposed", "shares", "price", "shares_after",
]
FORM144_COLUMNS = [
    "issuer_name", "insider_name", "relationship", "shares_to_sell", "dollar_value",
    "shares_outstanding", "approx_sale_date", "exchange", "broker",
    "notice_date", "has_10b5_1_plan", "gift_only",
]


def _ns(root) -> str:
    return root.tag.split("}")[0] + "}" if root.tag.startswith("{") else ""


def _text(el, path: str, ns: str, default: str = "") -> str:
    node = el.find(path.replace("{}", ns))
    return node.text.strip() if node is not None and node.text else default


def _float(s: str) -> float:
    try:
        return float(s.replace(",", ""))
    except (ValueError, AttributeError):
        return 0.0


def _flag(s: str) -> bool:
    return s.strip().lower() in ("1", "true", "y", "yes")


def _mmddyyyy(s: str) -> str:
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return ""


def parse_form4(xml_text: str) -> list[dict]:
    """Every non-derivative transaction in one Form 3/4/5 XML document.
    One row per (reporting owner, transaction). Empty list on parse failure."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    ns = _ns(root)
    issuer = root.find(f"{ns}issuer")
    if issuer is None:
        return []
    issuer_cik = _text(issuer, "{}issuerCik", ns).zfill(10)
    issuer_ticker = _text(issuer, "{}issuerTradingSymbol", ns).upper()
    issuer_name = _text(issuer, "{}issuerName", ns)

    owners = []
    for o in root.findall(f"{ns}reportingOwner"):
        rid = o.find(f"{ns}reportingOwnerId")
        rel = o.find(f"{ns}reportingOwnerRelationship")
        owners.append({
            "owner_cik": _text(rid, "{}rptOwnerCik", ns).zfill(10) if rid is not None else "",
            "owner_name": _text(rid, "{}rptOwnerName", ns) if rid is not None else "",
            "is_director": _flag(_text(rel, "{}isDirector", ns)) if rel is not None else False,
            "is_officer": _flag(_text(rel, "{}isOfficer", ns)) if rel is not None else False,
            "is_ten_pct": _flag(_text(rel, "{}isTenPercentOwner", ns)) if rel is not None else False,
            "officer_title": _text(rel, "{}officerTitle", ns) if rel is not None else "",
        })
    if not owners:
        return []

    rows = []
    table = root.find(f"{ns}nonDerivativeTable")
    for txn in (table.findall(f"{ns}nonDerivativeTransaction") if table is not None else []):
        row = {
            "issuer_cik": issuer_cik, "issuer_ticker": issuer_ticker, "issuer_name": issuer_name,
            "transaction_date": _text(txn, "{}transactionDate/{}value", ns),
            "code": _text(txn, "{}transactionCoding/{}transactionCode", ns),
            "acquired_disposed": _text(txn, "{}transactionAmounts/{}transactionAcquiredDisposedCode/{}value", ns),
            "shares": _float(_text(txn, "{}transactionAmounts/{}transactionShares/{}value", ns)),
            "price": _float(_text(txn, "{}transactionAmounts/{}transactionPricePerShare/{}value", ns)),
            "shares_after": _float(_text(txn, "{}postTransactionAmounts/{}sharesOwnedFollowingTransaction/{}value", ns)),
        }
        for o in owners:
            rows.append({**o, **row})
    return [{k: r[k] for k in FORM4_COLUMNS} for r in rows]


def parse_form144(xml_text: str) -> dict | None:
    """The single sell-intent in one Form 144 XML. None on parse failure or
    when nothing is to be sold. Gift-only notices are returned with
    ``gift_only=True`` rather than dropped, so the caller decides."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return None
    ns = _ns(root)
    fd = root.find(f"{ns}formData")
    if fd is None:
        return None
    issuer = fd.find(f"{ns}issuerInfo")
    sec = fd.find(f"{ns}securitiesInformation")
    sig = fd.find(f"{ns}noticeSignature")
    lots = fd.findall(f"{ns}securitiesToBeSold")
    gifts = [_flag(_text(lot, "{}isGiftTransaction", ns)) for lot in lots]
    row = {
        "issuer_name": _text(issuer, "{}issuerName", ns) if issuer is not None else "",
        "insider_name": _text(issuer, "{}nameOfPersonForWhoseAccountTheSecuritiesAreToBeSold", ns) if issuer is not None else "",
        "relationship": _text(issuer, "{}relationshipsToIssuer/{}relationshipToIssuer", ns) if issuer is not None else "",
        "shares_to_sell": _float(_text(sec, "{}noOfUnitsSold", ns)) if sec is not None else 0.0,
        "dollar_value": _float(_text(sec, "{}aggregateMarketValue", ns)) if sec is not None else 0.0,
        "shares_outstanding": _float(_text(sec, "{}noOfUnitsOutstanding", ns)) if sec is not None else 0.0,
        "approx_sale_date": _mmddyyyy(_text(sec, "{}approxSaleDate", ns)) if sec is not None else "",
        "exchange": _text(sec, "{}securitiesExchangeName", ns) if sec is not None else "",
        "broker": _text(sec, "{}brokerOrMarketmakerDetails/{}name", ns) if sec is not None else "",
        "notice_date": _mmddyyyy(_text(sig, "{}noticeDate", ns)) if sig is not None else "",
        "has_10b5_1_plan": bool(_text(sig, "{}planAdoptionDates", ns)) if sig is not None else False,
        "gift_only": bool(gifts) and all(gifts),
    }
    if row["shares_to_sell"] <= 0 and row["dollar_value"] <= 0:
        return None
    return row
