from tirramind.filings import hit_to_row
from tirramind.ledger import append, read

NSE = {"_id": "0001417835-24-000050:primary_doc.xml", "_source": {
    "adsh": "0001417835-24-000050", "file_type": "25-NSE", "file_date": "2024-03-05",
    "ciks": ["0001527428", "0001417835"],
    "display_names": ["Arrow Investments Trust  (CIK 0001527428)", "Cboe BZX Exchange, Inc.  (CIK 0001417835)"],
    "items": [], "period_ending": None}}
EIGHTK = {"_id": "0001999371-24-003109:nanophase-8k_030124.htm", "_source": {
    "adsh": "0001999371-24-003109", "file_type": "8-K", "file_date": "2024-03-05",
    "ciks": ["0000883107"], "display_names": ["NANOPHASE TECHNOLOGIES Corp  (NANX)  (CIK 0000883107)"],
    "items": ["1.01", "2.02", "3.02", "3.03", "5.03", "9.01"], "period_ending": "2024-03-01"}}


def test_form25_subject_is_issuer_not_exchange():
    r = hit_to_row(NSE)
    assert r["subject_cik"] == "0001527428"
    assert r["submitter_cik"] == "0001417835"
    assert r["primary_doc"] == "primary_doc.xml"


def test_8k_items_flattened():
    r = hit_to_row(EIGHTK)
    assert r["items"] == "1.01,2.02,3.02,3.03,5.03,9.01"
    assert r["subject_cik"] == "0000883107"
    assert r["submitter_cik"] == "0001999371"  # filing agent, not the issuer


def test_ledger_append_is_idempotent(tmp_path):
    root = str(tmp_path)
    rows = [hit_to_row(NSE), hit_to_row(EIGHTK)]
    assert append("filings", rows, "accession", root=root) == 2
    assert append("filings", rows, "accession", root=root) == 0
    assert len(read("filings", root=root)) == 2
