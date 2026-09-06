from datetime import datetime, timezone

import pandas as pd

from tirramind.store import digest, read_index, snapshot, snapshots_for


def _df(rows):
    return pd.DataFrame(rows, columns=["cik", "ticker"])


def test_same_content_twice_writes_once(tmp_path):
    root = str(tmp_path)
    a = _df([("1", "AAA"), ("2", "BBB")])
    p1, d1, s1 = snapshot("t", a, root=root)
    p2, d2, s2 = snapshot("t", a, root=root)
    assert s1 == "new" and p1 and p1.endswith(f"_{d1}.csv")
    assert s2 == "unchanged" and p2 is None and d2 == d1
    idx = read_index(root)
    assert [r["status"] for r in idx] == ["new", "unchanged"]
    assert len(snapshots_for("t", root=root)) == 1


def test_digest_ignores_row_and_column_order():
    a = _df([("1", "AAA"), ("2", "BBB")])
    b = pd.DataFrame([("BBB", "2"), ("AAA", "1")], columns=["ticker", "cik"])
    assert digest(a) == digest(b)


def test_changed_content_writes_new_file(tmp_path):
    root = str(tmp_path)
    snapshot("t", _df([("1", "AAA")]), root=root)
    _, _, s = snapshot("t", _df([("1", "AAA"), ("2", "BBB")]), root=root)
    assert s == "new"
    assert len(snapshots_for("t", root=root)) == 2


def test_backfill_timestamp_and_source(tmp_path):
    root = str(tmp_path)
    ts = datetime(2019, 3, 1, 12, tzinfo=timezone.utc)
    p, _, _ = snapshot("t", _df([("1", "AAA")]), root=root, captured_at=ts, source="wayback")
    assert "2019-03-01_" in p
    row = read_index(root)[0]
    assert row["source"] == "wayback" and row["captured_at"].startswith("2019-03-01")
