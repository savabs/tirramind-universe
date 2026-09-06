"""B2: events between two ticker-map snapshots.

Diffs are derived, never stored — recomputed from snapshots on demand so a
bug in this file can be fixed without rewriting history. Keys are
(cik, ticker). A CIK that keeps a ticker but changes name/exchange emits a
change event; a CIK whose ticker changes emits SYMBOL_CHANGED (matched on
CIK) rather than a delist+list pair.
"""

from __future__ import annotations

import pandas as pd

from .store import DEFAULT_ROOT, load_snapshot, snapshots_for

EVENT_COLUMNS = [
    "event", "cik", "ticker", "name", "exchange",
    "prev_ticker", "prev_name", "prev_exchange",
    "from_captured_at", "to_captured_at", "from_digest", "to_digest",
]


def diff_frames(prev: pd.DataFrame, curr: pd.DataFrame) -> pd.DataFrame:
    """Events from ``prev`` -> ``curr``. Both are canonical ticker frames."""
    p = prev.set_index(["cik", "ticker"])
    c = curr.set_index(["cik", "ticker"])
    gone = p.index.difference(c.index)
    new = c.index.difference(p.index)
    both = p.index.intersection(c.index)

    events: list[dict] = []

    # Symbol changes: same CIK, ticker left and a ticker arrived.
    gone_by_cik = {}
    for cik, tk in gone:
        gone_by_cik.setdefault(cik, []).append(tk)
    new_by_cik = {}
    for cik, tk in new:
        new_by_cik.setdefault(cik, []).append(tk)
    consumed_gone, consumed_new = set(), set()
    for cik in set(gone_by_cik) & set(new_by_cik):
        # Pair in order; ambiguous many-to-many pairs are still reported as
        # SYMBOL_CHANGED with both lists visible in the row.
        for old_tk, new_tk in zip(sorted(gone_by_cik[cik]), sorted(new_by_cik[cik])):
            row_c = c.loc[(cik, new_tk)]
            row_p = p.loc[(cik, old_tk)]
            events.append({
                "event": "SYMBOL_CHANGED", "cik": cik, "ticker": new_tk,
                "name": row_c["name"], "exchange": row_c["exchange"],
                "prev_ticker": old_tk, "prev_name": row_p["name"], "prev_exchange": row_p["exchange"],
            })
            consumed_gone.add((cik, old_tk))
            consumed_new.add((cik, new_tk))

    for cik, tk in gone:
        if (cik, tk) in consumed_gone:
            continue
        row = p.loc[(cik, tk)]
        events.append({
            "event": "DELISTED_FROM_MAP", "cik": cik, "ticker": tk,
            "name": row["name"], "exchange": row["exchange"],
            "prev_ticker": tk, "prev_name": row["name"], "prev_exchange": row["exchange"],
        })
    for cik, tk in new:
        if (cik, tk) in consumed_new:
            continue
        row = c.loc[(cik, tk)]
        events.append({
            "event": "LISTED", "cik": cik, "ticker": tk,
            "name": row["name"], "exchange": row["exchange"],
            "prev_ticker": "", "prev_name": "", "prev_exchange": "",
        })
    for cik, tk in both:
        rp, rc = p.loc[(cik, tk)], c.loc[(cik, tk)]
        if rp["name"] != rc["name"]:
            events.append({
                "event": "NAME_CHANGED", "cik": cik, "ticker": tk,
                "name": rc["name"], "exchange": rc["exchange"],
                "prev_ticker": tk, "prev_name": rp["name"], "prev_exchange": rp["exchange"],
            })
        if rp["exchange"] != rc["exchange"] and rp["exchange"] and rc["exchange"]:
            events.append({
                "event": "EXCHANGE_CHANGED", "cik": cik, "ticker": tk,
                "name": rc["name"], "exchange": rc["exchange"],
                "prev_ticker": tk, "prev_name": rp["name"], "prev_exchange": rp["exchange"],
            })
    out = pd.DataFrame(events, columns=EVENT_COLUMNS[:8])
    return out.sort_values(["event", "cik", "ticker"], kind="stable").reset_index(drop=True)


def events_over_history(name: str = "tickers", *, root: str = DEFAULT_ROOT) -> pd.DataFrame:
    """Concatenate diffs across every consecutive pair of stored snapshots."""
    snaps = snapshots_for(name, root=root)
    frames = []
    for a, b in zip(snaps, snaps[1:]):
        ev = diff_frames(load_snapshot(root, a["path"]), load_snapshot(root, b["path"]))
        ev["from_captured_at"] = a["captured_at"]
        ev["to_captured_at"] = b["captured_at"]
        ev["from_digest"] = a["digest"]
        ev["to_digest"] = b["digest"]
        frames.append(ev)
    if not frames:
        return pd.DataFrame(columns=EVENT_COLUMNS)
    return pd.concat(frames, ignore_index=True)[EVENT_COLUMNS]
