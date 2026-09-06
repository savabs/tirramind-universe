import pandas as pd

from tirramind.link import link, normalise_name

F144 = pd.DataFrame([
    # accession, issuer, owner, name, rel, notice, shares, $
    ["a", "0000000001", "0000000010", "Timothy D. Cook", "Officer", "2024-04-01", 1000, 100000],
    ["b", "0000000001", "", "Jane Q. Doe", "Director", "2024-04-01", 500, 5000],
    ["c", "0000000001", "0000000030", "Nobody Here", "Officer", "2024-04-01", 200, 2000],
    ["d", "0000000002", "0000000010", "Timothy D. Cook", "Officer", "2024-04-01", 100, 1000],
], columns=["accession", "issuer_cik", "owner_cik", "insider_name", "relationship", "notice_date", "shares_to_sell", "dollar_value"])

F4 = pd.DataFrame([
    ["0000000001", "0000000010", "COOK TIMOTHY D", "2024-04-03", "S", 600, 10.0],
    ["0000000001", "0000000010", "COOK TIMOTHY D", "2024-04-10", "S", 400, 12.0],
    ["0000000001", "0000000010", "COOK TIMOTHY D", "2024-09-01", "S", 999, 12.0],   # outside window
    ["0000000001", "0000000010", "COOK TIMOTHY D", "2024-04-04", "F", 50, 10.0],    # not a sale
    ["0000000001", "0000000020", "DOE JANE Q JR", "2024-04-05", "S", 250, 20.0],   # name-only match
    ["0000000002", "0000000010", "COOK TIMOTHY D", "2024-03-01", "S", 100, 10.0],  # before window
], columns=["issuer_cik", "owner_cik", "owner_name", "transaction_date", "code", "shares", "price"])


def test_cik_match_aggregates_only_window_sales():
    L = link(F144, F4).set_index("accession_144")
    a = L.loc["a"]
    assert a.match_method == "cik" and a.n_sales == 2 and a.shares_sold == 1000
    assert a.executed_fraction == 1.0 and a.days_to_first_sale == 2
    assert abs(a.vwap_sold - (600 * 10 + 400 * 12) / 1000) < 1e-9


def test_name_fallback_is_flagged():
    L = link(F144, F4).set_index("accession_144")
    b = L.loc["b"]
    assert b.match_method == "name" and b.shares_sold == 250 and b.executed_fraction == 0.5


def test_no_match_is_zero_not_missing():
    L = link(F144, F4).set_index("accession_144")
    assert L.loc["c"].match_method == "none" and L.loc["c"].executed_fraction == 0.0
    assert L.loc["c"].days_to_first_sale == -1
    d = L.loc["d"]  # cik matches but the sale predates the notice window
    assert d.n_sales == 0 and d.executed_fraction == 0.0


def test_window_complete_flag():
    L = link(F144, F4, coverage_end="2024-05-01").set_index("accession_144")
    assert not L.loc["a"].window_complete            # notice 2024-04-01 + 90d > coverage
    L2 = link(F144, F4, coverage_end="2024-12-31").set_index("accession_144")
    assert L2.loc["a"].window_complete


def test_normalise_name():
    assert normalise_name("COOK TIMOTHY D") == normalise_name("Timothy D. Cook")
    assert normalise_name("Doe, Jane Q. Jr.") == normalise_name("JANE Q DOE")
