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
