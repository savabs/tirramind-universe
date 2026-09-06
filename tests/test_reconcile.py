import pandas as pd

from tirramind.reconcile import CAUSES, reconcile, summary

EV_COLS = ["event", "cik", "ticker", "name", "exchange", "from_captured_at", "to_captured_at", "superseded_by", "superseded_kind"]
F_COLS = ["accession", "form", "items", "submitter_cik", "subject_cik", "all_ciks", "filed_at"]


def _ev(cik, tk, to="2024-04-01T00:00:00+00:00", sib="", kind=""):
    return ["DELISTED_FROM_MAP", cik, tk, tk + " Corp", "NYSE", "2024-03-01T00:00:00+00:00", to, sib, kind]


def _f(acc, form, items, sub, subj, filed, extra=""):
    return [acc, form, items, sub, subj, subj + ("," + extra if extra else ""), filed]


EX = "0000000099"  # an exchange CIK
FILINGS = pd.DataFrame([
    _f("a1", "8-K", "1.03,9.01", "0000000001", "0000000001", "2024-03-20"),      # bankruptcy
    _f("a2", "25-NSE", "", EX, "0000000002", "2024-03-25"),                      # exchange-filed
    _f("a3", "25", "", "0000000003", "0000000003", "2024-03-25"),                # issuer-filed
    _f("a4", "8-K", "2.01,9.01", "0000000003", "0000000003", "2024-03-15"),      # + acquisition
    _f("a5b", "15-12G", "", "0000000003", "0000000003", "2024-03-29"),           # + deregistered = real merger
    _f("a5", "15-12G", "", "0000000004", "0000000004", "2024-03-28"),            # dereg only
    _f("a6", "25", "", "0000000005", "0000000005", "2024-03-25"),                # voluntary
    _f("a7", "8-K", "3.01", "0000000006", "0000000006", "2023-01-01"),           # outside window
    _f("a8", "8-K", "2.01,9.01", "0000000008", "0000000008", "2024-03-10"),      # acquirer, still listed
    _f("a9", "25", "", "0000000008", "0000000008", "2024-03-12"),                # issuer-filed 25 (transfer)
    _f("c1", "8-K", "2.01,3.01,9.01", "0000000012", "0000000012", "2024-03-10"), # CSWI pattern: acquirer + 3.01 transfer notice
    _f("c2", "25", "", "0000000012", "0000000012", "2024-03-12"),
    _f("b1", "8-K", "1.03", "0000000090", "0000000090", "2024-03-10", "0000000009"),  # parent files, LP is co-registrant
], columns=F_COLS)
EVENTS = pd.DataFrame([_ev(f"{i:010d}", f"T{i}") for i in range(1, 10)]
                      + [_ev("0000000001", "T1Q", sib="T1Q", kind="SYMBOL_CHANGED"),      # bankrupt + sibling: filing wins
                         _ev("0000000008", "T8X", sib="T8", kind="EXCHANGE_TRANSFER"),   # voluntary + sibling: transfer
                         _ev("0000000011", "T11", sib="T11N", kind="SYMBOL_CHANGED"),    # unknown + sibling: symbol change
                         _ev("0000000012", "T12", sib="T12N", kind="EXCHANGE_TRANSFER")], # merger-looking 8-K but moved exchange
                      columns=EV_COLS)


def test_causes_and_evidence():
    rec = reconcile(EVENTS, FILINGS).drop_duplicates("cik", keep="first").set_index("cik")
    assert rec.loc["0000000001", "cause"] == "BANKRUPTCY"
    assert rec.loc["0000000002", "cause"] == "EXCHANGE_DELISTING"
    assert rec.loc["0000000003", "cause"] == "MERGER_ACQUISITION"
    assert rec.loc["0000000004", "cause"] == "DEREGISTRATION"
    assert rec.loc["0000000005", "cause"] == "VOLUNTARY_DELISTING"
    assert rec.loc["0000000006", "cause"] == "UNKNOWN"   # filing outside window
    assert rec.loc["0000000007", "cause"] == "UNKNOWN"   # no filings at all
    assert rec.loc["0000000003", "evidence_accessions"] == "a3,a4,a5b"
    assert rec.loc["0000000006", "n_filings_in_window"] == 0
    assert rec.loc["0000000008", "cause"] == "VOLUNTARY_DELISTING"   # 2.01 as acquirer is not a merger
    assert rec.loc["0000000009", "cause"] == "BANKRUPTCY"            # matched via co-registrant CIK
    assert rec.loc["0000000011", "cause"] == "SYMBOL_CHANGED"
    r = reconcile(EVENTS, FILINGS)
    assert r[r.ticker.eq("T1Q")].cause.iloc[0] == "BANKRUPTCY"
    assert r[r.ticker.eq("T8X")].cause.iloc[0] == "EXCHANGE_TRANSFER"
    assert r[r.ticker.eq("T12")].cause.iloc[0] == "EXCHANGE_TRANSFER"


def test_unknown_is_reported_in_summary():
    s = summary(reconcile(EVENTS, FILINGS))
    assert list(s.index) == CAUSES
    assert abs(s["UNKNOWN"] - 2 / 10) < 1e-9   # 13 rows minus 3 non-delistings


def test_non_delist_events_ignored():
    ev = EVENTS.copy()
    ev.loc[0, "event"] = "LISTED"
    assert len(reconcile(ev, FILINGS)) == 12
