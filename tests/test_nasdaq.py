from tirramind.nasdaq import parse_directory

NAS = """Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares
AAPL|Apple Inc. - Common Stock|Q|N|N|100|N|N
ZTEST|Test Issue|G|Y|N|100|N|N
aacg|ATA Creativity Global|S|N|N|100|N|N
File Creation Time: 0905202621:31|||||||"""
OTH = """ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol
A|Agilent Technologies|N|A|N|100|N|A
SPY|SPDR S&P 500|P|SPY|Y|100|N|SPY
File Creation Time: 0905202621:31|||||||"""


def test_parse_nasdaq_directory_drops_test_issues_and_uppercases():
    df = parse_directory(NAS, kind="nasdaq")
    assert list(df.ticker) == ["AACG", "AAPL"] and (df.exchange == "Nasdaq").all()


def test_parse_other_listed_maps_exchange_codes():
    df = parse_directory(OTH, kind="other")
    assert dict(zip(df.ticker, df.exchange)) == {"A": "NYSE", "SPY": "NYSE ARCA"}
    assert df[df.ticker.eq("SPY")].etf.iloc[0] == "Y"
