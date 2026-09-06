import numpy as np
import pandas as pd

from tirramind.accuracy import accuracy_table, cluster_bootstrap, effective_n


def _links(n_issuers, per_issuer, p_issuer_spread, seed=1):
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n_issuers):
        p = float(np.clip(0.5 + rng.normal(0, p_issuer_spread), 0.05, 0.95))
        for j in range(per_issuer):
            hit = rng.random() < p
            rows.append({"issuer_cik": f"{i:010d}", "notice_date": "2024-03-04",
                         "relationship": "Officer", "match_method": "cik",
                         "days_to_first_sale": int(rng.integers(0, 30)) if hit else -1,
                         "executed_fraction": 1.0 if hit else 0.0})
    return pd.DataFrame(rows)


def test_effective_n_shrinks_with_clustering():
    weak = _links(50, 4, 0.0)      # no issuer effect
    strong = _links(50, 4, 0.4)    # big issuer effect
    hit_w = (weak.days_to_first_sale >= 0).astype(float).values
    hit_s = (strong.days_to_first_sale >= 0).astype(float).values
    g = (weak.issuer_cik + ":2024-03").values
    n, k, neff_w = effective_n(hit_w, g)
    _, _, neff_s = effective_n(hit_s, g)
    assert n == 200 and k == 50
    assert neff_s < neff_w <= 200 + 1e-9
    assert neff_s < 120


def test_cluster_ci_wider_than_naive_when_issuers_share_an_effect():
    df = _links(60, 5, 0.4)
    df["hit"] = (df.days_to_first_sale >= 0).astype(float)
    by_issuer = df.issuer_cik
    by_row = pd.Series(range(len(df)), index=df.index).astype(str)   # every row its own cluster = iid
    _, lo_c, hi_c = cluster_bootstrap(lambda d: d.hit.mean(), df, by_issuer, n_boot=400)
    _, lo_r, hi_r = cluster_bootstrap(lambda d: d.hit.mean(), df, by_row, n_boot=400)
    assert (hi_c - lo_c) > (hi_r - lo_r)


def test_table_shape_and_determinism():
    df = _links(30, 3, 0.2)
    t1 = accuracy_table(df, n_boot=100)
    t2 = accuracy_table(df, n_boot=100)
    assert set(t1.horizon_days) == {30, 60, 90}
    assert (t1.n_eff <= t1.n).all() and (t1.n_clusters <= t1.n).all()
    assert (t1.ci_lo <= t1.p_executed).all() and (t1.p_executed <= t1.ci_hi).all()
    pd.testing.assert_frame_equal(t1, t2)
