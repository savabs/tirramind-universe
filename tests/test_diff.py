import pandas as pd

from tirramind.diff import diff_frames


def _f(rows):
    return pd.DataFrame(rows, columns=["cik", "ticker", "name", "exchange"])


PREV = _f([
    ("0000000001", "AAA", "Alpha", "NYSE"),
    ("0000000002", "BBB", "Beta", "Nasdaq"),
    ("0000000003", "CCC", "Gamma", "OTC"),
    ("0000000004", "DDD", "Delta", "NYSE"),
    ("0000000005", "EEE", "Eps", "NYSE"),
])
CURR = _f([
    ("0000000001", "AAA", "Alpha Holdings", "NYSE"),   # name change
    ("0000000002", "BBBX", "Beta", "Nasdaq"),          # symbol change
    ("0000000004", "DDD", "Delta", "Nasdaq"),          # exchange change
    ("0000000005", "EEE", "Eps", "NYSE"),              # unchanged
    ("0000000006", "FFF", "Zeta", "NYSE"),             # listed
])                                                      # CCC delisted


def test_exact_event_set():
    ev = diff_frames(PREV, CURR)
    got = {(r.event, r.cik, r.ticker, r.prev_ticker) for r in ev.itertuples()}
    assert got == {
        ("NAME_CHANGED", "0000000001", "AAA", "AAA"),
        ("SYMBOL_CHANGED", "0000000002", "BBBX", "BBB"),
        ("EXCHANGE_CHANGED", "0000000004", "DDD", "DDD"),
        ("LISTED", "0000000006", "FFF", ""),
        ("DELISTED_FROM_MAP", "0000000003", "CCC", "CCC"),
    }


def test_symbol_change_is_not_delist_plus_list():
    ev = diff_frames(PREV, CURR)
    assert not ((ev.event == "DELISTED_FROM_MAP") & (ev.cik == "0000000002")).any()
    assert not ((ev.event == "LISTED") & (ev.cik == "0000000002")).any()


def test_empty_exchange_does_not_emit_exchange_change():
    a = _f([("1", "A", "A", "")])
    b = _f([("1", "A", "A", "NYSE")])
    assert diff_frames(a, b).empty


def test_identical_frames_no_events():
    assert diff_frames(PREV, PREV).empty


def test_annotate_flags_flaps_suspect_steps_and_cosmetic_renames():
    from tirramind.diff import SUSPECT_REMOVALS, annotate, permanent_removals
    cols = ["event", "cik", "ticker", "name", "exchange", "prev_ticker", "prev_name", "prev_exchange",
            "from_captured_at", "to_captured_at", "from_digest", "to_digest"]
    ev = pd.DataFrame([
        ["DELISTED_FROM_MAP", "1", "AAA", "A", "", "AAA", "A", "", "t0", "t1", "", ""],   # flap: relisted at t2
        ["LISTED",            "1", "AAA", "A", "", "", "", "", "t1", "t2", "", ""],
        ["DELISTED_FROM_MAP", "2", "BBB", "B", "", "BBB", "B", "", "t1", "t2", "", ""],   # permanent
        ["NAME_CHANGED",      "3", "CCC", "APPLE INC.", "", "CCC", "Apple Inc", "", "t1", "t2", "", ""],
        ["NAME_CHANGED",      "4", "DDD", "New Co", "", "DDD", "Old Co", "", "t1", "t2", "", ""],
    ] + [["DELISTED_FROM_MAP", str(100 + i), "X%d" % i, "", "", "X%d" % i, "", "", "t2", "t3", "", ""]
         for i in range(SUSPECT_REMOVALS)], columns=cols)
    a = annotate(ev)
    assert a.loc[0, "relisted_at"] == "t2" and a.loc[2, "relisted_at"] == ""
    assert bool(a.loc[3, "cosmetic"]) and not bool(a.loc[4, "cosmetic"])
    assert a[a.to_captured_at.eq("t3")].suspect.all() and not a.loc[2, "suspect"]
    perm = permanent_removals(a)
    assert list(perm.cik) == ["2"]


def test_sibling_ticker_marks_symbol_change_or_transfer():
    from tirramind.diff import annotate, permanent_removals
    cols = ["event", "cik", "ticker", "name", "exchange", "prev_ticker", "prev_name", "prev_exchange",
            "from_captured_at", "to_captured_at", "from_digest", "to_digest"]
    ev = pd.DataFrame([
        ["LISTED",            "7", "FUNI", "", "OTC",    "", "", "", "2024-09-10T00:00:00+00:00", "2024-09-18T00:00:00+00:00", "", ""],
        ["DELISTED_FROM_MAP", "7", "DIGP", "", "OTC",    "DIGP", "", "", "2024-09-18T00:00:00+00:00", "2024-09-27T00:00:00+00:00", "", ""],
        ["LISTED",            "8", "CSW",  "", "NYSE",   "", "", "", "2025-06-01T00:00:00+00:00", "2025-06-21T00:00:00+00:00", "", ""],
        ["DELISTED_FROM_MAP", "8", "CSWI", "", "Nasdaq", "CSWI", "", "", "2025-06-21T00:00:00+00:00", "2025-07-04T00:00:00+00:00", "", ""],
        ["DELISTED_FROM_MAP", "9", "GONE", "", "NYSE",   "GONE", "", "", "2025-06-21T00:00:00+00:00", "2025-07-04T00:00:00+00:00", "", ""],
    ], columns=cols)
    a = annotate(ev).set_index("ticker")
    assert a.loc["DIGP", "superseded_by"] == "FUNI" and a.loc["DIGP", "superseded_kind"] == "SYMBOL_CHANGED"
    assert a.loc["CSWI", "superseded_by"] == "CSW" and a.loc["CSWI", "superseded_kind"] == "EXCHANGE_TRANSFER"
    assert sorted(permanent_removals(annotate(ev)).ticker) == ["CSWI", "DIGP", "GONE"]  # filings decide, not the sibling
