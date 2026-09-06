import pandas as pd

from tirramind.reconcile import CAUSES, reconcile, summary

EV_COLS = ["event", "cik", "ticker", "name", "exchange", "from_captured_at", "to_captured_at"]
F_COLS = ["accession", "form", "items", "submitter_cik", "subject_cik", "filed_at"]


def _ev(cik, tk, to="2024-04-01T00:00:00+00:00"):
    return ["DELISTED_FROM_MAP", cik, tk, tk + " Corp", "NYSE", "2024-03-01T00:00:00+00:00", to]


def _f(acc, form, items, sub, subj, filed):
    return [acc, form, items, sub, subj, filed]


EX = "0000000099"  # an exchange CIK
FILINGS = pd.DataFrame([
    _f("a1", "8-K", "1.03,9.01", "0000000001", "0000000001", "2024-03-20"),      # bankruptcy
    _f("a2", "25-NSE", "", EX, "0000000002", "2024-03-25"),                      # exchange-filed
    _f("a3", "25", "", "0000000003", "0000000003", "2024-03-25"),                # issuer-filed
    _f("a4", "8-K", "2.01,9.01", "0000000003", "0000000003", "2024-03-15"),      # + acquisition
    _f("a5", "15-12G", "", "0000000004", "0000000004", "2024-03-28"),            # dereg only
    _f("a6", "25", "", "0000000005", "0000000005", "2024-03-25"),                # voluntary
    _f("a7", "8-K", "3.01", "0000000006", "0000000006", "2023-01-01"),           # outside window
], columns=F_COLS)
EVENTS = pd.DataFrame([_ev(f"{i:010d}", f"T{i}") for i in range(1, 8)], columns=EV_COLS)


def test_causes_and_evidence():
    rec = reconcile(EVENTS, FILINGS).set_index("cik")
    assert rec.loc["0000000001", "cause"] == "BANKRUPTCY"
    assert rec.loc["0000000002", "cause"] == "EXCHANGE_DELISTING"
    assert rec.loc["0000000003", "cause"] == "MERGER_ACQUISITION"
    assert rec.loc["0000000004", "cause"] == "DEREGISTRATION"
    assert rec.loc["0000000005", "cause"] == "VOLUNTARY_DELISTING"
    assert rec.loc["0000000006", "cause"] == "UNKNOWN"   # filing outside window
    assert rec.loc["0000000007", "cause"] == "UNKNOWN"   # no filings at all
    assert rec.loc["0000000003", "evidence_accessions"] == "a3,a4"
    assert rec.loc["0000000006", "n_filings_in_window"] == 0


def test_unknown_is_reported_in_summary():
    s = summary(reconcile(EVENTS, FILINGS))
    assert list(s.index) == CAUSES
    assert abs(s["UNKNOWN"] - 2 / 7) < 1e-9


def test_non_delist_events_ignored():
    ev = EVENTS.copy()
    ev.loc[0, "event"] = "LISTED"
    assert len(reconcile(ev, FILINGS)) == 6
