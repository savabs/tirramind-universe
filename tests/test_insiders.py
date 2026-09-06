import io
import zipfile

from tirramind.insiders import F4_COLUMNS, _split_144_ciks, form4_from_dataset


def _zip(files: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for k, v in files.items():
            z.writestr(k, v)
    return buf.getvalue()


SUB = "ACCESSION_NUMBER\tFILING_DATE\tPERIOD_OF_REPORT\tDOCUMENT_TYPE\tISSUERCIK\tISSUERNAME\tISSUERTRADINGSYMBOL\n" \
      "0001-25-000001\t31-MAR-2025\t28-MAR-2025\t4\t0000320193\tApple Inc.\taapl\n"
OWN = "ACCESSION_NUMBER\tRPTOWNERCIK\tRPTOWNERNAME\tRPTOWNER_RELATIONSHIP\tRPTOWNER_TITLE\n" \
      "0001-25-000001\t0001214128\tCOOK TIMOTHY D\tOfficer\tCEO\n"
TR = "ACCESSION_NUMBER\tNONDERIV_TRANS_SK\tTRANS_DATE\tTRANS_CODE\tTRANS_SHARES\tTRANS_PRICEPERSHARE\tTRANS_ACQUIRED_DISP_CD\tSHRS_OWND_FOLWNG_TRANS\n" \
     "0001-25-000001\t1\t28-MAR-2025\tS\t1000.0\t210.5\tD\t50000.0\n" \
     "0001-25-000001\t2\t27-MAR-2025\tF\t100.0\t\tD\t51000.0\n"


def test_form4_from_dataset_joins_three_tables():
    df = form4_from_dataset(_zip({"SUBMISSION.tsv": SUB, "REPORTINGOWNER.tsv": OWN, "NONDERIV_TRANS.tsv": TR}), "2025q1")
    assert list(df.columns) == F4_COLUMNS and len(df) == 2
    s = df[df.code == "S"].iloc[0]
    assert s.issuer_cik == "0000320193" and s.issuer_ticker == "AAPL" and s.owner_cik == "0001214128"
    assert s.transaction_date == "2025-03-28" and s.filing_date == "2025-03-31"
    assert s.shares == 1000.0 and s.price == 210.5 and s.acquired_disposed == "D"
    assert df[df.code == "F"].iloc[0].price == 0.0
    assert (df.source == "dataset:2025q1").all()


def test_split_144_ciks():
    hit = {"_source": {"adsh": "0001214128-24-000003", "ciks": ["0000320193", "0001214128"]}}
    assert _split_144_ciks(hit) == ("0000320193", "0001214128")
    assert _split_144_ciks({"_source": {"adsh": "0009-24-1", "ciks": ["0000320193"]}}) == ("0000320193", "")
