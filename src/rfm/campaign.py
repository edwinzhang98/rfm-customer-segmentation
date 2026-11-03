"""Autumn campaign plan: one action per segment, plus the economics behind it.

Everything a CRM colleague needs to execute (audience, action, timing, channel,
category, KPI, holdout) lives in ``PLAN`` so the dashboard, the report and
docs/campaign_plan.md all show the same plan.

Economics model (per arm, 90-day horizon, money in CU):
    experiment population = customers we can reach: newsletter subscribers, plus everyone
                         else when the segment's plan uses paid social
    contacted          = population x the arm's audience share (the rest of the population is
                         split between other arms and the holdout, which gets no campaign)
    incremental buyers = contacted x assumed uplift (absolute, in 90-day repurchase rate)
    incremental revenue= incremental buyers x 90-day revenue per buyer (backtest)
    gross profit       = incremental revenue x gross margin
    discount cost      = redemptions x discount rate x segment AOV, where
                         redemptions = contacted x (baseline rate x redemption share + uplift)
                         (coupons are also used by customers who would have bought anyway)
    contact cost       = emails x email cost + paid-social audience x paid-social cost
    net profit         = gross profit - discount cost - contact cost
    break-even uplift  = (discount x AOV x baseline x redemption share + contact cost per head)
                         / (revenue per buyer x margin - discount x AOV)
All uplift values are planning assumptions, not measurements: the holdout exists to
replace them with measured numbers.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from . import power
from .config import get_paths, load_config

LAUNCH_DATE = "2020-09-28"   # Monday after the 2020-09-22 snapshot
READ_DATE = "2020-12-27"     # launch + 90 days (final read-out); interim read on day 30


@dataclass(frozen=True)
class Arm:
    segment: str
    arm: str
    role: str                 # "Rollout" (recommended) or "Test cell" (learn before scaling)
    objective: str
    action: str
    timing: str
    channels: str
    use_paid_social: bool     # reach non-subscribers with paid social (costed)
    discount_rate: float      # share of one order's value given back when redeemed
    uplift_pp: float          # assumed absolute lift in 90-day repurchase rate, percentage points
    kpi: str
    guardrail: str
    risk: str
    holdout_share: float      # share of the segment's experiment population kept out of the campaign
    audience_share: float     # share of the experiment population that gets this arm


PLAN: list[Arm] = [
    Arm(
        segment="Champions",
        arm="Autumn early access",
        role="Rollout",
        objective="Keep the 14% of customers who bring in over half of 12-month revenue; no discounting",
        action="48-hour early access to the autumn collection (lead with dresses and blouses, which they over-index on) + invite to an in-store styling evening for omnichannel shoppers. No % discount.",
        timing="Email 2020-09-29, two days before public launch; event invite in week 2",
        channels="Email (subscribers); member app/web banner for everyone else (free, not costed)",
        use_paid_social=False,
        discount_rate=0.0,
        uplift_pp=0.5,
        kpi="90-day revenue per customer vs holdout",
        guardrail="Unsubscribe rate; average order value",
        risk="83% buy within 90 days anyway: a discount here would mostly pay for orders we get anyway",
        holdout_share=0.10,
        audience_share=0.90,
    ),
    Arm(
        segment="Loyal",
        arm="Cross-category picks",
        role="Rollout",
        objective="Turn frequent mid-value buyers into Champions: one more order, bigger baskets",
        action="Personalised picks from categories they over-index on (under-/nightwear, accessories) next to their usual ones; member points reminder. No discount.",
        timing="Week 2 (from 2020-10-05)",
        channels="Email (subscribers); member app/web",
        use_paid_social=False,
        discount_rate=0.0,
        uplift_pp=1.0,
        kpi="90-day repurchase rate and revenue per customer vs holdout",
        guardrail="Unsubscribe rate",
        risk="Content-only lift may be too small to measure in this segment alone (see MDE)",
        holdout_share=0.10,
        audience_share=0.80,
    ),
    Arm(
        segment="Loyal",
        arm="Picks + 10% voucher (test cell)",
        role="Test cell",
        objective="Check whether a voucher lifts spend enough to pay for itself",
        action="Same picks + a voucher worth 10% of the next order, valid 21 days",
        timing="Week 2, in parallel with the rollout cell",
        channels="Email (subscribers); member app/web",
        use_paid_social=False,
        discount_rate=0.10,
        uplift_pp=1.5,
        kpi="Incremental net profit per contacted customer vs rollout cell and holdout",
        guardrail="Discount cost per incremental order",
        risk="68% buy within 90 days anyway: most vouchers would be redeemed on orders we would get anyway",
        holdout_share=0.10,
        audience_share=0.10,
    ),
    Arm(
        segment="Potential Loyalists",
        arm="Complete-the-look recommendations",
        role="Rollout",
        objective="Build the habit: second and third purchase while the brand is still top of mind",
        action="Personalised 'complete the look' email built from the last order's category (sport and basics over-index). No discount.",
        timing="Week 1 (from 2020-09-28)",
        channels="Email (subscribers); member app/web",
        use_paid_social=False,
        discount_rate=0.0,
        uplift_pp=1.0,
        kpi="90-day repurchase rate vs holdout",
        guardrail="Unsubscribe rate",
        risk="Content-only lift may be too small to measure in this segment alone (see MDE)",
        holdout_share=0.10,
        audience_share=0.90,
    ),
    Arm(
        segment="New Customers",
        arm="Welcome journey + 10% off 2nd order",
        role="Rollout",
        objective="Win the second order: the biggest drop-off on the order ladder",
        action="3-email welcome journey over 30 days (membership benefits, picks from their first category, store pickup and returns) with 10% off the second order",
        timing="Starts on day 7 after the first order; customers already in the segment enter in week 1",
        channels="Email (subscribers) + paid social for the two thirds not reachable by email",
        use_paid_social=True,
        discount_rate=0.10,
        uplift_pp=3.0,
        kpi="Second-order rate within 90 days vs holdout",
        guardrail="Discount cost per incremental second order",
        risk="A second order is worth more than its first 90 days (see cohort LTV): the 90-day view understates payback",
        holdout_share=0.15,
        audience_share=0.85,
    ),
    Arm(
        segment="Needs Attention",
        arm="Summer-to-autumn new-arrivals edit",
        role="Rollout",
        objective="Re-engage summer buyers (61-120 days quiet) before they lapse",
        action="New-arrivals edit that bridges from what they bought in summer (swimwear, underwear) to autumn basics. No discount.",
        timing="Week 1 (from 2020-09-28); reminder in week 3 to non-buyers",
        channels="Email (subscribers); member app/web",
        use_paid_social=False,
        discount_rate=0.0,
        uplift_pp=1.0,
        kpi="90-day repurchase rate vs holdout",
        guardrail="Unsubscribe rate",
        risk="About a third come back on their own in autumn: keep it cheap",
        holdout_share=0.10,
        audience_share=0.90,
    ),
    Arm(
        segment="At Risk",
        arm="Win-back: autumn knitwear & outerwear picks",
        role="Rollout",
        objective="Win back valuable customers who went quiet 4-12 months ago (highest AOV of all segments)",
        action="Personalised win-back featuring knitwear and outerwear, the categories they over-index on (they last bought in winter). No discount in the rollout cell.",
        timing="Week 1 (from 2020-09-28); reminder on day 7 to non-openers",
        channels="Email (subscribers) + paid social retargeting for the ~65% not reachable by email",
        use_paid_social=True,
        discount_rate=0.0,
        uplift_pp=1.0,
        kpi="90-day repurchase rate and revenue per customer vs holdout",
        guardrail="Paid-social cost per incremental buyer",
        risk="Paid-social match rates and creative fatigue; lift may be small",
        holdout_share=0.15,
        audience_share=0.65,
    ),
    Arm(
        segment="At Risk",
        arm="Win-back + 10% off (test cell)",
        role="Test cell",
        objective="Learn whether a modest offer pays for itself in this segment",
        action="Same win-back message + 10% off one order, valid 14 days",
        timing="Week 1, in parallel with the rollout cell",
        channels="Email (subscribers) + paid social",
        use_paid_social=True,
        discount_rate=0.10,
        uplift_pp=2.0,
        kpi="Incremental net profit per contacted customer vs rollout cell and holdout",
        guardrail="Discount cost per incremental buyer",
        risk="About a third would buy anyway, so much of the coupon cost goes to non-incremental orders",
        holdout_share=0.15,
        audience_share=0.10,
    ),
    Arm(
        segment="At Risk",
        arm="Win-back + 20% off (test cell)",
        role="Test cell",
        objective="Measure the response to a deep offer before anyone scales it",
        action="Same win-back message + 20% off one order, valid 14 days",
        timing="Week 1, in parallel with the rollout cell",
        channels="Email (subscribers) + paid social",
        use_paid_social=True,
        discount_rate=0.20,
        uplift_pp=3.0,
        kpi="Incremental net profit per contacted customer vs rollout cell and holdout",
        guardrail="Discount cost per incremental buyer",
        risk="Needs a much larger lift than the 10% cell to break even: small cell only",
        holdout_share=0.15,
        audience_share=0.10,
    ),
    Arm(
        segment="Hibernating",
        arm="Seasonal newsletter only",
        role="Rollout",
        objective="Stay present at near-zero cost; no discount budget for low-value lapsing customers",
        action="Regular autumn newsletter with a basics restock theme (underwear, nightwear, socks over-index)",
        timing="Week 4 (from 2020-10-19)",
        channels="Email (subscribers only); no paid media",
        use_paid_social=False,
        discount_rate=0.0,
        uplift_pp=0.3,
        kpi="90-day repurchase rate vs holdout (directional only)",
        guardrail="Unsubscribe and spam-complaint rate",
        risk="Effect is likely too small to measure; cost is close to zero",
        holdout_share=0.10,
        audience_share=0.90,
    ),
    Arm(
        segment="Lost",
        arm="One reactivation email",
        role="Rollout",
        objective="Cheap last attempt, then move non-responders to a low-frequency list",
        action="Single 'see what's new' email featuring kids' autumn and menswear (their over-indexed departments); suppressed from paid media",
        timing="Week 4 (from 2020-10-19)",
        channels="Email (subscribers only)",
        use_paid_social=False,
        discount_rate=0.0,
        uplift_pp=0.2,
        kpi="90-day reactivation rate vs holdout (directional only)",
        guardrail="Spam-complaint rate (old addresses)",
        risk="Too small to detect at any affordable holdout; keep cost at ~0",
        holdout_share=0.10,
        audience_share=0.90,
    ),
]


def plan_frame() -> pd.DataFrame:
    return pd.DataFrame([asdict(a) for a in PLAN])


# --------------------------------------------------------------------------- inputs
def segment_inputs() -> pd.DataFrame:
    """Per-segment numbers the economics need, from the marts.

    Business-as-usual behaviour comes from the season-matched backtest (2019-09-22).
    Lost has only ~3k customers in that backtest (the data starts one year earlier),
    so Lost uses the 2020-06-24 backtest instead.
    """
    paths = get_paths()
    prof = pd.read_parquet(paths.marts / "segment_profile.parquet")
    out = pd.read_parquet(paths.marts / "segment_outcomes_90d.parquet")
    seasonal = out[out.snapshot_name == "backtest_seasonal"].set_index("segment")
    recent = out[out.snapshot_name == "backtest_recent"].set_index("segment")
    rows = []
    for _, p in prof.iterrows():
        seg = p["segment"]
        use_recent = seasonal.loc[seg, "customers"] < 10_000 if seg in seasonal.index else True
        base = recent.loc[seg] if use_recent else seasonal.loc[seg]
        aov = p["aov_12m_cu"] if pd.notna(p["aov_12m_cu"]) else p["aov_2y_cu"]
        rows.append({
            "segment": seg,
            "customers": int(p["customers"]),
            "newsletter_share": float(p["pct_newsletter"]),
            "aov_cu": float(aov),
            "baseline_rate": float(base["repurchase_rate"]),
            "revenue_per_buyer_cu": float(base["revenue_per_buyer_cu"]),
            "sd_revenue_cu": float(base["sd_revenue_per_customer_cu"]),
            "revenue_per_customer_cu": float(base["revenue_per_customer_cu"]),
            "baseline_basis": "backtest_recent" if use_recent else "backtest_seasonal",
        })
    return pd.DataFrame(rows)


def category_focus(n: int = 2, min_share: float = 0.04) -> pd.Series:
    """Top garment groups a segment over-indexes on (>= 4% of its revenue), plus any
    department (index group) with index >= 115, e.g. 'Knitwear (124), Outdoor (121)'."""
    mix = pd.read_parquet(get_paths().marts / "segment_mix.parquet")
    out = {}
    for seg, d in mix.groupby("segment"):
        g = d[(d.dimension == "garment_group") & (d.segment_share >= min_share)]
        g = g.sort_values("affinity_index", ascending=False).head(n)
        parts = [f"{v} ({i:.0f})" for v, i in zip(g["value"], g["affinity_index"])]
        dept = d[(d.dimension == "index_group") & (d.affinity_index >= 115) & (d.segment_share >= 0.02)]
        parts += [f"{v} dept. ({i:.0f})" for v, i in zip(dept["value"], dept["affinity_index"])]
        out[seg] = ", ".join(parts)
    return pd.Series(out, name="category_focus")


# --------------------------------------------------------------------------- economics
def default_assumptions(cfg: dict | None = None) -> dict:
    e = (cfg or load_config())["economics"]
    return {
        "gross_margin": e["gross_margin"],
        "redemption_share": e["baseline_redemption_share"],
        "email_cost": e["contact_cost_cu"]["email"],
        "paid_social_cost": e["contact_cost_cu"]["paid_social"],
        "alpha": e["alpha"],
        "power": e["power"],
    }


def segment_reach(arms: pd.DataFrame) -> pd.Series:
    """A segment's experiment population includes non-subscribers if any of its arms uses paid social."""
    return arms.groupby("segment")["use_paid_social"].any()


def economics(arms: pd.DataFrame, inputs: pd.DataFrame, assumptions: dict) -> pd.DataFrame:
    """Expected 90-day economics per arm. `arms` needs the Arm columns (editable in the dashboard)."""
    df = arms.merge(inputs, on="segment", how="left")
    df["segment_uses_paid_social"] = df["segment"].map(segment_reach(arms))
    m = assumptions["gross_margin"]
    rho = assumptions["redemption_share"]
    reach_share = np.where(df["segment_uses_paid_social"], 1.0, df["newsletter_share"])
    population = df["customers"] * reach_share
    contacted = population * df["audience_share"]
    email_share_of_pop = df["newsletter_share"] / reach_share
    emails = contacted * email_share_of_pop
    social = contacted - emails
    uplift = df["uplift_pp"] / 100.0
    inc_buyers = contacted * uplift
    inc_revenue = inc_buyers * df["revenue_per_buyer_cu"]
    gross_profit = inc_revenue * m
    redemptions = np.where(df["discount_rate"] > 0, contacted * (df["baseline_rate"] * rho + uplift), 0.0)
    discount_cost = redemptions * df["discount_rate"] * df["aov_cu"]
    contact_cost = emails * assumptions["email_cost"] + social * assumptions["paid_social_cost"]
    total_cost = discount_cost + contact_cost
    net = gross_profit - total_cost
    contact_per_head = np.divide(contact_cost, contacted, out=np.zeros(len(df)), where=contacted > 0)
    denom = df["revenue_per_buyer_cu"] * m - df["discount_rate"] * df["aov_cu"]
    numer = df["discount_rate"] * df["aov_cu"] * df["baseline_rate"] * rho + contact_per_head
    breakeven = np.where(denom > 0, numer / denom, np.inf)
    holdout_n = population * df["holdout_share"]
    mde = [power.mde_rate(p0, n_t, n_c, assumptions["alpha"], assumptions["power"])
           for p0, n_t, n_c in zip(df["baseline_rate"], contacted, holdout_n)]
    return df.assign(
        experiment_population=population,
        holdout=holdout_n,
        contacted_email=emails,
        contacted_paid_social=social,
        contacted=contacted,
        incremental_buyers=inc_buyers,
        incremental_revenue_cu=inc_revenue,
        incremental_gross_profit_cu=gross_profit,
        redemptions=redemptions,
        discount_cost_cu=discount_cost,
        contact_cost_cu=contact_cost,
        total_cost_cu=total_cost,
        net_profit_cu=net,
        roi=np.divide(net, total_cost, out=np.full(len(df), np.nan), where=total_cost > 0),
        breakeven_uplift_pp=breakeven * 100,
        relative_uplift=uplift / df["baseline_rate"],
        mde_vs_holdout_pp=np.array(mde) * 100,
        detectable=np.array(mde) * 100 <= df["uplift_pp"],
    )


def allocate_budget(econ: pd.DataFrame, budget_cu: float) -> pd.DataFrame:
    """Fund rollout arms with positive expected net profit, best profit per CU spent first.

    A partly funded arm runs on a random subset of its audience (cost and profit scale
    linearly). Test cells are small, fixed learning costs and are listed separately.
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
