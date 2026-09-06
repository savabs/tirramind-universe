"""D1: the daily job. Runs every collector for a trailing window, rebuilds
the derived outputs, and prints row counts for every step so the log is
evidence. Exit status is not — ``verify.py`` is the gate."""

from __future__ import annotations

from datetime import date, timedelta

from .build import build
from .filings import collect
from .sec import SecClient
from .store import record_failure
from .tickers import snapshot_current


def main(lookback_days: int = 5) -> None:
    client = SecClient(cache_dir=".cache/sec")
    try:
        snapshot_current(client)
    except Exception as e:  # noqa: BLE001
        record_failure("tickers", f"{type(e).__name__}: {e}")
        print(f"tickers FAIL {type(e).__name__}: {str(e)[:120]}")
    today = date.today()
    counts = collect(client, today - timedelta(days=lookback_days), today)
    print("filings  " + "  ".join(f"{k}={v}" for k, v in counts.items()))
    stats = build()
    print(f"build    events={stats['events']} delistings={stats['delistings']} "
          f"unknown={stats['cause_shares']['UNKNOWN']:.1%} filings={stats['filings']}")


if __name__ == "__main__":
    main()
