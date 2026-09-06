"""Append-only JSONL ledgers keyed by a unique field.

A ledger row is never edited. Re-appending a key that already exists is a
no-op, so daily runs can safely overlap their date windows. A correction is
a new row carrying ``supersedes=<old key>``.
"""

from __future__ import annotations

import json
import os

import pandas as pd

DEFAULT_ROOT = os.path.join(os.getcwd(), "data", "ledgers")


def _path(name: str, root: str) -> str:
    return os.path.join(root, f"{name}.jsonl")


def read(name: str, *, root: str = DEFAULT_ROOT) -> pd.DataFrame:
    p = _path(name, root)
    if not os.path.exists(p):
        return pd.DataFrame()
    with open(p, encoding="utf-8") as fh:
        rows = [json.loads(line) for line in fh if line.strip()]
    return pd.DataFrame(rows)


def keys(name: str, key: str, *, root: str = DEFAULT_ROOT) -> set:
    df = read(name, root=root)
    return set(df[key]) if len(df) and key in df else set()


def append(name: str, rows: list[dict], key: str, *, root: str = DEFAULT_ROOT) -> int:
    """Append rows whose ``key`` is not already present. Returns count added."""
    os.makedirs(root, exist_ok=True)
    seen = keys(name, key, root=root)
    added = 0
    with open(_path(name, root), "a", encoding="utf-8") as fh:
        for r in rows:
            k = r[key]
            if k in seen:
                continue
            fh.write(json.dumps(r, sort_keys=True, default=str) + "\n")
            seen.add(k)
            added += 1
    return added
