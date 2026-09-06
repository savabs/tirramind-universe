import os

from tirramind.forms import FORM4_COLUMNS, FORM144_COLUMNS, parse_form4, parse_form144

FX = os.path.join(os.path.dirname(__file__), "fixtures")


def _read(name):
    with open(os.path.join(FX, name), encoding="utf-8") as fh:
        return fh.read()


def test_form4_returns_sales_that_the_old_parser_dropped():
    rows = parse_form4(_read("form4_sale.xml"))
    assert [r["code"] for r in rows] == ["S", "F"]
    s = rows[0]
    assert list(s) == FORM4_COLUMNS
    assert s["issuer_cik"] == "0000320193" and s["issuer_ticker"] == "AAPL"
    assert s["owner_cik"] == "0001214128" and s["is_officer"] and s["is_director"]
    assert s["shares"] == 196410.0 and s["price"] == 169.5 and s["acquired_disposed"] == "D"
    assert s["transaction_date"] == "2024-04-02" and s["shares_after"] == 3280000.0


def test_form4_namespaced_purchase_and_boolean_flags():
    rows = parse_form4(_read("form4_purchase_ns.xml"))
    assert len(rows) == 1
    r = rows[0]
    assert r["code"] == "P" and r["issuer_cik"] == "0001018724"
    assert r["is_director"] and not r["is_officer"] and r["is_ten_pct"]


def test_form4_garbage_is_empty():
    assert parse_form4("<not xml") == []


def test_form144_fields():
    r = parse_form144(_read("form144.xml"))
    assert list(r) == FORM144_COLUMNS
    assert r["insider_name"] == "Timothy D. Cook" and r["relationship"] == "Officer"
    assert r["shares_to_sell"] == 196410.0 and r["dollar_value"] == 33291495.0
    assert r["approx_sale_date"] == "2024-04-02" and r["notice_date"] == "2024-04-01"
    assert r["has_10b5_1_plan"] is True and r["gift_only"] is False
    assert r["broker"].startswith("Goldman")


def test_form144_gift_only_flagged_not_dropped():
    r = parse_form144(_read("form144_gift.xml"))
    assert r is not None and r["gift_only"] is True
