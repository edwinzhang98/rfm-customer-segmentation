"""Python analysis steps that run after the SQL marts (``python run.py --steps analysis``).

Outputs (all in data/marts/ unless noted):
    revenue_at_risk.parquet        "if we do nothing" 90-day projection per segment
    channel_value.parquet          online-only vs store-only vs omnichannel, at equal order counts
    order_ladder.parquet           chance of an (n+1)-th order given n orders
    holdout_power.parquet          minimum detectable effect per segment and holdout share
    campaign_economics.parquet     base-case economics of every campaign arm
    kmeans_k_selection.parquet     inertia + silhouette for k = 2..10
    kmeans_profile.parquet         cluster centroids in business units
    kmeans_crosstab.parquet        clusters x rule-based segments
    app_customers.parquet          slim customer table for the dashboard (no ids)
    app_backtest.parquet           slim backtest table for the dashboard (no ids)
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
from .segments import SEGMENT_ORDER
from .sqlrun import query

Z95 = 1.959964


# --------------------------------------------------------------------------- helpers
def _marts(name: str) -> pd.DataFrame:
    return pd.read_parquet(get_paths().marts / name)


def _save(df: pd.DataFrame, name: str) -> None:
    df.to_parquet(get_paths().marts / name, index=False)


def _ratio_ci(y: np.ndarray, x: np.ndarray) -> tuple[float, float, float]:
    """Ratio of sums sum(y)/sum(x) with a delta-method 95% CI (customer-level sampling noise)."""
    n = len(y)
    r = y.sum() / x.sum()
    resid = y - r * x
    se = math.sqrt(resid.var(ddof=1) / n) / x.mean()
    return r, r - Z95 * se, r + Z95 * se


# --------------------------------------------------------------------------- revenue at risk
def revenue_at_risk() -> pd.DataFrame:
    """Project the next 90 days for today's segments from what the same segments did a year ago.

    run-rate 90d   = 12-month revenue x 90/365 (what the segment brings in per quarter at its usual pace)
    expected (BAU) = run-rate x realisation ratio observed in the backtest
                     (Lost: customers x 90-day revenue per customer, as its run-rate is 0)
    shortfall      = run-rate - expected = revenue at risk if we do nothing
    Base case = season-matched backtest (2019-09-22); range = min/max over both backtests.
    """
    cfg = load_config()
    factor = cfg["snapshot"]["outcome_days"] / cfg["snapshot"]["lookback_days"]
    prof = _marts("segment_profile.parquet")
    outcomes = _marts("customer_outcomes_90d.parquet")
    seg_out = _marts("segment_outcomes_90d.parquet")

    rows = []
    for _, p in prof.iterrows():
        seg = p["segment"]
        row = {"segment": seg, "customers": int(p["customers"]),
               "revenue_12m_cu": float(p["revenue_12m_cu"]),
               "run_rate_90d_cu": float(p["revenue_12m_cu"]) * factor}
        for basis in ("backtest_seasonal", "backtest_recent"):
            so = seg_out[(seg_out.snapshot_name == basis) & (seg_out.segment == seg)]
            if so.empty:
                continue
            so = so.iloc[0]
            cust = outcomes[(outcomes.snapshot_name == basis) & (outcomes.segment == seg)]
            key = basis.replace("backtest_", "")
            row[f"backtest_customers_{key}"] = int(so["customers"])
            row[f"repurchase_rate_{key}"] = float(so["repurchase_rate"])
            if row["run_rate_90d_cu"] > 0 and so["run_rate_90d_cu"] > 0:
                ratio, lo, hi = _ratio_ci(cust["revenue_next_90d_cents"].to_numpy(float),
                                          cust["run_rate_90d_cents"].to_numpy(float))
                row[f"realisation_{key}"] = ratio
                row[f"realisation_{key}_lo"] = lo
                row[f"realisation_{key}_hi"] = hi
                row[f"expected_90d_cu_{key}"] = row["run_rate_90d_cu"] * ratio
            else:
                per_cust = float(so["revenue_per_customer_cu"])
                row[f"realisation_{key}"] = np.nan
                row[f"expected_90d_cu_{key}"] = row["customers"] * per_cust
            row[f"expected_buyers_{key}"] = row["customers"] * float(so["repurchase_rate"])
        rows.append(row)
    df = pd.DataFrame(rows)
    # Lost has a tiny seasonal backtest (data starts a year before the snapshot): use recent as base
    df["base_basis"] = np.where(df["backtest_customers_seasonal"].fillna(0) < 10_000, "recent", "seasonal")
    for col in ("expected_90d_cu", "repurchase_rate", "realisation", "expected_buyers"):
        df[f"{col}_base"] = np.where(df["base_basis"] == "recent", df[f"{col}_recent"], df[f"{col}_seasonal"])
    df["shortfall_90d_cu_base"] = (df["run_rate_90d_cu"] - df["expected_90d_cu_base"]).where(df["run_rate_90d_cu"] > 0)
    for key in ("seasonal", "recent"):
        df[f"shortfall_90d_cu_{key}"] = (df["run_rate_90d_cu"] - df[f"expected_90d_cu_{key}"]).where(df["run_rate_90d_cu"] > 0)
    df["shortfall_90d_cu_low"] = df[["shortfall_90d_cu_seasonal", "shortfall_90d_cu_recent"]].min(axis=1)
    df["shortfall_90d_cu_high"] = df[["shortfall_90d_cu_seasonal", "shortfall_90d_cu_recent"]].max(axis=1)
    df["shortfall_pct_of_run_rate"] = df["shortfall_90d_cu_base"] / df["run_rate_90d_cu"]
    df["expected_non_buyers_base"] = df["customers"] - df["expected_buyers_base"]
    # sampling-noise CI on the shortfall (base basis only)
    df["shortfall_90d_cu_ci_lo"] = df["run_rate_90d_cu"] * (1 - df["realisation_seasonal_hi"])
    df["shortfall_90d_cu_ci_hi"] = df["run_rate_90d_cu"] * (1 - df["realisation_seasonal_lo"])
    df["segment"] = pd.Categorical(df["segment"], SEGMENT_ORDER, ordered=True)
    return df.sort_values("segment").reset_index(drop=True)


# --------------------------------------------------------------------------- channel
def channel_value() -> pd.DataFrame:
    """12-month value by channel profile *within the same order-count band*.

    Customers with more orders are mechanically more likely to have used both channels,
    so comparing raw averages across channel profiles mostly measures frequency.
    """
    return query("""
        WITH cur AS (
            SELECT *,
                   CASE WHEN frequency_12m = 1 THEN '1 order'
                        WHEN frequency_12m = 2 THEN '2 orders'
                        WHEN frequency_12m <= 4 THEN '3-4 orders'
                        WHEN frequency_12m <= 9 THEN '5-9 orders'
                        ELSE '10+ orders' END AS order_band
            FROM 'data/marts/customer_rfm.parquet'
            WHERE snapshot_name = 'current' AND frequency_12m > 0 AND NOT is_excluded
        )
        SELECT order_band, channel_profile,
               COUNT(*)                                      AS customers,
               AVG(monetary_12m_cu)                          AS revenue_per_customer_cu,
               SUM(monetary_12m_cu) / SUM(frequency_12m)     AS aov_cu,
               AVG(frequency_12m)                            AS avg_orders
        FROM cur
        GROUP BY ALL
        ORDER BY order_band, channel_profile
    """)


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
    """MDE per segment for a range of holdout shares, on the segment's experiment population
    (newsletter subscribers, or everyone when the plan uses paid social)."""
    cfg = load_config()["economics"]
    reach = campaign.segment_reach(campaign.plan_frame())
    rows = []
    for _, r in inputs.iterrows():
        if r["segment"] == "Excluded":
            continue
        pop = r["customers"] * (1.0 if reach.get(r["segment"], False) else r["newsletter_share"])
        for s in shares:
            n_c, n_t = pop * s, pop * (1 - s)
            rows.append({
                "segment": r["segment"], "holdout_share": s, "population": pop, "n_treat": n_t, "n_control": n_c,
                "baseline_rate": r["baseline_rate"],
                "mde_rate_pp": 100 * power.mde_rate(r["baseline_rate"], n_t, n_c, cfg["alpha"], cfg["power"]),
                "mde_revenue_cu": power.mde_mean(r["sd_revenue_cu"], n_t, n_c, cfg["alpha"], cfg["power"]),
                "revenue_per_customer_cu": r["revenue_per_customer_cu"],
            })
    return pd.DataFrame(rows)


def pooled_holdout(econ: pd.DataFrame, share: float = 0.10) -> dict:
    """One campaign-wide holdout (same share in every segment): MDE on the overall 90-day
    repurchase rate and the expected overall lift if every rollout arm hits its assumption."""
    cfg = load_config()["economics"]
    seg = econ.groupby("segment").agg(population=("experiment_population", "first"),
                                      baseline=("baseline_rate", "first"))
    roll = econ[econ.role == "Rollout"].set_index("segment")
    pop = seg["population"].sum()
    p_bar = float((seg["population"] * seg["baseline"]).sum() / pop)
    expected_lift = float((roll["contacted"] * roll["uplift_pp"] / 100).sum() / (pop * (1 - share)))
    mde = power.mde_rate(p_bar, pop * (1 - share), pop * share, cfg["alpha"], cfg["power"])
    return {"holdout_share": share, "population": round(pop), "baseline_rate": round(p_bar, 4),
            "mde_rate_pp": round(100 * mde, 3), "expected_lift_pp": round(100 * expected_lift, 3),
            "detectable": bool(100 * mde <= 100 * expected_lift)}


# --------------------------------------------------------------------------- k-means
def kmeans_comparison(log: Callable[[str], None] = print) -> dict:
    """K-Means on log-scaled R, F, M of 12-month-active customers, compared with the rules."""
    cfg = load_config()
    kcfg, seed = cfg["kmeans"], cfg["random_seed"]
    df = _marts("customer_rfm.parquet")
    cur = df[(df.snapshot_name == "current") & (df.frequency_12m > 0) & (~df.is_excluded)].reset_index(drop=True)
    feats = ["recency_days", "frequency_12m", "monetary_12m_cu"]
    X_raw = np.log1p(cur[feats].to_numpy(float))
    scaler = StandardScaler().fit(X_raw)
    X = scaler.transform(X_raw)

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
    labels = final.labels_
    # order clusters by median monetary value so labels read low -> high
    order = pd.Series(cur["monetary_12m_cu"].to_numpy()).groupby(labels).median().sort_values().index
    relabel = {old: new for new, old in enumerate(order, start=1)}
    labels = np.vectorize(relabel.get)(labels)
    cur["cluster"] = labels

    prof = cur.groupby("cluster").agg(
        customers=("customer_id", "size"),
        median_recency_days=("recency_days", "median"),
        median_orders_12m=("frequency_12m", "median"),
        median_revenue_12m_cu=("monetary_12m_cu", "median"),
        revenue_12m_cu=("monetary_12m_cu", "sum"),
    ).reset_index()
    prof["pct_customers"] = prof["customers"] / prof["customers"].sum()
    prof["pct_revenue_12m"] = prof["revenue_12m_cu"] / prof["revenue_12m_cu"].sum()
    top_seg = cur.groupby("cluster")["segment"].agg(lambda s: s.value_counts(normalize=True).head(2).round(2).to_dict())
    prof["main_rule_segments"] = prof["cluster"].map(lambda c: ", ".join(f"{s} {v:.0%}" for s, v in top_seg[c].items()))

    ct = pd.crosstab(cur["cluster"], cur["segment"])
    ct = ct.reset_index().melt(id_vars="cluster", var_name="segment", value_name="customers")
    ari_rules = adjusted_rand_score(cur["segment"], labels)

    # stability 1: same data, different random starts
    seeds = kcfg["stability_seeds"]
    alt = [KMeans(n_clusters=k, n_init=1, random_state=s).fit(X[sample_idx]).predict(X) for s in seeds]
    ari_seeds = [adjusted_rand_score(alt[0], a) for a in alt[1:]]
    # stability 2: fit on the previous quarter (2020-06-24) and apply to today's customers
    prev = df[(df.snapshot_name == "backtest_recent") & (df.frequency_12m > 0) & (~df.is_excluded)]
    Xp_raw = np.log1p(prev[feats].to_numpy(float))
    sp = StandardScaler().fit(Xp_raw)
    km_prev = KMeans(n_clusters=k, n_init=10, random_state=seed).fit(sp.transform(Xp_raw))
    labels_prev_model = km_prev.predict(sp.transform(X_raw))
    ari_refit = adjusted_rand_score(final.labels_, labels_prev_model)
    # share of customers whose cluster changes when the model is refit a quarter later
    switch = pd.crosstab(final.labels_, labels_prev_model).to_numpy()
    moved_share = 1 - switch.max(axis=1).sum() / switch.sum()

    _save(sel, "kmeans_k_selection.parquet")
    _save(prof, "kmeans_profile.parquet")
    _save(ct, "kmeans_crosstab.parquet")
    return {
        "k_final": k,
        "n_customers": int(len(cur)),
        "silhouette_by_k": {int(r.k): round(float(r.silhouette), 4) for r in sel.itertuples()},
        "ari_vs_rules": round(float(ari_rules), 4),
        "ari_between_seeds_min": round(float(min(ari_seeds)), 4),
        "ari_between_seeds_mean": round(float(np.mean(ari_seeds)), 4),
        "ari_refit_previous_quarter": round(float(ari_refit), 4),
        "share_reassigned_by_refit": round(float(moved_share), 4),
    }


# --------------------------------------------------------------------------- app tables
def app_tables() -> None:
    """Slim, id-free copies of the customer tables for the dashboard (fast to load)."""
    df = _marts("customer_rfm.parquet")
    keep = ["recency_days", "tenure_days", "frequency_12m", "monetary_12m_cu", "is_excluded",
            "is_newsletter_subscriber", "channel_profile", "segment"]
    cur = df[df.snapshot_name == "current"][keep].copy()
    cur["channel_profile"] = cur["channel_profile"].astype("category")
    cur["segment"] = pd.Categorical(cur["segment"], SEGMENT_ORDER, ordered=True)
    for c in ("recency_days", "tenure_days", "frequency_12m"):
        cur[c] = cur[c].astype("int32")
    cur["monetary_12m_cu"] = cur["monetary_12m_cu"].astype("float32")
    _save(cur, "app_customers.parquet")

    out = _marts("customer_outcomes_90d.parquet")
    rfm_bt = df[df.snapshot_name != "current"][["snapshot_name", "customer_id", "tenure_days", "is_excluded",
                                               "monetary_12m_cu"]]
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


# --------------------------------------------------------------------------- metrics
def build_metrics(kmeans: dict, rar: pd.DataFrame, econ: pd.DataFrame, chan: pd.DataFrame,
                  ladder: pd.DataFrame, power_tbl: pd.DataFrame) -> dict:
    cfg = load_config()
    paths = get_paths()
    prof = _marts("segment_profile.parquet").set_index("segment")
    dq = _marts("dq_checks.parquet")
    rec = _marts("reconciliation_checks.parquet")
    dim = query("""SELECT COUNT(*) AS customers, SUM(has_orders::INT) AS buyers, SUM(is_excluded::INT) AS excluded,
                          SUM(is_newsletter_subscriber::INT) AS newsletter
                   FROM 'data/marts/dim_customers.parquet'""").iloc[0]
    totals = query(f"""SELECT COUNT(*) AS rows_, SUM(price) AS price_sum FROM 'data/staged/stg_transactions.parquet'""").iloc[0]
    orders = query("SELECT COUNT(*) AS orders, SUM(revenue_cents)/100.0 AS revenue_cu FROM 'data/marts/fct_orders.parquet'").iloc[0]
    active = query("""SELECT COUNT(*) AS active, SUM(monetary_12m_cu) AS rev12
                      FROM 'data/marts/customer_rfm.parquet' WHERE snapshot_name='current' AND frequency_12m > 0""").iloc[0]
    rar_i = rar.set_index("segment")

    def seg(name: str) -> dict:
        p = prof.loc[name]
        r = rar_i.loc[name]
        return {
            "customers": int(p["customers"]),
            "pct_customers": round(float(p["pct_customers"]), 4),
            "revenue_12m_cu": round(float(p["revenue_12m_cu"]), 0),
            "pct_revenue_12m": round(float(p["pct_revenue_12m"]), 4),
            "pct_revenue_2y": round(float(p["pct_revenue_2y"]), 4),
            "aov_12m_cu": None if p["aov_12m_cu"] != p["aov_12m_cu"] else round(float(p["aov_12m_cu"]), 2),
            "avg_orders_12m": round(float(p["avg_orders_12m"]), 2),
            "pct_online_only": round(float(p["pct_online_only"]), 4),
            "pct_omnichannel": round(float(p["pct_omnichannel"]), 4),
            "pct_newsletter": round(float(p["pct_newsletter"]), 4),
            "repurchase_rate_90d_base": round(float(r["repurchase_rate_base"]), 4),
            "repurchase_rate_90d_seasonal": None if pd.isna(r.get("repurchase_rate_seasonal")) else round(float(r["repurchase_rate_seasonal"]), 4),
            "repurchase_rate_90d_recent": round(float(r["repurchase_rate_recent"]), 4),
            "run_rate_90d_cu": round(float(r["run_rate_90d_cu"]), 0),
            "expected_90d_cu_base": round(float(r["expected_90d_cu_base"]), 0),
            "shortfall_90d_cu_base": None if pd.isna(r["shortfall_90d_cu_base"]) else round(float(r["shortfall_90d_cu_base"]), 0),
            "shortfall_90d_cu_low": None if pd.isna(r["shortfall_90d_cu_low"]) else round(float(r["shortfall_90d_cu_low"]), 0),
            "shortfall_90d_cu_high": None if pd.isna(r["shortfall_90d_cu_high"]) else round(float(r["shortfall_90d_cu_high"]), 0),
            "realisation_base": None if pd.isna(r["realisation_base"]) else round(float(r["realisation_base"]), 4),
            "expected_non_buyers_base": round(float(r["expected_non_buyers_base"]), 0),
        }

    segs = {s: seg(s) for s in SEGMENT_ORDER}
    hv = ["Champions", "Loyal"]
    online_only_active = chan.groupby("channel_profile")["customers"].sum()
    rollout = econ[econ["role"] == "Rollout"]
    tests = econ[econ["role"] == "Test cell"]
    pooled = pooled_holdout(econ)
    timings = json.loads((ROOT / "reports" / "run_log.json").read_text()).get("timings_s", {}) \
        if (ROOT / "reports" / "run_log.json").exists() else {}
    m = {
        "data": {
            "transaction_rows": int(totals["rows_"]),
            "customers_in_customer_file": int(dim["customers"]),
            "customers_with_orders": int(dim["buyers"]),
            "customers_without_orders": int(dim["customers"] - dim["buyers"]),
            "orders": int(orders["orders"]),
            "revenue_2y_cu": round(float(orders["revenue_cu"]), 0),
            "first_date": "2018-09-20",
            "last_date": "2020-09-22",
            "snapshot_date": str(cfg["snapshot"]["current"]),
            "active_12m_customers": int(active["active"]),
            "pct_active_12m": round(float(active["active"] / dim["buyers"]), 4),
            "revenue_12m_cu": round(float(active["rev12"]), 0),
            "excluded_customers": int(dim["excluded"]),
            "newsletter_subscribers": int(dim["newsletter"]),
            "pct_newsletter": round(float(dim["newsletter"] / dim["customers"]), 4),
            "dq_pass": int((dq.status == "PASS").sum()),
            "dq_flag": int((dq.status == "FLAG").sum()),
            "dq_fail": int((dq.status == "FAIL").sum()),
            "reconciliation_checks_passed": int(rec.passed.sum()),
            "reconciliation_checks_total": int(len(rec)),
        },
        "segments": segs,
        "headline": {
            "champions_pct_customers": segs["Champions"]["pct_customers"],
            "champions_pct_revenue_12m": segs["Champions"]["pct_revenue_12m"],
            "high_value_customers": sum(segs[s]["customers"] for s in hv),
            "high_value_pct_customers": round(sum(segs[s]["pct_customers"] for s in hv), 4),
            "high_value_pct_revenue_12m": round(sum(segs[s]["pct_revenue_12m"] for s in hv), 4),
            "at_risk_customers": segs["At Risk"]["customers"],
            "at_risk_pct_customers": segs["At Risk"]["pct_customers"],
            "at_risk_shortfall_90d_cu": segs["At Risk"]["shortfall_90d_cu_base"],
            "at_risk_shortfall_90d_cu_low": segs["At Risk"]["shortfall_90d_cu_low"],
            "at_risk_shortfall_90d_cu_high": segs["At Risk"]["shortfall_90d_cu_high"],
            "at_risk_run_rate_90d_cu": segs["At Risk"]["run_rate_90d_cu"],
            "at_risk_expected_90d_cu": segs["At Risk"]["expected_90d_cu_base"],
            "at_risk_non_buyers_90d": segs["At Risk"]["expected_non_buyers_base"],
            "churn_signal_customers": segs["At Risk"]["customers"] + segs["Needs Attention"]["customers"],
            "churn_signal_pct_customers": round(segs["At Risk"]["pct_customers"] + segs["Needs Attention"]["pct_customers"], 4),
            "churn_signal_shortfall_90d_cu": round(segs["At Risk"]["shortfall_90d_cu_base"] + segs["Needs Attention"]["shortfall_90d_cu_base"], 0),
            "online_only_active_customers": int(online_only_active.get("Online only", 0)),
            "pct_online_only_active": round(float(online_only_active.get("Online only", 0) / online_only_active.sum()), 4),
            "online_only_high_value_customers": int(query("""
                SELECT COUNT(*) AS n FROM 'data/marts/customer_rfm.parquet'
                WHERE snapshot_name = 'current' AND segment IN ('Champions', 'Loyal')
                  AND channel_profile = 'Online only'""").iloc[0]["n"]),
        },
        "kmeans": kmeans,
        "order_ladder": {c: {int(r.orders): (None if pd.isna(r.p_next_order) else round(float(r.p_next_order), 4))
                             for r in g.itertuples()} for c, g in ladder.groupby("cohort")},
        "campaign": {
            "launch_date": campaign.LAUNCH_DATE,
            "read_date": campaign.READ_DATE,
            "rollout_contacted": round(float(rollout["contacted"].sum()), 0),
            "rollout_total_cost_cu": round(float(rollout["total_cost_cu"].sum()), 0),
            "rollout_incremental_buyers": round(float(rollout["incremental_buyers"].sum()), 0),
            "rollout_incremental_revenue_cu": round(float(rollout["incremental_revenue_cu"].sum()), 0),
            "rollout_net_profit_cu": round(float(rollout["net_profit_cu"].sum()), 0),
            "test_cells_total_cost_cu": round(float(tests["total_cost_cu"].sum()), 0),
            "test_cells_net_profit_cu": round(float(tests["net_profit_cu"].sum()), 0),
            "arms": {f"{r.segment} | {r.arm}": {
                "role": r.role,
                "contacted": round(float(r.contacted), 0),
                "uplift_pp": float(r.uplift_pp),
                "discount_rate": float(r.discount_rate),
                "incremental_revenue_cu": round(float(r.incremental_revenue_cu), 0),
                "total_cost_cu": round(float(r.total_cost_cu), 0),
                "net_profit_cu": round(float(r.net_profit_cu), 0),
                "breakeven_uplift_pp": None if not np.isfinite(r.breakeven_uplift_pp) else round(float(r.breakeven_uplift_pp), 2),
                "mde_vs_holdout_pp": round(float(r.mde_vs_holdout_pp), 2),
                "detectable": bool(r.detectable),
            } for r in econ.itertuples()},
            "assumptions": campaign.default_assumptions(),
            "pooled_holdout": pooled,
        },
        "timings_s": timings,
    }
    return m


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

    rar = timed("revenue_at_risk", revenue_at_risk)
    _save(rar.assign(segment=rar["segment"].astype(str)), "revenue_at_risk.parquet")
    chan = timed("channel_value", channel_value)
    _save(chan, "channel_value.parquet")
    ladder = timed("order_ladder", order_ladder)
    _save(ladder, "order_ladder.parquet")
    inputs = timed("segment_inputs", campaign.segment_inputs)
    _save(inputs, "campaign_inputs.parquet")
    econ = timed("campaign_economics", campaign.economics, campaign.plan_frame(), inputs, campaign.default_assumptions())
    focus = campaign.category_focus()
    econ["category_focus"] = econ["segment"].map(focus)
    _save(econ, "campaign_economics.parquet")
    power_tbl = timed("holdout_power", holdout_power, inputs)
    _save(power_tbl, "holdout_power.parquet")
    km = timed("kmeans_comparison", kmeans_comparison, log=log)
    timed("app_tables", app_tables)
    metrics = timed("metrics", build_metrics, km, rar, econ, chan, ladder, power_tbl)
    out = paths.reports / "metrics.json"
    out.write_text(json.dumps(metrics, indent=2, default=str) + "\n")
    log(f"  wrote {out.relative_to(ROOT)}")
    return metrics
