"""The gate. A run that captured nothing on a business day fails red.

Green-with-zero-rows has bitten this owner four separate times. Exit codes
of the collectors are not evidence; the ledgers are.
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta, timezone

from .ledger import DEFAULT_ROOT as LEDGER_ROOT, read as read_ledger
from .store import DEFAULT_ROOT as SNAP_ROOT, read_index


def is_business_day(d: date) -> bool:
    return d.weekday() < 5


def check(*, snap_root: str = SNAP_ROOT, ledger_root: str = LEDGER_ROOT, today: date | None = None) -> list[str]:
    today = today or datetime.now(timezone.utc).date()
    problems: list[str] = []

    idx = read_index(snap_root)
    todays = [r for r in idx if r["name"] == "tickers" and r["captured_at"].startswith(str(today))]
    if not todays:
        problems.append("no ticker snapshot attempted today")
    elif all(r["status"] == "fail" for r in todays):
        problems.append("every ticker snapshot today failed: " + "; ".join(str(r["error"]) for r in todays))

    f = read_ledger("filings", root=ledger_root)
    if f.empty:
        problems.append("filings ledger is empty")
    else:
        recent = f[f["filed_at"] >= str(today - timedelta(days=7))]
        if is_business_day(today) and len(recent) == 0:
            problems.append(f"zero delisting-related filings in the last 7 days (ledger has {len(f)} rows)")
    return problems


if __name__ == "__main__":
    p = check()
    if p:
        print("VERIFY FAILED:\n  " + "\n  ".join(p))
        sys.exit(1)
    print("verify ok")
