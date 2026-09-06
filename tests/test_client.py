import pandas as pd
import pytest

import tirramind


def test_load_from_local_dir(tmp_path, monkeypatch):
    pd.DataFrame({"event": ["LISTED", "DELISTED_FROM_MAP"], "cik": ["1", "2"],
                  "to_captured_at": ["2025-01-02", "2025-03-04"]}).to_parquet(tmp_path / "events.parquet")
    pd.DataFrame({"cause": ["BANKRUPTCY", "UNKNOWN"], "to_captured_at": ["2025-01-02", "2025-03-04"]}).to_parquet(tmp_path / "delistings.parquet")
    monkeypatch.setenv("TIRRAMIND_DATA", str(tmp_path))
    assert len(tirramind.load("events")) == 2
    assert list(tirramind.events(since="2025-02-01").event) == ["DELISTED_FROM_MAP"]
    assert list(tirramind.delistings(cause="BANKRUPTCY").cause) == ["BANKRUPTCY"]


def test_unknown_table():
    with pytest.raises(KeyError):
        tirramind.load("nope")
