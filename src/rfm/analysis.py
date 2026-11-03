"""Python analysis steps that run after the SQL marts (``python run.py --steps analysis``).

Outputs (data/marts/ unless noted):
    revenue_at_risk.parquet        "if we do nothing" 90-day projection per segment (composition-adjusted)
    regression_to_mean.parquet     why Champions show a gap: realisation by M score in the backtest
    channel_value.parquet          12-month value by channel at equal order counts (gross demand)
    channel_forward.parquet        next-90-day behaviour by 12-month channel at equal order counts (backtest)
    channel_order_aov.parquet      AOV of store vs online orders, incl. the same omnichannel customers
    channel_audience.parquet       segment x 12-month channel x newsletter counts (the Q3 audience)
    threshold_sensitivity.parquet  segment sizes with each threshold group moved -25% / +25%
    value_grid.parquet             segment x value tier customers and revenue
    order_ladder.parquet           chance of an (n+1)-th order given n orders
    campaign_inputs.parquet        per-audience inputs for the economics
    campaign_economics.parquet     base-case economics of every arm
    campaign_scenarios.parquet     pessimistic / base / optimistic totals
    campaign_budget.parquet        the budget ask by cost type
    holdout_power.parquet          minimum detectable effect per audience and holdout share
    kmeans_*.parquet               K-Means comparison
    app_*.parquet                  slim id-free tables for the dashboard
    reports/metrics.json           every headline number quoted in README / docs
"""

from __future__ import annotations

import json
import math
import time
from typing import Callable

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import adjusted_rand_score, silhouette_score
from sklearn.preprocessing import StandardScaler

from . import campaign, power
from .config import ROOT, get_paths, load_config
from .segments import SEGMENT_ORDER, Thresholds, assign_segments, quantile_edges
from .sqlrun import query

Z95 = 1.959964
CELL = ["r_score", "f_score", "m_score", "channel_12m"]


# --------------------------------------------------------------------------- helpers
def _marts(name: str, **kw) -> pd.DataFrame:
    return pd.read_parquet(get_paths().marts / name, **kw)


def _save(df: pd.DataFrame, name: str) -> None:
    df.to_parquet(get_paths().marts / name, index=False)


def _ratio_ci(y: np.ndarray, x: np.ndarray) -> tuple[float, float, float]:
    """Ratio of sums sum(y)/sum(x) with a delta-method 95% CI (customer-level sampling noise only)."""
    n = len(y)
    r = y.sum() / x.sum()
    resid = y - r * x
    se = math.sqrt(resid.var(ddof=1) / n) / x.mean()
    return r, r - Z95 * se, r + Z95 * se


def _cell_ratios(bt: pd.DataFrame, min_n: int = 30) -> pd.DataFrame:
    g = bt.groupby(CELL, observed=True).agg(n=("purchased_next_90d", "size"), rev=("revenue_next_90d_cents", "sum"),
                                            rr=("run_rate_90d_cents", "sum"), buy=("purchased_next_90d", "mean"))
    g = g[(g.n >= min_n) & (g.rr > 0)]
    g["ratio"] = g["rev"] / g["rr"]
    return g[["ratio", "buy", "n"]].rename(columns={"n": "n_backtest"})


# --------------------------------------------------------------------------- revenue at risk
def revenue_at_risk() -> pd.DataFrame:
    """What today's segments are expected to spend in the next 90 days if we do nothing.

    usual pace (run-rate) = 12-month revenue x 90/365
    expected (BAU)        = usual pace x realisation (actual 90-day revenue / usual pace) observed for
                            customers who looked the same at a backtest date
    gap vs usual pace     = usual pace - expected. Part of it is natural slowdown (regression to the
                            mean after a strong 12 months), so it is NOT the amount a campaign can win back.

    Realisation is direct-standardised: computed per cell of R x F x M score x 12-month channel in the
    backtest and re-weighted to today's mix (today's At Risk is more online-only and largely last bought
    during the spring-2020 lockdown, unlike either backtest). Scenarios:
        base         season-matched backtest (2019-09-22), composition-adjusted
        recent       last-quarter backtest (2020-06-24, reopening summer), composition-adjusted
        pessimistic  per cell, the lower of the two backtests
    Lost has no usual pace: its expected revenue is reactivation revenue, re-weighted by how long
    customers have been away (the 2019 backtest cannot baseline Lost: only 3k customers).
    """
    cfg = load_config()
    factor = cfg["snapshot"]["outcome_days"] / cfg["snapshot"]["lookback_days"]
    cur = _marts("customer_rfm.parquet", filters=[("snapshot_name", "==", "current")])
    cur = cur.assign(run_rate_90d_cents=cur["monetary_12m_cents"] * factor)
    out = _marts("customer_outcomes_90d.parquet")
    rows = []
    for seg in SEGMENT_ORDER:
        c = cur[cur.segment == seg]
        row = {"segment": seg, "customers": len(c), "revenue_12m_cu": c.monetary_12m_cu.sum(),
               "run_rate_90d_cu": c.run_rate_90d_cents.sum() / 100}
        cells_now = c.groupby(CELL, observed=True).agg(rr=("run_rate_90d_cents", "sum"), n=("customer_id", "size"))
        per_basis = {}
        for basis in ("seasonal", "recent"):
            b = out[(out.snapshot_name == f"backtest_{basis}") & (out.segment == seg)]
            row[f"backtest_customers_{basis}"] = len(b)
            if not len(b):
                continue
            row[f"repurchase_rate_{basis}"] = b.purchased_next_90d.mean()
            if row["run_rate_90d_cu"] > 0 and b.run_rate_90d_cents.sum() > 0:
                r, lo, hi = _ratio_ci(b.revenue_next_90d_cents.to_numpy(float), b.run_rate_90d_cents.to_numpy(float))
                row[f"realisation_raw_{basis}"], row[f"realisation_ci_lo_{basis}"], row[f"realisation_ci_hi_{basis}"] = r, lo, hi
                cr = _cell_ratios(b)
                j = cells_now.join(cr, how="left")
                j["ratio"] = j["ratio"].fillna(r)
                j["buy"] = j["buy"].fillna(b.purchased_next_90d.mean())
                per_basis[basis] = j
                row[f"realisation_{basis}"] = float((j.rr * j.ratio).sum() / j.rr.sum())
                row[f"repurchase_rate_adj_{basis}"] = float((j.n * j.buy).sum() / j.n.sum())
                row[f"cell_coverage_{basis}"] = float(j.rr[j.index.isin(cr.index)].sum() / j.rr.sum())
        if len(per_basis) == 2:
            j = per_basis["seasonal"].join(per_basis["recent"][["ratio"]], rsuffix="_recent")
            row["realisation_pessimistic"] = float((j.rr * np.minimum(j.ratio, j.ratio_recent)).sum() / j.rr.sum())
        rows.append(row)
    df = pd.DataFrame(rows)

    # Lost: reactivation revenue by time away (recent backtest, 90-day recency buckets)
    lost_now = cur[cur.segment == "Lost"]
    lost_bt = out[(out.snapshot_name == "backtest_recent") & (out.segment == "Lost")]
    bins = [365, 450, 540, 630, 10_000]
    rate = lost_bt.groupby(pd.cut(lost_bt.recency_days, bins, right=False), observed=True).agg(
        buy=("purchased_next_90d", "mean"), rev=("revenue_next_90d_cents", "mean"))
    n_now = lost_now.groupby(pd.cut(lost_now.recency_days, bins, right=False), observed=True).size()
    lost_rev = float((n_now * rate["rev"]).sum() / 100)
    lost_buyers = float((n_now * rate["buy"]).sum())

    for basis in ("seasonal", "recent", "pessimistic"):
        df[f"expected_90d_cu_{basis}"] = df["run_rate_90d_cu"] * df.get(f"realisation_{basis}", np.nan)
    df.loc[df.segment == "Lost", ["expected_90d_cu_seasonal", "expected_90d_cu_recent", "expected_90d_cu_pessimistic"]] = lost_rev
    df["base_basis"] = np.where(df["backtest_customers_seasonal"].fillna(0) < 10_000, "recent", "seasonal")
    df["expected_90d_cu_base"] = np.where(df.base_basis == "recent", df["expected_90d_cu_recent"], df["expected_90d_cu_seasonal"])
    df["realisation_base"] = np.where(df.base_basis == "recent", df.get("realisation_recent"), df.get("realisation_seasonal"))
    rate_base = np.where(df.base_basis == "recent", df.get("repurchase_rate_adj_recent"), df.get("repurchase_rate_adj_seasonal"))
    df["repurchase_rate_base"] = np.where(np.isnan(rate_base.astype(float)), df.get("repurchase_rate_recent"), rate_base)
    df.loc[df.segment == "Lost", "repurchase_rate_base"] = lost_buyers / len(lost_now)
    df["expected_buyers_base"] = df["customers"] * df["repurchase_rate_base"]
    df["expected_non_buyers_base"] = df["customers"] - df["expected_buyers_base"]
    has_pace = df["run_rate_90d_cu"] > 0
    for basis in ("base", "seasonal", "recent", "pessimistic"):
        df[f"gap_90d_cu_{basis}"] = (df["run_rate_90d_cu"] - df[f"expected_90d_cu_{basis}"]).where(has_pace)
    gaps = df[["gap_90d_cu_seasonal", "gap_90d_cu_recent", "gap_90d_cu_pessimistic"]]
    df["gap_90d_cu_low"] = gaps.min(axis=1)
    df["gap_90d_cu_high"] = gaps.max(axis=1)
    df["gap_pct_of_pace"] = df["gap_90d_cu_base"] / df["run_rate_90d_cu"]
    df["gap_ci_lo"] = df["run_rate_90d_cu"] * (1 - df.get("realisation_ci_hi_seasonal")) - (
        df["run_rate_90d_cu"] * (df.get("realisation_raw_seasonal") - df.get("realisation_seasonal"))).fillna(0)
    df["gap_ci_hi"] = df["run_rate_90d_cu"] * (1 - df.get("realisation_ci_lo_seasonal")) - (
        df["run_rate_90d_cu"] * (df.get("realisation_raw_seasonal") - df.get("realisation_seasonal"))).fillna(0)
    return df


def regression_to_mean() -> pd.DataFrame:
    """Realisation by M score inside each segment (season-matched backtest): top spenders fall back,
    lower spenders catch up. This is why Champions show a 'gap' that is not churn."""
    out = _marts("customer_outcomes_90d.parquet", filters=[("snapshot_name", "==", "backtest_seasonal")])
    g = out[out.run_rate_90d_cents > 0].groupby(["segment", "m_score"]).agg(
        customers=("customer_id", "size"), revenue=("revenue_next_90d_cents", "sum"), run_rate=("run_rate_90d_cents", "sum"))
    g["realisation"] = g["revenue"] / g["run_rate"]
    return g.reset_index()


# --------------------------------------------------------------------------- channel
_BAND = """CASE WHEN frequency_12m = 1 THEN '1 order' WHEN frequency_12m = 2 THEN '2 orders'
                WHEN frequency_12m <= 4 THEN '3-4 orders' WHEN frequency_12m <= 9 THEN '5-9 orders'
                ELSE '10+ orders' END"""


def channel_tables(online_return_rate: float = 0.25, store_return_rate: float = 0.08) -> dict[str, pd.DataFrame]:
    """Store vs online, with the channel defined on the 12 months before each snapshot (no leakage).

    Revenue is gross demand: the data has no returns. The returns haircut (25% online / 8% store)
    is an illustrative assumption to show how sensitive the comparison is, not a measured rate.
    """
    value = query(f"""
        SELECT {_BAND} AS order_band, channel_12m AS channel, COUNT(*) AS customers,
               AVG(monetary_12m_cu) AS revenue_per_customer_cu,
               SUM(monetary_12m_cu) / SUM(frequency_12m) AS aov_cu,
               AVG((online_revenue_12m_cents * {1 - online_return_rate}
                    + (monetary_12m_cents - online_revenue_12m_cents) * {1 - store_return_rate}) / 100.0) AS revenue_net_of_returns_cu
        FROM 'data/marts/customer_rfm.parquet'
        WHERE snapshot_name = 'current' AND frequency_12m > 0 AND NOT is_excluded
        GROUP BY ALL ORDER BY ALL""")
    forward = query(f"""
        SELECT snapshot_name, {_BAND} AS order_band, channel_12m AS channel, COUNT(*) AS customers,
               AVG(purchased_next_90d::INT) AS repurchase_rate_90d,
               AVG(revenue_next_90d_cents) / 100.0 AS revenue_next_90d_per_customer_cu
        FROM 'data/marts/customer_outcomes_90d.parquet'
        WHERE frequency_12m > 0 AND segment <> 'Review List'
        GROUP BY ALL ORDER BY ALL""")
    aov = query("""
        WITH cur AS (SELECT customer_id, channel_12m FROM 'data/marts/customer_rfm.parquet'
                     WHERE snapshot_name = 'current' AND frequency_12m > 0 AND NOT is_excluded),
        o AS (SELECT * FROM 'data/marts/fct_orders.parquet' WHERE DATE '2020-09-22' - order_date < 365)
        SELECT CASE WHEN c.channel_12m = 'Omnichannel' THEN 'Omnichannel customers' ELSE 'All customers' END AS customers_group,
               o.channel AS order_channel, COUNT(*) AS orders, SUM(o.revenue_cents) / 100.0 / COUNT(*) AS aov_cu,
               SUM(o.n_units) / COUNT(*) AS units_per_order
        FROM o JOIN cur c USING (customer_id)
        WHERE c.channel_12m = 'Omnichannel'
        GROUP BY ALL
        UNION ALL
        SELECT 'All customers', o.channel, COUNT(*), SUM(o.revenue_cents) / 100.0 / COUNT(*), SUM(o.n_units) / COUNT(*)
        FROM o JOIN cur c USING (customer_id) GROUP BY ALL
        ORDER BY 1, 2""")
    audience = query("""
        SELECT segment, channel_12m AS channel, COUNT(*) AS customers,
               SUM(is_newsletter_subscriber::INT) AS newsletter_subscribers,
               SUM(monetary_12m_cu) AS revenue_12m_cu
        FROM 'data/marts/customer_rfm.parquet'
        WHERE snapshot_name = 'current'
        GROUP BY ALL ORDER BY ALL""")
    return {"channel_value": value, "channel_forward": forward, "channel_order_aov": aov, "channel_audience": audience}


# --------------------------------------------------------------------------- thresholds and value
def threshold_sensitivity(step: float = 0.25) -> pd.DataFrame:
    """Segment sizes when each group of thresholds moves -25% / +25% (one group at a time)."""
    cur = _marts("app_customers.parquet")
    th = Thresholds.from_config()
    variants = {"Default": th}
    for sign, lab in ((-1, "-25%"), (1, "+25%")):
        f = 1 + sign * step
        variants[f"Recency cut-offs {lab}"] = th.with_changes(
            r5_max_days=round(th.r5_max_days * f), r4_max_days=round(th.r4_max_days * f),
            r3_max_days=round(th.r3_max_days * f), r2_max_days=round(th.r2_max_days * f))
        variants[f"Frequency cut-offs {lab}"] = th.with_changes(
            f5_min_orders=max(2, round(th.f5_min_orders * f)), f4_min_orders=max(2, round(th.f4_min_orders * f)),
            f3_min_orders=max(2, round(th.f3_min_orders * f)))
        variants[f"Monetary cut-offs {lab}"] = th.with_changes(
            m5_min_cu=th.m5_min_cu * f, m4_min_cu=th.m4_min_cu * f, m3_min_cu=th.m3_min_cu * f, m2_min_cu=th.m2_min_cu * f)
    base = assign_segments(cur, th).value_counts()
    rows = []
    for name, t in variants.items():
        vc = assign_segments(cur, t).value_counts()
        for seg in SEGMENT_ORDER:
            rows.append({"variant": name, "segment": seg, "customers": int(vc.get(seg, 0)),
                         "change_vs_default": int(vc.get(seg, 0) - base.get(seg, 0)),
                         "pct_change": (vc.get(seg, 0) - base.get(seg, 0)) / max(base.get(seg, 1), 1)})
    return pd.DataFrame(rows)


def value_grid() -> pd.DataFrame:
    return query("""
        SELECT segment, value_tier, COUNT(*) AS customers, SUM(monetary_12m_cu) AS revenue_12m_cu
        FROM 'data/marts/customer_rfm.parquet' WHERE snapshot_name = 'current'
        GROUP BY ALL ORDER BY ALL""")


def order_ladder() -> pd.DataFrame:
    """P(at least n+1 orders | at least n orders) within 12 months of the first order.

    Two cohorts, both with a full 12-month follow-up:
      'first order 2018-09-20 to 2019-09-22'  everyone whose first order *in the data* is in year 1
                                              (includes existing customers: left-censoring)
      'new: first order 2019-03-01 to 2019-09-22' no order in the 5+ months before, so mostly
                                              genuinely new customers
    """
    return query("""
        WITH first AS (
            SELECT customer_id, first_order_date,
                   CASE WHEN first_order_date >= DATE '2019-03-01'
                        THEN 'new: first order 2019-03-01 to 2019-09-22' END AS clean_cohort
            FROM 'data/marts/dim_customers.parquet'
            WHERE has_orders AND NOT is_excluded AND first_order_date <= DATE '2019-09-22'
        ),
        n_orders AS (
            SELECT f.customer_id, f.clean_cohort, COUNT(*) AS orders_12m_after_first
            FROM first f
            JOIN 'data/marts/fct_orders.parquet' o
              ON o.customer_id = f.customer_id
             AND o.order_date >= f.first_order_date
             AND o.order_date <  f.first_order_date + 365
            GROUP BY 1, 2
        ),
        tagged AS (
            SELECT 'first order 2018-09-20 to 2019-09-22' AS cohort, orders_12m_after_first FROM n_orders
            UNION ALL
            SELECT clean_cohort, orders_12m_after_first FROM n_orders WHERE clean_cohort IS NOT NULL
        ),
        ladder AS (
            SELECT c.cohort, k AS orders,
                   (SELECT COUNT(*) FROM tagged t WHERE t.cohort = c.cohort AND t.orders_12m_after_first >= k) AS customers
            FROM (SELECT DISTINCT cohort FROM tagged) c, range(1, 11) r(k)
        )
        SELECT cohort, orders, customers,
               LEAD(customers) OVER (PARTITION BY cohort ORDER BY orders) / customers AS p_next_order
        FROM ladder ORDER BY cohort, orders
    """)


# --------------------------------------------------------------------------- power
def holdout_power(inputs: pd.DataFrame, shares=(0.05, 0.10, 0.15, 0.20, 0.30)) -> pd.DataFrame:
    """MDE per audience for a range of holdout shares, on the audience's experiment population."""
    cfg = load_config()["economics"]
    reach = campaign.audience_reach(campaign.plan_frame())
    rows = []
    for _, r in inputs.iterrows():
        pop = r["customers"] * (1.0 if reach.get(r["audience"], False) else r["newsletter_share"])
        for s in shares:
            n_c, n_t = pop * s, pop * (1 - s)
            rows.append({
                "audience": r["audience"], "audience_label": r["audience_label"], "segment": r["segment"],
                "holdout_share": s, "population": pop, "n_treat": n_t, "n_control": n_c, "baseline_rate": r["baseline_rate"],
                "mde_rate_pp": 100 * power.mde_rate(r["baseline_rate"], n_t, n_c, cfg["alpha"], cfg["power"]),
                "mde_revenue_cu": power.mde_mean(r["sd_revenue"], n_t, n_c, cfg["alpha"], cfg["power"]),
                "revenue_per_customer_cu": r["revenue_per_customer"],
            })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- k-means
def kmeans_comparison(log: Callable[[str], None] = print) -> dict:
    """K-Means on log-scaled R, F, M of 12-month-active customers, compared with the rules."""
    cfg = load_config()
    kcfg, seed = cfg["kmeans"], cfg["random_seed"]
    df = _marts("customer_rfm.parquet")
    cur = df[(df.snapshot_name == "current") & (df.frequency_12m > 0) & (~df.is_excluded)].reset_index(drop=True)
    feats = ["recency_days", "frequency_12m", "monetary_12m_cu"]
    X_raw = np.log1p(cur[feats].to_numpy(float))
    X = StandardScaler().fit(X_raw).transform(X_raw)

    rng = np.random.default_rng(seed)
    sample_idx = rng.choice(len(X), size=min(200_000, len(X)), replace=False)
    sil_idx = rng.choice(sample_idx, size=min(kcfg["silhouette_sample"], len(sample_idx)), replace=False)
    sel = []
    for k in kcfg["k_range"]:
        km = KMeans(n_clusters=k, n_init=4, random_state=seed).fit(X[sample_idx])
        sil = silhouette_score(X[sil_idx], km.predict(X[sil_idx]))
        sel.append({"k": k, "inertia": km.inertia_, "silhouette": sil})
        log(f"    k={k}: silhouette {sil:.3f}")
    sel = pd.DataFrame(sel)

    k = kcfg["k_final"]
    final = KMeans(n_clusters=k, n_init=10, random_state=seed).fit(X)
    order = pd.Series(cur["monetary_12m_cu"].to_numpy()).groupby(final.labels_).median().sort_values().index
    relabel = {old: new for new, old in enumerate(order, start=1)}
    labels = np.vectorize(relabel.get)(final.labels_)
    cur["cluster"] = labels

    prof = cur.groupby("cluster").agg(
        customers=("customer_id", "size"), median_recency_days=("recency_days", "median"),
        median_orders_12m=("frequency_12m", "median"), median_revenue_12m_cu=("monetary_12m_cu", "median"),
        revenue_12m_cu=("monetary_12m_cu", "sum")).reset_index()
    prof["pct_customers"] = prof["customers"] / prof["customers"].sum()
    prof["pct_revenue_12m"] = prof["revenue_12m_cu"] / prof["revenue_12m_cu"].sum()
    mix = cur.groupby("cluster")["segment"].value_counts(normalize=True)
    prof["n_segments_over_10pct"] = prof["cluster"].map(lambda c: int((mix.loc[c] >= 0.10).sum()))
    prof["main_rule_segments"] = prof["cluster"].map(
        lambda c: ", ".join(f"{s} {v:.0%}" for s, v in mix.loc[c].head(3).items()))

    ct = pd.crosstab(cur["cluster"], cur["segment"]).reset_index().melt(id_vars="cluster", var_name="segment", value_name="customers")
    ari_rules = adjusted_rand_score(cur["segment"], labels)
    alt = [KMeans(n_clusters=k, n_init=1, random_state=s).fit(X[sample_idx]).predict(X) for s in kcfg["stability_seeds"]]
    ari_seeds = [adjusted_rand_score(alt[0], a) for a in alt[1:]]
    prev = df[(df.snapshot_name == "backtest_recent") & (df.frequency_12m > 0) & (~df.is_excluded)]
    Xp_raw = np.log1p(prev[feats].to_numpy(float))
    sp = StandardScaler().fit(Xp_raw)
    km_prev = KMeans(n_clusters=k, n_init=10, random_state=seed).fit(sp.transform(Xp_raw))
    labels_prev_model = km_prev.predict(sp.transform(X_raw))
    switch = pd.crosstab(final.labels_, labels_prev_model).to_numpy()

    _save(sel, "kmeans_k_selection.parquet")
    _save(prof, "kmeans_profile.parquet")
    _save(ct, "kmeans_crosstab.parquet")
    top = prof.sort_values("pct_revenue_12m", ascending=False).iloc[0]
    mid = prof.sort_values("n_segments_over_10pct", ascending=False).iloc[0]
    return {
        "k_final": k, "n_customers": int(len(cur)),
        "silhouette_by_k": {int(r.k): round(float(r.silhouette), 4) for r in sel.itertuples()},
        "ari_vs_rules": round(float(ari_rules), 4),
        "ari_between_seeds_min": round(float(min(ari_seeds)), 4),
        "ari_refit_previous_quarter": round(float(adjusted_rand_score(final.labels_, labels_prev_model)), 4),
        "share_reassigned_by_refit": round(float(1 - switch.max(axis=1).sum() / switch.sum()), 4),
        "top_cluster_champion_share": round(float(mix.loc[top.cluster].get("Champions", 0)), 4),
        "mixed_cluster": int(mid.cluster), "mixed_cluster_pct_customers": round(float(mid.pct_customers), 4),
        "mixed_cluster_pct_revenue": round(float(mid.pct_revenue_12m), 4),
        "mixed_cluster_segments": mid.main_rule_segments,
    }


# --------------------------------------------------------------------------- small chart inputs
def price_points_table() -> pd.DataFrame:
    """Most common unit prices after x 590 (evidence that the scaling recovers retail prices)."""
    return query("""
        WITH p AS (SELECT unit_price_cents / 100.0 AS price_cu, SUM(units) AS units
                   FROM 'data/marts/fct_sales_lines.parquet' GROUP BY 1)
        SELECT price_cu, units, SUM(units) OVER () AS units_total FROM p ORDER BY units DESC LIMIT 30""")


def rf_grid() -> pd.DataFrame:
    """Recency score x Frequency score grid for 12-month-active customers (current snapshot)."""
    return query("""
        SELECT r_score, f_score, COUNT(*) AS customers, SUM(monetary_12m_cu) AS revenue_12m_cu
        FROM 'data/marts/customer_rfm.parquet'
        WHERE snapshot_name = 'current' AND frequency_12m > 0 AND NOT is_excluded
        GROUP BY ALL ORDER BY ALL""")


# --------------------------------------------------------------------------- app tables
def app_tables() -> None:
    """Slim, id-free copies of the customer tables for the dashboard (fast to load)."""
    df = _marts("customer_rfm.parquet")
    keep = ["recency_days", "tenure_days", "frequency_12m", "monetary_12m_cu", "is_excluded",
            "is_newsletter_subscriber", "channel_12m", "value_tier", "segment"]
    cur = df[df.snapshot_name == "current"][keep].copy()
    for c in ("channel_12m", "value_tier"):
        cur[c] = cur[c].astype("category")
    cur["segment"] = pd.Categorical(cur["segment"], SEGMENT_ORDER, ordered=True)
    for c in ("recency_days", "tenure_days", "frequency_12m"):
        cur[c] = cur[c].astype("int32")
    cur["monetary_12m_cu"] = cur["monetary_12m_cu"].astype("float32")
    _save(cur, "app_customers.parquet")

    out = _marts("customer_outcomes_90d.parquet")
    rfm_bt = df[df.snapshot_name != "current"][["snapshot_name", "customer_id", "is_excluded"]]
    bt = out.merge(rfm_bt, on=["snapshot_name", "customer_id"], how="left")
    bt = bt[["snapshot_name", "recency_days", "tenure_days", "frequency_12m", "monetary_12m_cu", "is_excluded",
             "segment", "purchased_next_90d", "revenue_next_90d_cents", "run_rate_90d_cents"]].copy()
    bt["snapshot_name"] = bt["snapshot_name"].astype("category")
    bt["segment"] = pd.Categorical(bt["segment"], SEGMENT_ORDER, ordered=True)
    bt["revenue_next_90d_cu"] = (bt.pop("revenue_next_90d_cents") / 100).astype("float32")
    bt["run_rate_90d_cu"] = (bt.pop("run_rate_90d_cents") / 100).astype("float32")
    for c in ("recency_days", "tenure_days", "frequency_12m"):
        bt[c] = bt[c].astype("int32")
    bt["monetary_12m_cu"] = bt["monetary_12m_cu"].astype("float32")
    _save(bt, "app_backtest.parquet")

    dim = _marts("dim_customers.parquet")
    ex = dim[dim.has_orders][["max_units_same_article", "max_units_per_order", "lifetime_purchase_days",
                             "lifetime_revenue_cents"]].copy()
    ex["lifetime_revenue_cu"] = (ex.pop("lifetime_revenue_cents") / 100).astype("float32")
    for c in ("max_units_same_article", "max_units_per_order", "lifetime_purchase_days"):
        ex[c] = ex[c].astype("int32")
    _save(ex, "app_exclusion.parquet")


# --------------------------------------------------------------------------- metrics
def _f(v, nd=4):
    if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
        return None
    return round(float(v), nd)


def build_metrics(km: dict, rar: pd.DataFrame, econ: pd.DataFrame, scen: pd.DataFrame, budget: pd.DataFrame,
                  pooled: dict, ch: dict[str, pd.DataFrame], ladder: pd.DataFrame, flow: pd.DataFrame,
                  rtm: pd.DataFrame, sens: pd.DataFrame, grid: pd.DataFrame) -> dict:
    cfg = load_config()
    prof = _marts("segment_profile.parquet").set_index("segment")
    dq = _marts("dq_checks.parquet")
    rec = _marts("reconciliation_checks.parquet")
    dim = query("""SELECT COUNT(*) AS customers, SUM(has_orders::INT) AS buyers, SUM(is_excluded::INT) AS excluded,
                          SUM(is_newsletter_subscriber::INT) AS newsletter FROM 'data/marts/dim_customers.parquet'""").iloc[0]
    rows_ = query("SELECT COUNT(*) AS n FROM 'data/staged/stg_transactions.parquet'").iloc[0]["n"]
    orders = query("SELECT COUNT(*) AS orders, SUM(revenue_cents)/100.0 AS revenue_cu FROM 'data/marts/fct_orders.parquet'").iloc[0]
    active = query("""SELECT COUNT(*) AS active, SUM(monetary_12m_cu) AS rev12, SUM(is_newsletter_subscriber::INT) AS subs
                      FROM 'data/marts/customer_rfm.parquet' WHERE snapshot_name='current' AND frequency_12m > 0""").iloc[0]
    r = rar.set_index("segment")

    def seg(name: str) -> dict:
        p, q = prof.loc[name], r.loc[name]
        return {
            "customers": int(p.customers), "pct_customers": _f(p.pct_customers), "revenue_12m_cu": _f(p.revenue_12m_cu, 0),
            "pct_revenue_12m": _f(p.pct_revenue_12m), "pct_revenue_2y": _f(p.pct_revenue_2y),
            "aov_12m_cu": _f(p.aov_12m_cu, 2), "aov_2y_cu": _f(p.aov_2y_cu, 2), "avg_orders_12m": _f(p.avg_orders_12m, 2),
            "avg_revenue_12m_cu": _f(p.avg_revenue_12m_cu, 1), "median_recency_days": _f(p.median_recency_days, 0),
            "median_days_between_orders": _f(p.median_days_between_orders, 1),
            "pct_online_only_12m": _f(p.pct_online_only_12m), "pct_omnichannel_12m": _f(p.pct_omnichannel_12m),
            "pct_online_only_2y": _f(p.pct_online_only_2y), "pct_newsletter": _f(p.pct_newsletter), "pct_vip": _f(p.pct_vip),
            "repurchase_rate_90d_base": _f(q.repurchase_rate_base), "repurchase_rate_90d_seasonal": _f(q.get("repurchase_rate_seasonal")),
            "repurchase_rate_90d_recent": _f(q.get("repurchase_rate_recent")),
            "run_rate_90d_cu": _f(q.run_rate_90d_cu, 0), "expected_90d_cu_base": _f(q.expected_90d_cu_base, 0),
            "expected_non_buyers_base": _f(q.expected_non_buyers_base, 0),
            "realisation_base": _f(q.realisation_base), "realisation_raw_seasonal": _f(q.get("realisation_raw_seasonal")),
            "realisation_recent": _f(q.get("realisation_recent")), "realisation_pessimistic": _f(q.get("realisation_pessimistic")),
            "gap_90d_cu_base": _f(q.gap_90d_cu_base, 0), "gap_90d_cu_low": _f(q.gap_90d_cu_low, 0),
            "gap_90d_cu_high": _f(q.gap_90d_cu_high, 0), "gap_ci_lo": _f(q.gap_ci_lo, 0), "gap_ci_hi": _f(q.gap_ci_hi, 0),
        }

    segs = {s: seg(s) for s in SEGMENT_ORDER}
    live = econ[econ.role != "Not run"]
    roll, test = live[live.role == "Rollout"], live[live.role == "Test cell"]
    addressable = live.groupby("segment")["incremental_revenue_cu"].sum()
    cv = ch["channel_value"]
    online_only_active = int(cv.loc[cv.channel == "Online only", "customers"].sum())
    aud = ch["channel_audience"]
    oo_aud = aud[(aud.channel == "Online only") & ~aud.segment.isin(["Lost", "Review List"])]
    aov = ch["channel_order_aov"].set_index(["customers_group", "order_channel"])["aov_cu"]
    fw = ch["channel_forward"]
    fw59 = fw[(fw.snapshot_name == "backtest_seasonal") & (fw.order_band == "5-9 orders")].set_index("channel")
    cv59 = cv[cv.order_band == "5-9 orders"].set_index("channel")
    fl = flow.set_index(["from_segment", "to_segment"])["share_of_from_segment"]
    rtm_c = rtm[rtm.segment == "Champions"].set_index("m_score")["realisation"]
    sens_t = sens[sens.variant != "Default"]
    hv = ["Champions", "Loyal", "Slipping Regulars"]
    timings = json.loads((ROOT / "reports" / "run_log.json").read_text()).get("timings_s", {}) \
        if (ROOT / "reports" / "run_log.json").exists() else {}
    return {
        "data": {
            "transaction_rows": int(rows_), "customers_in_customer_file": int(dim.customers),
            "customers_with_orders": int(dim.buyers), "customers_without_orders": int(dim.customers - dim.buyers),
            "orders": int(orders.orders), "revenue_2y_cu": _f(orders.revenue_cu, 0), "first_date": "2018-09-20",
            "last_date": "2020-09-22", "snapshot_date": str(cfg["snapshot"]["current"]),
            "active_12m_customers": int(active.active), "pct_active_12m": _f(active.active / dim.buyers),
            "revenue_12m_cu": _f(active.rev12, 0), "review_list_customers": int(dim.excluded),
            "newsletter_subscribers": int(dim.newsletter), "pct_newsletter_all": _f(dim.newsletter / dim.customers),
            "pct_newsletter_active": _f(active.subs / active.active),
            "dq_pass": int((dq.status == "PASS").sum()), "dq_flag": int((dq.status == "FLAG").sum()),
            "dq_fail": int((dq.status == "FAIL").sum()), "reconciliation_checks_passed": int(rec.passed.sum()),
            "reconciliation_checks_total": int(len(rec)),
            "store_closure": "2020-03-20 to 2020-05-05 (stores reopened 2020-05-06)",
        },
        "segments": segs,
        "headline": {
            "champions_pct_customers": segs["Champions"]["pct_customers"],
            "champions_pct_revenue_12m": segs["Champions"]["pct_revenue_12m"],
            "high_value_pct_customers": _f(sum(segs[s]["pct_customers"] for s in hv)),
            "high_value_pct_revenue_12m": _f(sum(segs[s]["pct_revenue_12m"] for s in hv)),
            "vip_customers": int(grid.loc[grid.value_tier == "VIP", "customers"].sum()),
            "vip_pct_revenue_12m": _f(grid.loc[grid.value_tier == "VIP", "revenue_12m_cu"].sum() / grid.revenue_12m_cu.sum()),
            "at_risk_customers": segs["At Risk"]["customers"], "at_risk_pct_customers": segs["At Risk"]["pct_customers"],
            "at_risk_expected_90d_cu": segs["At Risk"]["expected_90d_cu_base"],
            "at_risk_run_rate_90d_cu": segs["At Risk"]["run_rate_90d_cu"],
            "at_risk_gap_90d_cu": segs["At Risk"]["gap_90d_cu_base"],
            "at_risk_gap_90d_cu_low": segs["At Risk"]["gap_90d_cu_low"],
            "at_risk_gap_90d_cu_high": segs["At Risk"]["gap_90d_cu_high"],
            "at_risk_non_buyers_90d": segs["At Risk"]["expected_non_buyers_base"],
            "at_risk_addressable_90d_cu": _f(addressable.get("At Risk", 0), 0),
            "slipping_customers": segs["Slipping Regulars"]["customers"],
            "slipping_gap_90d_cu": segs["Slipping Regulars"]["gap_90d_cu_base"],
            "slipping_pct_revenue_12m": segs["Slipping Regulars"]["pct_revenue_12m"],
            "churn_signal_customers": segs["At Risk"]["customers"] + segs["Slipping Regulars"]["customers"],
            "churn_signal_pct_customers": _f(segs["At Risk"]["pct_customers"] + segs["Slipping Regulars"]["pct_customers"]),
            "churn_signal_gap_90d_cu": _f(segs["At Risk"]["gap_90d_cu_base"] + segs["Slipping Regulars"]["gap_90d_cu_base"], 0),
            "at_risk_lockdown_share": _f(query("""SELECT AVG((last_order_date BETWEEN DATE '2020-03-01' AND DATE '2020-05-31')::INT) AS s
                FROM 'data/marts/customer_rfm.parquet' WHERE snapshot_name='current' AND segment='At Risk'""").iloc[0]["s"]),
            "champions_realisation_m5": _f(rtm_c.get(5)), "champions_realisation_m4": _f(rtm_c.get(4)),
            "online_only_active_customers": online_only_active,
            "pct_online_only_active": _f(online_only_active / cv.customers.sum()),
            "online_only_active_subscribers": int(oo_aud.newsletter_subscribers.sum()),
            "online_only_high_value_customers": int(oo_aud[oo_aud.segment.isin(["Champions", "Loyal", "Slipping Regulars"])].customers.sum()),
            "store_only_active_customers": int(cv.loc[cv.channel == "Store only", "customers"].sum()),
            "aov_online_order_omni": _f(aov.get(("Omnichannel customers", "Online")), 2),
            "aov_store_order_omni": _f(aov.get(("Omnichannel customers", "Store")), 2),
            "rev_per_customer_5_9_online_only": _f(cv59.loc["Online only", "revenue_per_customer_cu"], 1),
            "rev_per_customer_5_9_omni": _f(cv59.loc["Omnichannel", "revenue_per_customer_cu"], 1),
            "rev_net_5_9_online_only": _f(cv59.loc["Online only", "revenue_net_of_returns_cu"], 1),
            "rev_net_5_9_omni": _f(cv59.loc["Omnichannel", "revenue_net_of_returns_cu"], 1),
            "repurchase_5_9_online_only": _f(fw59.loc["Online only", "repurchase_rate_90d"]),
            "repurchase_5_9_omni": _f(fw59.loc["Omnichannel", "repurchase_rate_90d"]),
            "repurchase_5_9_store_only": _f(fw59.loc["Store only", "repurchase_rate_90d"]),
            "champions_stayed_one_quarter": _f(fl.get(("Champions", "Champions"))),
            "champions_to_slipping_one_quarter": _f(fl.get(("Champions", "Slipping Regulars"))),
            "at_risk_to_lost_one_quarter": _f(fl.get(("At Risk", "Lost"))),
            "customers_changed_segment_one_quarter": _f(1 - flow[flow.from_segment == flow.to_segment].customers.sum()
                                                       / flow[flow.from_segment != "Not yet a customer"].customers.sum()),
            "threshold_sensitivity_max_abs_pct_change": _f(sens_t[~sens_t.segment.isin(["Lost", "Review List"])]["pct_change"].abs().max()),
        },
        "kmeans": km,
        "order_ladder": {c: {int(x.orders): _f(x.p_next_order) for x in g.itertuples()} for c, g in ladder.groupby("cohort")},
        "campaign": {
            "launch_date": campaign.LAUNCH_DATE, "read_date": campaign.READ_DATE, "holdout_share": campaign.HOLDOUT_SHARE,
            "rollout_contacted": _f(roll.contacted.sum(), 0), "rollout_total_cost_cu": _f(roll.total_cost_cu.sum(), 0),
            "rollout_incremental_buyers": _f(roll.incremental_buyers.sum(), 0),
            "rollout_incremental_revenue_cu": _f(roll.incremental_revenue_cu.sum(), 0),
            "rollout_net_profit_cu": _f(roll.net_profit_cu.sum(), 0),
            "test_cells_contacted": _f(test.contacted.sum(), 0), "test_cells_total_cost_cu": _f(test.total_cost_cu.sum(), 0),
            "test_cells_net_profit_cu": _f(test.net_profit_cu.sum(), 0),
            "budget_total_cu": _f(budget.loc[budget.line == "Total budget ask", "cost_cu"].iloc[0], 0),
            "holdout_opportunity_cost_cu": _f(budget.loc[budget.line.str.startswith("Memo: profit"), "cost_cu"].iloc[0], 0),
            "scenarios": {f"{x.scenario} | {x.role}": {"net_profit_cu": _f(x.net_profit_cu, 0), "total_cost_cu": _f(x.total_cost_cu, 0),
                                                      "incremental_revenue_cu": _f(x.incremental_revenue_cu, 0)} for x in scen.itertuples()},
            "arms": {f"{x.audience_label} | {x.arm}": {
                "role": x.role, "contacted": _f(x.contacted, 0), "uplift_pp": float(x.uplift_pp), "discount_rate": float(x.discount_rate),
                "baseline_rate": _f(x.baseline_rate), "incremental_revenue_cu": _f(x.incremental_revenue_cu, 0),
                "total_cost_cu": _f(x.total_cost_cu, 0), "net_profit_cu": _f(x.net_profit_cu, 0),
                "breakeven_uplift_pp": _f(x.breakeven_uplift_pp, 2), "mde_rate_pp": _f(x.mde_rate_pp, 2),
                "mde_revenue_cu": _f(x.mde_revenue_cu, 2), "readable_alone": bool(x.readable_alone),
                "powered_for_decision": bool(x.powered_for_decision)} for x in econ.itertuples()},
            "assumptions": campaign.default_assumptions(),
            "pooled_read": pooled,
        },
        "timings_s": timings,
    }


# --------------------------------------------------------------------------- orchestration
def run_all(log: Callable[[str], None] = print, timings: dict | None = None) -> dict:
    timings = {} if timings is None else timings
    paths = get_paths()

    def timed(name, fn, *a, **k):
        t0 = time.perf_counter()
        res = fn(*a, **k)
        timings[f"analysis:{name}"] = round(time.perf_counter() - t0, 2)
        log(f"  {name:<22} {timings[f'analysis:{name}']:6.1f} s")
        return res

    timed("app_tables", app_tables)
    rar = timed("revenue_at_risk", revenue_at_risk)
    rtm = timed("regression_to_mean", regression_to_mean)
    _save(rtm, "regression_to_mean.parquet")
    ch = timed("channel_tables", channel_tables)
    for name, frame in ch.items():
        _save(frame, f"{name}.parquet")
    sens = timed("threshold_sensitivity", threshold_sensitivity)
    _save(sens, "threshold_sensitivity.parquet")
    grid = timed("value_grid", value_grid)
    _save(grid, "value_grid.parquet")
    ladder = timed("order_ladder", order_ladder)
    _save(ladder, "order_ladder.parquet")
    inputs = timed("audience_inputs", campaign.audience_inputs)
    _save(inputs, "campaign_inputs.parquet")
    plan = campaign.plan_frame()
    econ = timed("campaign_economics", campaign.economics, plan, inputs, campaign.default_assumptions())
    econ["category_focus"] = econ["segment"].map(campaign.category_focus())
    _save(econ, "campaign_economics.parquet")
    scen = timed("campaign_scenarios", campaign.scenario_table, inputs, plan)
    _save(scen, "campaign_scenarios.parquet")
    budget = campaign.budget_lines(econ)
    _save(budget, "campaign_budget.parquet")
    pooled = campaign.pooled_read(econ)
    addressable = econ[econ.role != "Not run"].groupby("segment")["incremental_revenue_cu"].sum()
    rar["addressable_90d_cu"] = rar["segment"].map(addressable).fillna(0.0)
    _save(rar, "revenue_at_risk.parquet")
    power_tbl = timed("holdout_power", holdout_power, inputs)
    _save(power_tbl, "holdout_power.parquet")
    _save(timed("price_points", price_points_table), "price_points.parquet")
    _save(timed("rf_grid", rf_grid), "rf_grid.parquet")
    km = timed("kmeans_comparison", kmeans_comparison, log=log)
    flow = _marts("segment_flow.parquet")
    metrics = timed("metrics", build_metrics, km, rar, econ, scen, budget, pooled, ch, ladder, flow, rtm, sens, grid)
    out = paths.reports / "metrics.json"
    out.write_text(json.dumps(metrics, indent=2, default=str) + "\n")
    log(f"  wrote {out.relative_to(ROOT)}")
    return metrics
