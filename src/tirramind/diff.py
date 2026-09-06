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
    cols = ["cik", "ticker", "name", "exchange"]
    m = prev[cols].merge(curr[cols], on=["cik", "ticker"], how="outer",
                         suffixes=("_p", "_c"), indicator=True)
    gone = m[m["_merge"] == "left_only"]
    new = m[m["_merge"] == "right_only"]
    both = m[m["_merge"] == "both"]

    # Symbol changes: a CIK that lost a ticker and gained one in the same step.
    g = gone.sort_values("ticker").groupby("cik")["ticker"].apply(list)
    n = new.sort_values("ticker").groupby("cik")["ticker"].apply(list)
    pairs = []
    for cik in g.index.intersection(n.index):
        pairs.extend((cik, o, w) for o, w in zip(g[cik], n[cik]))
    consumed_gone = {(c, o) for c, o, _ in pairs}
    consumed_new = {(c, w) for c, _, w in pairs}

    frames = []
    if pairs:
        pp = pd.DataFrame(pairs, columns=["cik", "prev_ticker", "ticker"])
        pp = pp.merge(gone[["cik", "ticker", "name_p", "exchange_p"]].rename(columns={"ticker": "prev_ticker"}),
                      on=["cik", "prev_ticker"]).merge(new[["cik", "ticker", "name_c", "exchange_c"]], on=["cik", "ticker"])
        frames.append(pd.DataFrame({"event": "SYMBOL_CHANGED", "cik": pp.cik, "ticker": pp.ticker,
                                    "name": pp.name_c, "exchange": pp.exchange_c, "prev_ticker": pp.prev_ticker,
                                    "prev_name": pp.name_p, "prev_exchange": pp.exchange_p}))
    gk = gone[~gone.set_index(["cik", "ticker"]).index.isin(list(consumed_gone))]
    frames.append(pd.DataFrame({"event": "DELISTED_FROM_MAP", "cik": gk.cik, "ticker": gk.ticker,
                                "name": gk.name_p, "exchange": gk.exchange_p, "prev_ticker": gk.ticker,
                                "prev_name": gk.name_p, "prev_exchange": gk.exchange_p}))
    nk = new[~new.set_index(["cik", "ticker"]).index.isin(list(consumed_new))]
    frames.append(pd.DataFrame({"event": "LISTED", "cik": nk.cik, "ticker": nk.ticker,
                                "name": nk.name_c, "exchange": nk.exchange_c, "prev_ticker": "",
                                "prev_name": "", "prev_exchange": ""}))
    nc = both[both.name_p != both.name_c]
    frames.append(pd.DataFrame({"event": "NAME_CHANGED", "cik": nc.cik, "ticker": nc.ticker,
                                "name": nc.name_c, "exchange": nc.exchange_c, "prev_ticker": nc.ticker,
                                "prev_name": nc.name_p, "prev_exchange": nc.exchange_p}))
    xc = both[(both.exchange_p != both.exchange_c) & both.exchange_p.ne("") & both.exchange_c.ne("")]
    frames.append(pd.DataFrame({"event": "EXCHANGE_CHANGED", "cik": xc.cik, "ticker": xc.ticker,
                                "name": xc.name_c, "exchange": xc.exchange_c, "prev_ticker": xc.ticker,
                                "prev_name": xc.name_p, "prev_exchange": xc.exchange_p}))
    out = pd.concat([f for f in frames if len(f)], ignore_index=True) if any(len(f) for f in frames) \
        else pd.DataFrame(columns=EVENT_COLUMNS[:8])
    out = out[EVENT_COLUMNS[:8]].astype(str)
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


# -- honesty layer ------------------------------------------------------------
SUSPECT_REMOVALS = 1500   # a step that drops this many tickers is a capture artefact, not the market


def annotate(events: pd.DataFrame) -> pd.DataFrame:
    """Add the columns that separate real delistings from artefacts:

    * ``suspect``      the step removed >= SUSPECT_REMOVALS tickers (partial or
                       format-shifted capture); every event in that step is flagged.
    * ``relisted_at``  for DELISTED_FROM_MAP, when the same (cik, ticker) next
                       appeared again; '' if never. 85% of raw removals re-appear.
    * ``cosmetic``     NAME_CHANGED where only case/punctuation differs.
    """
    ev = events.copy()
    if ev.empty:
        for c in ("suspect", "relisted_at", "cosmetic"):
            ev[c] = pd.Series(dtype=object)
        return ev
    removals = ev[ev.event.eq("DELISTED_FROM_MAP")].groupby("to_captured_at").size()
    bad_steps = set(removals[removals >= SUSPECT_REMOVALS].index)
    ev["suspect"] = ev["to_captured_at"].isin(bad_steps)

    d = ev[ev.event.eq("DELISTED_FROM_MAP")][["cik", "ticker", "to_captured_at"]].reset_index()
    l = ev[ev.event.eq("LISTED")][["cik", "ticker", "to_captured_at"]].rename(columns={"to_captured_at": "at"})
    m = d.merge(l, on=["cik", "ticker"], how="left")
    m = m[m["at"].notna() & (m["at"] > m["to_captured_at"])]
    first = m.groupby("index")["at"].min()
    ev["relisted_at"] = ""
    ev.loc[first.index, "relisted_at"] = first.values

    def _norm(s):
        return s.str.lower().str.replace(r"[^a-z0-9]", "", regex=True)
    nc = ev.event.eq("NAME_CHANGED")
    ev["cosmetic"] = False
    ev.loc[nc, "cosmetic"] = (_norm(ev.loc[nc, "name"]) == _norm(ev.loc[nc, "prev_name"])).values
    return ev


def permanent_removals(annotated: pd.DataFrame) -> pd.DataFrame:
    """DELISTED_FROM_MAP events that are neither suspect nor re-listed."""
    a = annotated
    return a[a.event.eq("DELISTED_FROM_MAP") & ~a.suspect & a.relisted_at.eq("")].reset_index(drop=True)
