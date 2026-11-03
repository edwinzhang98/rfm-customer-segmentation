"""Segment definitions and a vectorised Python copy of the SQL scoring rules.

The SQL in ``sql/05_customer_rfm.sql`` is the production definition. This module
re-implements the same rules in numpy so the dashboard can re-segment 1.36M customers
instantly when someone moves a threshold slider. ``tests/test_segments_parity.py``
checks that both give identical results.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace

import numpy as np
import pandas as pd

from .config import load_config

SEGMENT_ORDER = [
    "Champions",
    "Loyal",
    "Slipping Regulars",
    "Potential Loyalists",
    "New Customers",
    "Needs Attention",
    "At Risk",
    "Hibernating",
    "Lost",
    "Review List",
]
VALUE_TIERS = ["VIP", "High", "Mid", "Low", "None"]

# Plain-language definition (for CRM colleagues) and the rule in score terms.
SEGMENT_INFO: dict[str, dict[str, str]] = {
    "Champions": {
        "plain": "Bought in the last 60 days, 5+ orders and 200+ CU in the last 12 months",
        "rule": "R >= 4 and F >= 4 and M >= 4",
        "group": "High value - keep",
    },
    "Loyal": {
        "plain": "Bought in the last 60 days, 5+ orders in 12 months, under 200 CU (frequent, small baskets)",
        "rule": "R >= 4 and F >= 4 (remaining)",
        "group": "High frequency - grow basket",
    },
    "Slipping Regulars": {
        "plain": "5+ orders in 12 months, but no order in the last 61-120 days",
        "rule": "R = 3 and F >= 4",
        "group": "Early warning - high value",
    },
    "Potential Loyalists": {
        "plain": "Bought in the last 60 days, 1-4 orders in 12 months (not new)",
        "rule": "R >= 4 (remaining)",
        "group": "Growth",
    },
    "New Customers": {
        "plain": "First order within the last 90 days",
        "rule": "tenure < 90 days",
        "group": "Growth",
    },
    "Needs Attention": {
        "plain": "Last order 61-120 days ago, 1-4 orders in 12 months",
        "rule": "R = 3 (remaining)",
        "group": "Early warning",
    },
    "At Risk": {
        "plain": "Last order 121-364 days ago but used to buy often (3+ orders) or a lot (200+ CU)",
        "rule": "R <= 2 and (F >= 3 or M >= 4)",
        "group": "Churn risk - win back",
    },
    "Hibernating": {
        "plain": "Last order 121-364 days ago, 1-2 orders and under 200 CU",
        "rule": "R <= 2 (remaining)",
        "group": "Low value lapsing",
    },
    "Lost": {
        "plain": "No order in the last 365 days",
        "rule": "recency >= 365 days",
        "group": "Churned",
    },
    "Review List": {
        "plain": "Bulk or near-daily buying pattern: no offers or paid media until reviewed",
        "rule": ">= 20 units of one article in an order, >= 100 units in an order, or purchases on >= 150 days",
        "group": "Under review",
    },
}


@dataclass(frozen=True)
class Thresholds:
    lookback_days: int = 365
    r5_max_days: int = 30
    r4_max_days: int = 60
    r3_max_days: int = 120
    r2_max_days: int = 180
    f5_min_orders: int = 10
    f4_min_orders: int = 5
    f3_min_orders: int = 3
    f2_min_orders: int = 2
    m5_min_cu: float = 400
    m4_min_cu: float = 200
    m3_min_cu: float = 100
    m2_min_cu: float = 50
    new_customer_days: int = 90
    vip_min_cu: float = 1000

    @classmethod
    def from_config(cls, cfg: dict | None = None) -> "Thresholds":
        cfg = cfg or load_config()
        t = cfg["rfm_thresholds"]
        return cls(lookback_days=cfg["snapshot"]["lookback_days"], **t)

    def with_changes(self, **changes) -> "Thresholds":
        return replace(self, **changes)

    def as_dict(self) -> dict:
        return asdict(self)


def score(df: pd.DataFrame, th: Thresholds) -> pd.DataFrame:
    """Return r_score, f_score, m_score (0-5) for columns recency_days, frequency_12m, monetary_12m_cu."""
    rec = df["recency_days"].to_numpy()
    freq = df["frequency_12m"].to_numpy()
    mon = df["monetary_12m_cu"].to_numpy()
    r = np.select(
        [rec <= th.r5_max_days, rec <= th.r4_max_days, rec <= th.r3_max_days, rec <= th.r2_max_days,
         rec < th.lookback_days],
        [5, 4, 3, 2, 1],
        default=0,
    )
    f = np.select(
        [freq >= th.f5_min_orders, freq >= th.f4_min_orders, freq >= th.f3_min_orders, freq >= th.f2_min_orders,
         freq >= 1],
        [5, 4, 3, 2, 1],
        default=0,
    )
    m = np.select(
        [freq == 0, mon >= th.m5_min_cu, mon >= th.m4_min_cu, mon >= th.m3_min_cu, mon >= th.m2_min_cu],
        [0, 5, 4, 3, 2],
        default=1,
    )
    return pd.DataFrame({"r_score": r, "f_score": f, "m_score": m}, index=df.index)


def assign_segments(df: pd.DataFrame, th: Thresholds, scores: pd.DataFrame | None = None) -> pd.Series:
    """Segment per customer, same priority order as the SQL CASE WHEN."""
    s = score(df, th) if scores is None else scores
    r, f, m = s["r_score"].to_numpy(), s["f_score"].to_numpy(), s["m_score"].to_numpy()
    rec = df["recency_days"].to_numpy()
    tenure = df["tenure_days"].to_numpy()
    excluded = df["is_excluded"].to_numpy().astype(bool)
    conditions = [
        excluded,
        rec >= th.lookback_days,
        tenure < th.new_customer_days,
        (r >= 4) & (f >= 4) & (m >= 4),
        (r >= 4) & (f >= 4),
        (r == 3) & (f >= 4),
        r >= 4,
        r == 3,
        (f >= 3) | (m >= 4),
    ]
    choices = ["Review List", "Lost", "New Customers", "Champions", "Loyal", "Slipping Regulars",
               "Potential Loyalists", "Needs Attention", "At Risk"]
    seg = np.select(conditions, choices, default="Hibernating")
    return pd.Series(pd.Categorical(seg, categories=SEGMENT_ORDER, ordered=True), index=df.index, name="segment")


def value_tier(df: pd.DataFrame, th: Thresholds) -> pd.Series:
    """Second axis: VIP / High / Mid / Low on 12-month spend; None = no 12-month order."""
    mon = df["monetary_12m_cu"].to_numpy()
    freq = df["frequency_12m"].to_numpy()
    tier = np.select([freq == 0, mon >= th.vip_min_cu, mon >= th.m5_min_cu, mon >= th.m4_min_cu],
                     ["None", "VIP", "High", "Mid"], default="Low")
    return pd.Series(pd.Categorical(tier, categories=VALUE_TIERS, ordered=True), index=df.index, name="value_tier")


def quantile_scores(df: pd.DataFrame) -> pd.DataFrame:
    """The common textbook alternative: quintile scores (1-5) among 12-month-active customers.

    Ties make this unstable: 34% of active customers have exactly one order, so the
    frequency quintile edges collapse (pd.qcut drops duplicate edges) and customers
    with identical behaviour can only be split by an arbitrary rank. Returned so the
    dashboard can show the problem side by side with the business thresholds.
    """
    active = df["frequency_12m"] > 0
    out = pd.DataFrame(index=df.index, data={"r_q": 0, "f_q": 0, "m_q": 0})
    sub = df.loc[active]
    # Recency: fewer days = better = higher score
    out.loc[active, "r_q"] = pd.qcut(-sub["recency_days"], 5, labels=False, duplicates="drop") + 1
    out.loc[active, "f_q"] = pd.qcut(sub["frequency_12m"], 5, labels=False, duplicates="drop") + 1
    out.loc[active, "m_q"] = pd.qcut(sub["monetary_12m_cu"], 5, labels=False, duplicates="drop") + 1
    return out


def quantile_edges(df: pd.DataFrame) -> dict[str, list[float]]:
    """Quintile cut points among active customers (for the comparison table)."""
    sub = df[df["frequency_12m"] > 0]
    qs = [0.2, 0.4, 0.6, 0.8]
    return {
        "recency_days": [float(x) for x in sub["recency_days"].quantile(qs)],
        "frequency_12m": [float(x) for x in sub["frequency_12m"].quantile(qs)],
        "monetary_12m_cu": [float(x) for x in sub["monetary_12m_cu"].quantile(qs)],
    }


def segment_summary(df: pd.DataFrame, segments: pd.Series) -> pd.DataFrame:
    """Customers and 12-month revenue per segment, with shares (used by interactive pages)."""
    tmp = pd.DataFrame({"segment": segments, "revenue": df["monetary_12m_cu"].to_numpy()})
    out = tmp.groupby("segment", observed=False).agg(customers=("revenue", "size"), revenue_12m_cu=("revenue", "sum"))
    out["pct_customers"] = out["customers"] / out["customers"].sum()
    out["pct_revenue_12m"] = out["revenue_12m_cu"] / out["revenue_12m_cu"].sum()
    return out.reset_index()
