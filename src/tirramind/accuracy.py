"""C4: the accuracy table for the 144 -> 4 ledger, with honest uncertainty.

Form 144 notices are not independent observations: one insider files
several, several insiders at one issuer file in the same week, and a whole
sector sells into the same window. So every rate here carries

* ``n``          nominal count,
* ``n_clusters`` distinct issuer-weeks,
* ``n_eff``      design-effect effective sample size, n / (1 + (m-1)·ICC),
* a cluster-bootstrap CI: resample issuer-weeks with replacement, never rows.

The CI must widen when clusters are merged; the test asserts it.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

HORIZONS = (30, 60, 90)


def cluster_key(df: pd.DataFrame) -> pd.Series:
    wk = pd.to_datetime(df["notice_date"]).dt.to_period("W").astype(str)
    return df["issuer_cik"].astype(str) + ":" + wk


def icc_binary(y: np.ndarray, g: np.ndarray) -> float:
    """ANOVA-style intraclass correlation for a binary outcome."""
    df = pd.DataFrame({"y": y, "g": g})
    grp = df.groupby("g")["y"]
    k = grp.ngroups
    n = len(df)
    if k < 2 or n <= k:
        return 0.0
    m = grp.size().values.astype(float)
    n0 = (n - (m ** 2).sum() / n) / (k - 1)
    grand = df["y"].mean()
    msb = (m * (grp.mean().values - grand) ** 2).sum() / (k - 1)
    msw = ((df["y"] - grp.transform("mean")) ** 2).sum() / (n - k)
    if msb + (n0 - 1) * msw <= 0:
        return 0.0
    return float(max(0.0, (msb - msw) / (msb + (n0 - 1) * msw)))


def effective_n(y: np.ndarray, g: np.ndarray) -> tuple[int, int, float]:
    n = len(y)
    k = len(set(g))
    if n == 0:
        return 0, 0, 0.0
    m_bar = n / k
    rho = icc_binary(y, g)
    deff = 1.0 + (m_bar - 1.0) * rho
    return n, k, float(n / deff)


def cluster_bootstrap(stat_fn, df: pd.DataFrame, g: pd.Series, *, n_boot: int = 1000,
                      conf: float = 0.9, seed: int = 7) -> tuple[float, float, float]:
    rng = np.random.default_rng(seed)
    groups = {k: v.index.values for k, v in df.groupby(g)}
    keys = list(groups)
    point = float(stat_fn(df))
    if len(keys) < 2:
        return point, float("nan"), float("nan")
    boots = np.empty(n_boot)
    for b in range(n_boot):
        pick = rng.choice(len(keys), size=len(keys), replace=True)
        idx = np.concatenate([groups[keys[i]] for i in pick])
        boots[b] = stat_fn(df.loc[idx])
    a = (1 - conf) / 2
    return point, float(np.quantile(boots, a)), float(np.quantile(boots, 1 - a))


def accuracy_table(links: pd.DataFrame, *, n_boot: int = 1000, seed: int = 7) -> pd.DataFrame:
    """Rows: (segment, horizon) -> P(any sale within horizon) with CI, plus
    executed-fraction median, n, n_clusters, n_eff. Segments: all, by
    relationship, by match_method."""
    L = links.copy()
    L = L[L["notice_date"].ne("")]
    if "window_complete" in L:
        L = L[L["window_complete"]]
    L["g"] = cluster_key(L)
    segments = [("all", L)]
    for rel, sub in L.groupby("relationship"):
        if len(sub) >= 20:
            segments.append((f"relationship={rel}", sub))
    for mm, sub in L.groupby("match_method"):
        segments.append((f"match={mm}", sub))

    rows = []
    for name, sub in segments:
        for h in HORIZONS:
            hit = ((sub["days_to_first_sale"] >= 0) & (sub["days_to_first_sale"] <= h)).astype(float)
            n, k, neff = effective_n(hit.values, sub["g"].values)
            tmp = sub.assign(hit=hit)
            p, lo, hi = cluster_bootstrap(lambda d: d["hit"].mean(), tmp, tmp["g"], n_boot=n_boot, seed=seed)
            rows.append({"segment": name, "horizon_days": h, "p_executed": p, "ci_lo": lo, "ci_hi": hi,
                         "n": n, "n_clusters": k, "n_eff": round(neff, 1),
                         "median_executed_fraction": float(sub["executed_fraction"].median())})
    return pd.DataFrame(rows)
