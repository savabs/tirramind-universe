from tirramind.tickers import COLUMNS, canonical_frame

TICKERS = {
    "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
    "1": {"cik_str": 1018724, "ticker": "amzn", "title": "AMAZON COM INC"},
    "2": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
}
EXCHANGE = {
    "fields": ["cik", "name", "ticker", "exchange"],
    "data": [[320193, "Apple Inc.", "AAPL", "Nasdaq"], [1018724, "AMAZON COM INC", "AMZN", "Nasdaq"]],
}


def test_canonical_frame_merges_and_normalises():
    df = canonical_frame(TICKERS, EXCHANGE)
    assert list(df.columns) == COLUMNS
    assert len(df) == 2  # duplicate AAPL row collapsed
    assert df.iloc[0].cik == "0000320193" and df.iloc[0].exchange == "Nasdaq"
    assert df.iloc[1].ticker == "AMZN"


def test_canonical_frame_without_exchange_file():
    df = canonical_frame(TICKERS, None)
    assert (df.exchange == "").all()
