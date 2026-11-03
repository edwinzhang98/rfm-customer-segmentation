"""Autumn campaign plan: audiences, actions, economics and measurement.

Everything a CRM colleague needs to execute (audience rule, action, timing, channel,
category, KPI, holdout, decision rule) lives here, so the dashboard, the report and
docs/campaign_plan.md all show the same plan.

Audiences are segments, or slices of a segment where the economics differ (At Risk is
split by recency and value because 44% of the 121-180-day group come back on their own
against 27% of the 181-364-day group).

Economics model (per arm, 90-day horizon, money in CU):
    experiment population = customers we can reach: newsletter subscribers, plus everyone
                            else when the audience's plan uses paid social
    contacted          = population x the arm's share (the rest goes to other arms and to
                         the 10% holdout, which receives business-as-usual mail only)
    incremental buyers = contacted x assumed lift (intention-to-treat: per assigned customer,
                         so non-openers and unmatched paid-social contacts are included)
    incremental revenue= incremental buyers x value of an incremental buyer
                         (base: ONE order at the audience's AOV; optimistic: the backtest's
                         average 90-day revenue per buyer)
    contribution       = incremental revenue x contribution margin (base 40% = 50% gross
                         margin less fulfilment and returns on mostly-online orders)
    discount cost      = redemptions x discount x AOV, with redemptions =
                         contacted x (baseline rate x redemption share + lift); coupons are
                         also used by customers who would have bought anyway
    contact cost       = emails x email cost + paid-social audience x paid-social cost
    net profit         = contribution - discount cost - contact cost
    break-even lift    = (discount x AOV x baseline x redemption share + contact cost per head)
                         / (value per incremental buyer x margin - discount x AOV)
All lifts are planning assumptions. The holdout exists to replace them with measurements.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from . import power
from .config import get_paths, load_config

LAUNCH_DATE = "2020-09-28"   # Monday after the 2020-09-22 snapshot
READ_DATE = "2020-12-27"     # launch + 90 days (final read-out)
HOLDOUT_SHARE = 0.10         # same share in every audience, so the pooled read is a clean split


@dataclass(frozen=True)
class Audience:
    key: str
    segment: str
    label: str
    rule: str          # plain language, for the audience spec
    query: str         # pandas query on customer_rfm / customer_outcomes columns


AUDIENCES: list[Audience] = [
    Audience("champions", "Champions", "Champions", "segment = Champions", "segment == 'Champions'"),
    Audience("loyal", "Loyal", "Loyal", "segment = Loyal", "segment == 'Loyal'"),
    Audience("slipping", "Slipping Regulars", "Slipping Regulars", "segment = Slipping Regulars",
             "segment == 'Slipping Regulars'"),
    Audience("potential", "Potential Loyalists", "Potential Loyalists", "segment = Potential Loyalists",
             "segment == 'Potential Loyalists'"),
    Audience("new", "New Customers", "New Customers", "segment = New Customers", "segment == 'New Customers'"),
    Audience("needs_attention", "Needs Attention", "Needs Attention", "segment = Needs Attention",
             "segment == 'Needs Attention'"),
    Audience("at_risk_121_180", "At Risk", "At Risk, 121-180 days", "segment = At Risk and R score = 2 (121-180 days)",
             "segment == 'At Risk' and r_score == 2"),
    Audience("at_risk_181_364_high", "At Risk", "At Risk, 181-364 days, 200+ CU",
             "segment = At Risk and R score = 1 (181-364 days) and 12-month spend >= 200 CU",
             "segment == 'At Risk' and r_score == 1 and monetary_12m_cu >= 200"),
    Audience("at_risk_181_364_low", "At Risk", "At Risk, 181-364 days, < 200 CU",
             "segment = At Risk and R score = 1 and 12-month spend < 200 CU",
             "segment == 'At Risk' and r_score == 1 and monetary_12m_cu < 200"),
    Audience("lost", "Lost", "Lost", "segment = Lost", "segment == 'Lost'"),
]
AUDIENCE_BY_KEY = {a.key: a for a in AUDIENCES}


@dataclass(frozen=True)
class Arm:
    audience: str             # Audience.key
    arm: str
    role: str                 # "Rollout" | "Test cell" | "Not run" (considered and rejected, kept for the record)
    objective: str
    action: str
    timing: str
    channels: str
    use_paid_social: bool     # reach non-subscribers with paid social (costed)
    discount_rate: float      # share of one order's value given back when redeemed
    uplift_pp: float          # assumed ITT lift in 90-day repurchase rate vs holdout, percentage points
    audience_share: float     # share of the audience's experiment population assigned to this arm
    kpi: str
    decision_rule: str
    risk: str


PLAN: list[Arm] = [
    Arm("champions", "Autumn early access", "Rollout",
        "Keep the 14% of customers who bring in over half of 12-month revenue, without discounting",
        "Personal 48-hour early-access link to the autumn collection; free click-and-collect on the early-access order. No % discount.",
        "2020-09-29, two days before the public launch",
        "Email (subscribers) + personalised member-app message (treated customers only)",
        False, 0.0, 0.5, 0.90,
        "90-day repurchase rate vs holdout (revenue per customer secondary)",
        "Keep as an always-on Champions benefit if the pooled campaign lift is positive; segment read is directional",
        "83% buy within 90 days anyway: a discount would mostly pay for orders we get anyway"),
    Arm("loyal", "Basket-building picks", "Rollout",
        "Frequent buyers with small baskets (AOV ~24 CU): add one more item per order",
        "'Complete your order' picks (accessories, basics multipacks) and a free-delivery threshold reminder. No discount.",
        "Week 2 (from 2020-10-05)",
        "Email (subscribers) + member app",
        False, 0.0, 0.5, 0.90,
        "90-day repurchase rate; AOV vs holdout (secondary)",
        "Directional only (too small to read alone); judge AOV in the next quarterly review",
        "Low value per order: never fund paid media here"),
    Arm("loyal", "Picks + 10% voucher", "Not run",
        "Considered: a voucher on the next order",
        "Same picks + voucher worth 10% of the next order",
        "-", "Email", False, 0.10, 1.5, 0.0,
        "-", "Not run this season: break-even far above any plausible lift and the cell could not be read", "-"),
    Arm("slipping", "Purchase-cycle reminder: autumn picks", "Rollout",
        "Early warning for valuable regulars: 5+ orders a year, now 61-120 days quiet - typically twice their usual gap between orders",
        "'New in for autumn' picks from the categories they bought most, sent in week 1; second touch on day 10 to those who have not bought since launch. No discount.",
        "Week 1 (2020-09-28), reminder day 10",
        "Email (subscribers) + member app",
        False, 0.0, 1.5, 0.90,
        "90-day repurchase rate vs holdout",
        "Make it an always-on trigger (fires when a regular passes 1.5x their usual gap) if lift > 0 at day 90",
        "Contact pressure on a valuable group: respect the weekly cap"),
    Arm("potential", "Complete-the-look recommendations", "Rollout",
        "Build the habit: the second and third order while the brand is top of mind",
        "Personalised 'complete the look' email from the last order's category; customers who came back after 12+ months get a 'welcome back' version. No discount.",
        "Week 1 (from 2020-09-28)",
        "Email (subscribers) + member app",
        False, 0.0, 1.0, 0.90,
        "90-day repurchase rate vs holdout",
        "Directional only; keep if the pooled lift is positive",
        "Content-only lift may be small"),
    Arm("new", "Welcome journey", "Rollout",
        "Win the second order: the biggest drop-off on the order ladder",
        "3-email journey over 30 days (membership benefits, picks from the first order's category, delivery / returns / click-and-collect explained). No discount.",
        "Starts day 7 after the first order; customers already in the segment enter in week 1",
        "Email (subscribers) + paid social for the two thirds not reachable by email",
        True, 0.0, 1.5, 0.45,
        "Second-order rate within 90 days vs holdout",
        "Keep the journey always-on if its lift clears its break-even (paid social cost)",
        "Paid-social match rates for new customers"),
    Arm("new", "Welcome journey + 10% off 2nd order", "Test cell",
        "Learn whether a second-order coupon pays for itself",
        "Same journey + 10% off the second order, valid 30 days",
        "Same as the journey (parallel cell)",
        "Email (subscribers) + paid social",
        True, 0.10, 3.0, 0.45,
        "Second-order rate within 90 days vs journey-only cell and holdout",
        "Roll out the coupon only if its lift over the journey-only cell has a 95% lower bound above break-even; also track 12-month value",
        "The 90-day view understates a second order's value (repeat customers keep buying)"),
    Arm("needs_attention", "Summer-to-autumn new-arrivals edit", "Rollout",
        "Re-engage summer buyers (61-120 days quiet) before they lapse",
        "New-arrivals edit that bridges from what they bought in summer (swimwear, underwear) to autumn basics; one-order customers get the second-order version of the welcome email. No discount.",
        "Week 1 (from 2020-09-28); reminder in week 3 to those who have not bought",
        "Email (subscribers) + member app",
        False, 0.0, 1.0, 0.90,
        "90-day repurchase rate vs holdout",
        "Directional only; keep if the pooled lift is positive",
        "About a third come back on their own in autumn: keep it cheap"),
    Arm("at_risk_121_180", "Win-back content (email only)", "Rollout",
        "Recently lapsed valuable customers; 44% come back on their own, so no paid media",
        "Personalised 'we picked these for you' email from each customer's own top categories (this group last bought during the spring 2020 store closure and has no seasonal skew). No discount.",
        "Week 1 (from 2020-09-28); reminder on day 7 to those who have not bought",
        "Email (subscribers only)",
        False, 0.0, 1.0, 0.90,
        "90-day repurchase rate and revenue per customer vs holdout",
        "Directional; feeds the pooled read",
        "Low risk, near-zero cost"),
    Arm("at_risk_181_364_high", "Win-back content + paid social", "Rollout",
        "Long-lapsed but high-spending customers: worth paying to reach the ~70% not on email",
        "Personalised win-back leading with outerwear and knitwear (they last bought in autumn / winter 2019-20 and over-index on both); paid-social retargeting to non-subscribers with the same creative. No discount.",
        "Week 1 (from 2020-09-28); retargeting runs 3 weeks, stops for anyone who buys",
        "Email (subscribers) + paid social (non-subscribers, holdout uploaded as an exclusion audience)",
        True, 0.0, 1.0, 0.60,
        "90-day repurchase rate vs holdout",
        "Keep paid social for this audience only if the measured lift clears its break-even",
        "Paid-social match rate and frequency fatigue"),
    Arm("at_risk_181_364_high", "Win-back + 10% off", "Test cell",
        "Learn whether a modest offer pays for itself where few customers come back alone",
        "Same win-back message + 10% off one order, valid 14 days",
        "Week 1, in parallel with the content cell",
        "Email (subscribers) + paid social",
        True, 0.10, 2.5, 0.30,
        "90-day repurchase rate vs content cell and holdout",
        "Scale in the next wave only if the lift over the content cell has a 95% lower bound above break-even",
        "Coupons also go to the ~1 in 4 who would have bought anyway"),
    Arm("at_risk_181_364_high", "Win-back + 20% off", "Not run",
        "Considered: a deep offer",
        "Same message + 20% off one order",
        "-", "Email + paid social", True, 0.20, 3.5, 0.0,
        "-", "Not run: under one-order value it needs a lift no win-back campaign delivers", "-"),
    Arm("at_risk_181_364_low", "Win-back content (email only)", "Rollout",
        "Long-lapsed, lower-spend customers: stay present at near-zero cost",
        "Knitwear-led win-back email (their strongest category), lighter version; no paid media, no discount",
        "Week 1 (from 2020-09-28)",
        "Email (subscribers only)",
        False, 0.0, 0.5, 0.90,
        "90-day repurchase rate vs holdout (directional)",
        "Directional only",
        "Near-zero cost"),
    Arm("lost", "One reactivation email", "Rollout",
        "Cheap last attempt, then move non-responders to a low-frequency list",
        "Single 'see what's new' email in week 4 leading with kids' autumn and menswear (their over-indexed departments); suppressed from paid media",
        "Week 4 (from 2020-10-19)",
        "Email (subscribers only)",
        False, 0.0, 0.2, 0.90,
        "90-day reactivation rate vs holdout (directional)",
        "Non-responders after 90 days move to a quarterly newsletter cadence",
        "Old addresses: watch spam complaints"),
]

NO_CAMPAIGN = {
    "Hibernating": "No autumn campaign spend: business-as-usual newsletter only (which the holdout also receives), so there is nothing to measure",
    "Review List": "No offers or paid media until CRM / retail ops have reviewed the accounts; service messages continue",
}


def plan_frame() -> pd.DataFrame:
    df = pd.DataFrame([asdict(a) for a in PLAN])
    df["segment"] = df["audience"].map(lambda k: AUDIENCE_BY_KEY[k].segment)
    df["audience_label"] = df["audience"].map(lambda k: AUDIENCE_BY_KEY[k].label)
    df["holdout_share"] = HOLDOUT_SHARE
    return df


def audience_frame() -> pd.DataFrame:
    return pd.DataFrame([asdict(a) for a in AUDIENCES])


# --------------------------------------------------------------------------- inputs
def audience_inputs() -> pd.DataFrame:
    """Per-audience numbers the economics need.

    Today's size, reach and AOV come from the 2020-09-22 snapshot. Business-as-usual behaviour
    comes from the same audience rule applied at 2019-09-22 (same season). Where that backtest
    audience is too small to be representative (< 10,000: Lost, because the data starts a year
    earlier) the 2020-06-24 backtest is used. Both backtests' rates are kept for the bands.
    """
    paths = get_paths()
    cur = pd.read_parquet(paths.marts / "customer_rfm.parquet", filters=[("snapshot_name", "==", "current")],
                          columns=["segment", "r_score", "monetary_12m_cu", "frequency_12m", "monetary_12m_cents",
                                   "orders_to_date", "revenue_to_date_cents", "is_newsletter_subscriber"])
    out = pd.read_parquet(paths.marts / "customer_outcomes_90d.parquet",
                          columns=["snapshot_name", "segment", "r_score", "monetary_12m_cu", "purchased_next_90d",
                                   "revenue_next_90d_cents", "orders_next_90d"])
    rows = []
    for a in AUDIENCES:
        c = cur.query(a.query)
        orders = c["frequency_12m"].sum()
        aov = (c["monetary_12m_cents"].sum() / orders / 100) if orders > 0 else \
            c["revenue_to_date_cents"].sum() / c["orders_to_date"].sum() / 100
        row = {"audience": a.key, "segment": a.segment, "audience_label": a.label, "customers": len(c),
               "newsletter_share": float(c["is_newsletter_subscriber"].mean()), "aov_cu": float(aov),
               "revenue_12m_cu": float(c["monetary_12m_cu"].sum())}
        for snap in ("backtest_seasonal", "backtest_recent"):
            b = out[out.snapshot_name == snap].query(a.query)
            key = snap.replace("backtest_", "")
            buyers = b["purchased_next_90d"].sum()
            rev = b["revenue_next_90d_cents"] / 100
            row[f"n_{key}"] = len(b)
            row[f"baseline_rate_{key}"] = float(b["purchased_next_90d"].mean()) if len(b) else np.nan
            row[f"revenue_per_buyer_{key}"] = float(rev.sum() / buyers) if buyers else np.nan
            row[f"sd_revenue_{key}"] = float(rev.std()) if len(b) > 1 else np.nan
            row[f"revenue_per_customer_{key}"] = float(rev.mean()) if len(b) else np.nan
        use = "recent" if row["n_seasonal"] < 10_000 else "seasonal"
        row["baseline_basis"] = f"backtest_{use}"
        for col in ("baseline_rate", "revenue_per_buyer", "sd_revenue", "revenue_per_customer"):
            row[col] = row[f"{col}_{use}"]
        rows.append(row)
    return pd.DataFrame(rows)


def category_focus(n: int = 2, min_index: float = 120, min_share: float = 0.05) -> pd.Series:
    """Categories a segment clearly over-indexes on: affinity index >= 120 AND >= 5% of the
    segment's revenue (garment groups and departments). Segments with none mirror the overall mix."""
    mix = pd.read_parquet(get_paths().marts / "segment_mix.parquet")
    out = {}
    for seg, d in mix.groupby("segment"):
        g = d[d.dimension.isin(["garment_group", "index_group"]) & (d.value != "Unknown")
              & (d.affinity_index >= min_index) & (d.segment_share >= min_share)]
        g = g.sort_values("affinity_index", ascending=False).head(n)
        parts = [f"{v}{' dept.' if dim == 'index_group' else ''} ({i:.0f})" for v, dim, i in
                 zip(g["value"], g["dimension"], g["affinity_index"])]
        out[seg] = ", ".join(parts) if parts else FOCUS_FALLBACK
    return pd.Series(out, name="category_focus")


FOCUS_FALLBACK = "their own top categories (no category at index >= 120)"


def audience_category_focus(n: int = 2, min_index: float = 120, min_share: float = 0.05) -> pd.Series:
    """Same rule as category_focus(), per campaign audience (data/marts/audience_mix.parquet)."""
    mix = pd.read_parquet(get_paths().marts / "audience_mix.parquet")
    out = {}
    for key, d in mix.groupby("audience"):
        g = d[(d.value != "Unknown") & (d.affinity_index >= min_index) & (d.audience_share >= min_share)]
        g = g.sort_values("affinity_index", ascending=False).head(n)
        parts = [f"{v}{' dept.' if dim == 'index_group' else ''} ({i:.0f})" for v, dim, i in
                 zip(g["value"], g["dimension"], g["affinity_index"])]
        out[key] = ", ".join(parts) if parts else FOCUS_FALLBACK
    return pd.Series(out, name="category_focus")


# --------------------------------------------------------------------------- economics
def default_assumptions(cfg: dict | None = None) -> dict:
    e = (cfg or load_config())["economics"]
    return {
        "contribution_margin": e["contribution_margin"],
        "incremental_value": e["incremental_value"],
        "redemption_share": e["baseline_redemption_share"],
        "email_cost": e["contact_cost_cu"]["email"],
        "paid_social_cost": e["contact_cost_cu"]["paid_social"],
        "uplift_factor": 1.0,
        "alpha": e["alpha"],
        "power": e["power"],
    }


def scenarios(cfg: dict | None = None) -> dict[str, dict]:
    base = default_assumptions(cfg)
    e = (cfg or load_config())["economics"]["scenarios"]
    return {name: {**base, **over} for name, over in e.items()}


def audience_reach(arms: pd.DataFrame) -> pd.Series:
    """An audience's experiment population includes non-subscribers if any of its live arms uses paid social."""
    live = arms[arms["role"] != "Not run"]
    return live.groupby("audience")["use_paid_social"].any().reindex(arms["audience"].unique()).fillna(False)


def economics(arms: pd.DataFrame, inputs: pd.DataFrame, assumptions: dict) -> pd.DataFrame:
    """Expected 90-day economics per arm. `arms` needs the Arm columns (editable in the dashboard)."""
    df = arms.merge(inputs.drop(columns=["segment", "audience_label"], errors="ignore"), on="audience", how="left")
    df["audience_uses_paid_social"] = df["audience"].map(audience_reach(arms)).astype(bool)
    m = assumptions["contribution_margin"]
    rho = assumptions["redemption_share"]
    reach_share = np.where(df["audience_uses_paid_social"], 1.0, df["newsletter_share"])
    population = df["customers"] * reach_share
    contacted = population * df["audience_share"]
    emails = contacted * (df["newsletter_share"] / reach_share)
    social = np.where(df["use_paid_social"], contacted - emails, 0.0)
    emails = np.where(df["use_paid_social"], emails, contacted)   # email-only arms only reach subscribers anyway
    uplift = df["uplift_pp"] * assumptions.get("uplift_factor", 1.0) / 100.0
    value = df["aov_cu"] if assumptions["incremental_value"] == "one_order" else df["revenue_per_buyer"]
    inc_buyers = contacted * uplift
    inc_revenue = inc_buyers * value
    contribution = inc_revenue * m
    redemptions = np.where(df["discount_rate"] > 0, contacted * (df["baseline_rate"] * rho + uplift), 0.0)
    discount_cost = redemptions * df["discount_rate"] * df["aov_cu"]
    contact_cost = emails * assumptions["email_cost"] + social * assumptions["paid_social_cost"]
    total_cost = discount_cost + contact_cost
    net = contribution - total_cost
    head = np.where(df["use_paid_social"],
                    (df["newsletter_share"] * assumptions["email_cost"] + (1 - df["newsletter_share"]) * assumptions["paid_social_cost"]),
                    assumptions["email_cost"])
    denom = value * m - df["discount_rate"] * df["aov_cu"]
    numer = df["discount_rate"] * df["aov_cu"] * df["baseline_rate"] * rho + head
    breakeven = np.where(denom > 0, numer / denom, np.inf)
    holdout_n = population * df["holdout_share"]
    a, pw = assumptions["alpha"], assumptions["power"]
    mde_rate = np.array([power.mde_rate(p0, n_t, n_c, a, pw) if n_t > 0 else np.nan
                         for p0, n_t, n_c in zip(df["baseline_rate"], contacted, holdout_n)])
    mde_rev = np.array([power.mde_mean(sd, n_t, n_c, a, pw) if n_t > 0 else np.nan
                        for sd, n_t, n_c in zip(df["sd_revenue"], contacted, holdout_n)])
    return df.assign(
        experiment_population=population,
        holdout=holdout_n,
        contacted=contacted,
        contacted_email=emails,
        contacted_paid_social=social,
        value_per_incremental_buyer_cu=value,
        incremental_buyers=inc_buyers,
        incremental_revenue_cu=inc_revenue,
        contribution_cu=contribution,
        redemptions=redemptions,
        discount_cost_cu=discount_cost,
        contact_cost_cu=contact_cost,
        total_cost_cu=total_cost,
        net_profit_cu=net,
        breakeven_uplift_pp=breakeven * 100,
        # profit given up by not treating the holdout with the rollout arm
        holdout_opportunity_cost_cu=np.where(df["role"] == "Rollout", holdout_n * (uplift * value * m - head), 0.0),
        mde_rate_pp=mde_rate * 100,
        mde_revenue_cu=mde_rev,
        readable_alone=(mde_rate * 100) <= df["uplift_pp"] * assumptions.get("uplift_factor", 1.0),
        powered_for_decision=np.where(df["role"] == "Test cell", (mde_rate * 100) <= (2 / 3) * breakeven * 100, False),
    )


def scenario_table(inputs: pd.DataFrame, arms: pd.DataFrame | None = None, cfg: dict | None = None) -> pd.DataFrame:
    """Net profit and cost per arm under the pessimistic / base / optimistic assumption sets."""
    arms = plan_frame() if arms is None else arms
    rows = []
    for name, ass in scenarios(cfg).items():
        e = economics(arms, inputs, ass)
        e = e[e.role != "Not run"]
        for role, g in e.groupby("role"):
            rows.append({"scenario": name, "role": role, "contacted": g.contacted.sum(), "total_cost_cu": g.total_cost_cu.sum(),
                         "incremental_revenue_cu": g.incremental_revenue_cu.sum(), "net_profit_cu": g.net_profit_cu.sum()})
    return pd.DataFrame(rows)


def budget_lines(econ: pd.DataFrame) -> pd.DataFrame:
    """The budget ask by cost type (base case), plus two memo lines."""
    ass = default_assumptions()
    live = econ[econ.role != "Not run"]
    roll, test = live[live.role == "Rollout"], live[live.role == "Test cell"]
    rows = [
        {"line": "Email sends (all rollout arms)", "cost_cu": float(roll.contacted_email.sum() * ass["email_cost"]),
         "note": f"{roll.contacted_email.sum():,.0f} contacts x {ass['email_cost']} CU"},
        {"line": "Paid social (New Customers journey, At Risk 181-364 days 200+ CU)",
         "cost_cu": float(roll.contacted_paid_social.sum() * ass["paid_social_cost"]),
         "note": f"{roll.contacted_paid_social.sum():,.0f} non-subscribers x {ass['paid_social_cost']} CU"},
        {"line": "Test cells: discounts", "cost_cu": float(test.discount_cost_cu.sum()),
         "note": "coupon value on all redeemed orders in the two test cells"},
        {"line": "Test cells: contacts", "cost_cu": float(test.contact_cost_cu.sum()), "note": "email + paid social for the test cells"},
    ]
    total = sum(r["cost_cu"] for r in rows)
    rows.append({"line": "Total budget ask", "cost_cu": total, "note": "cash cost of the autumn wave"})
    rows.append({"line": "Memo: profit given up by holding out 10%", "cost_cu": float(roll.holdout_opportunity_cost_cu.sum()),
                 "note": "holdout x assumed lift x one-order value x margin (the price of being able to measure)"})
    rows.append({"line": "Memo: expected net of test cells", "cost_cu": float(test.net_profit_cu.sum()),
                 "note": "negative = what we expect to pay to learn whether the offers work"})
    return pd.DataFrame(rows)


def allocate_budget(econ: pd.DataFrame, budget_cu: float) -> pd.DataFrame:
    """Fund rollout arms with positive expected net profit, best net profit per CU first.

    Near-free content arms always come first; the ranking matters for the arms that spend
    money (paid social). A partly funded arm runs on a random subset of its audience.
    Test cells are a fixed learning cost and are listed separately.
    """
    cands = econ[(econ["role"] == "Rollout") & (econ["net_profit_cu"] > 0)].copy()
    cands["profit_per_cu"] = cands["net_profit_cu"] / cands["total_cost_cu"].where(cands["total_cost_cu"] > 0)
    cands = cands.sort_values("profit_per_cu", ascending=False)
    remaining = budget_cu
    shares = []
    for _, row in cands.iterrows():
        cost = row["total_cost_cu"]
        share = 1.0 if cost <= remaining else max(0.0, remaining / cost)
        shares.append(share)
        remaining -= share * cost
    cands["funded_share"] = shares
    cands["funded_cost_cu"] = cands["funded_share"] * cands["total_cost_cu"]
    cands["funded_net_profit_cu"] = cands["funded_share"] * cands["net_profit_cu"]
    cands["funded_incremental_revenue_cu"] = cands["funded_share"] * cands["incremental_revenue_cu"]
    return cands


def pooled_read(econ: pd.DataFrame, assumptions: dict | None = None) -> dict:
    """Campaign-wide read: every audience keeps the same 10% holdout, so treated vs holdout has the
    same audience mix. The estimator is still stratified (population-weighted within-audience
    differences); this gives its MDE and the lift expected if every rollout arm hits its assumption."""
    ass = assumptions or default_assumptions()
    live = econ[econ.role != "Not run"]
    aud = live.groupby("audience").agg(pop=("experiment_population", "first"), p0=("baseline_rate", "first"),
                                       share=("holdout_share", "first"))
    w = aud["pop"] / aud["pop"].sum()
    # stratified SE: sum_w^2 * var(diff_s)
    treated = live.groupby("audience")["contacted"].sum()
    var = (w ** 2 * aud["p0"] * (1 - aud["p0"]) * (1 / treated + 1 / (aud["pop"] * aud["share"]))).sum()
    mde = power.z_total(ass["alpha"], ass["power"]) * np.sqrt(var)
    lift = (live["contacted"] * live["uplift_pp"] / 100).sum() / treated.sum()
    return {"holdout_share": HOLDOUT_SHARE, "population": int(round(aud["pop"].sum())),
            "holdout_customers": int(round((aud["pop"] * aud["share"]).sum())),
            "baseline_rate": round(float((w * aud["p0"]).sum()), 4),
            "mde_rate_pp": round(float(100 * mde), 3), "expected_lift_pp": round(float(100 * lift), 3),
            "detectable": bool(mde <= lift)}
