import numpy as np
import pandas as pd
import streamlit as st

from common import callout, chart, fmt_cu, fmt_n, how_to_read, mart, metrics, note, page_header, pct, table
from rfm import campaign as CP
from rfm import charts as C
from rfm import power as PW

page_header(
    "Campaign Plan & Measurement",
    "What does each audience get, when and through which channel; what does it cost; and how will we know whether it worked?",
)

m = metrics()
camp = m["campaign"]
inputs = mart("campaign_inputs")
plan = CP.plan_frame()
focus = CP.category_focus()
aud = CP.audience_frame().set_index("key")

# ----------------------------------------------------------------------------- 1. plan
st.subheader("1. The plan: one row per audience and arm")
tbl = plan.assign(rule=plan.audience.map(aud["rule"]), category_focus=plan.segment.map(focus),
                  discount=plan.discount_rate.map(lambda v: "none" if v == 0 else f"{100 * v:.0f}% off one order"),
                  assumed_lift=plan.uplift_pp.map(lambda v: f"+{v:.1f} pp"),
                  split=[("-" if r.role == "Not run" else f"{100 * r.audience_share:.0f}% / holdout {100 * r.holdout_share:.0f}%")
                         for r in plan.itertuples()])
tbl = tbl[["audience_label", "rule", "arm", "role", "objective", "action", "timing", "channels", "category_focus", "discount",
           "assumed_lift", "kpi", "decision_rule", "risk", "split"]]
tbl.columns = ["Audience", "Audience rule", "Arm", "Role", "Goal", "Action", "Timing", "Channel", "Category focus (index)", "Discount",
               "Assumed lift (ITT)", "Primary KPI", "Decision rule", "Risk", "Share of reachable audience"]
no_camp = pd.DataFrame([{"Audience": k, "Arm": "No autumn campaign", "Role": "-", "Goal": v} for k, v in CP.NO_CAMPAIGN.items()])
table(pd.concat([tbl, no_camp], ignore_index=True).fillna(""), hide_index=True, width="stretch", height=470,
             column_config={c: st.column_config.TextColumn(width="large") for c in ["Goal", "Action", "Risk", "Decision rule", "Timing", "Channel"]})
note(f"Launch week of {CP.LAUNCH_DATE}; final read {CP.READ_DATE} (day 90). 'Not run' rows were considered and rejected; they stay in the table "
     "so the reasoning is visible.")
with st.expander("Contact, suppression and journey rules (apply to every arm)", expanded=False):
    st.markdown(
        """
- **Re-score on launch day.** Audiences are rebuilt from the same SQL on 2020-09-28, not taken from the 2020-09-22 extract; the segment at launch is
  the *segment of record* for the analysis, even if the customer moves later.
- **Suppress everywhere:** unsubscribed or bounced addresses, the Review List, the holdout (also uploaded as an exclusion audience in paid social,
  including lookalike seeds), and customers in another live test.
- **Contact cap:** at most one campaign email per customer per week on top of the business-as-usual newsletter.
- **Exit on purchase:** a customer who buys leaves every reminder and retargeting audience within 24 hours.
- **Hand-offs after day 30:** New Customers without a second order -> one-time-buyer version of the journey; Needs Attention / Potential Loyalists
  non-buyers -> win-back content; Lost non-responders after 90 days -> quarterly newsletter cadence.
- **Channel rule:** online-only customers get online creative and are excluded from store invitations; store-only customers get store-led
  creative and no online-only vouchers.
"""
    )

# ----------------------------------------------------------------------------- 2. economics
st.subheader("2. Economics: change the assumptions and see what pays back")
a0 = CP.default_assumptions()
with st.expander("Assumptions shared by every arm", expanded=True):
    c1, c2, c3 = st.columns(3)
    margin = c1.slider("Contribution margin on incremental orders", 0.20, 0.60, float(a0["contribution_margin"]), 0.01,
                       help="Base 40% = H&M gross margin (50.0% FY2020) less ~10 pp fulfilment and returns; to be confirmed with Finance")
    value = c1.radio("Value of one incremental buyer", ["One order at the audience AOV (base)", "Average 90-day buyer (optimistic)"],
                     key="val_basis")
    rho = c2.slider("Coupon use by customers who would buy anyway", 0.0, 1.0, float(a0["redemption_share"]), 0.05,
                    help="The subsidy on orders we would get anyway")
    factor = c2.slider("Scale all assumed lifts by", 0.25, 2.0, 1.0, 0.25, help="0.5 = every lift is half of the planning assumption")
    email_cost = c3.slider("Cost per email (CU)", 0.0, 0.10, float(a0["email_cost"]), 0.005)
    social_cost = c3.slider("Paid social cost per targeted customer (CU)", 0.0, 1.50, float(a0["paid_social_cost"]), 0.05)
assumptions = {**a0, "contribution_margin": margin, "redemption_share": rho, "email_cost": email_cost, "paid_social_cost": social_cost,
               "uplift_factor": factor, "incremental_value": "one_order" if value.startswith("One") else "avg_buyer"}
st.caption("Edit the per-arm assumptions (lift, discount, share of the audience, paid social). Everything below recalculates.")
editable = plan[["audience_label", "arm", "role", "uplift_pp", "discount_rate", "audience_share", "use_paid_social"]]
edited = st.data_editor(
    editable, hide_index=True, width="stretch", key="arm_editor", disabled=["audience_label", "arm", "role"],
    column_config={
        "audience_label": st.column_config.TextColumn("Audience"),
        "arm": st.column_config.TextColumn("Arm"),
        "role": st.column_config.TextColumn("Role"),
        "uplift_pp": st.column_config.NumberColumn("Assumed lift (pp)", min_value=0.0, max_value=20.0, step=0.1, format="%.1f"),
        "discount_rate": st.column_config.NumberColumn("Discount (share of order)", min_value=0.0, max_value=0.5, step=0.05, format="%.2f"),
        "audience_share": st.column_config.NumberColumn("Share of reachable audience", min_value=0.0, max_value=0.9, step=0.05, format="%.2f"),
        "use_paid_social": st.column_config.CheckboxColumn("Paid social for non-subscribers"),
    },
)
arms = plan.drop(columns=["uplift_pp", "discount_rate", "audience_share", "use_paid_social"]).merge(
    edited, on=["audience_label", "arm", "role"])
econ = CP.economics(arms, inputs, assumptions)
live = econ[econ.role != "Not run"]
roll, test = live[live.role == "Rollout"], live[live.role == "Test cell"]
k1, k2, k3, k4 = st.columns(4)
k1.metric("Customers contacted (rollout)", fmt_n(roll.contacted.sum()))
k2.metric("Rollout cost", fmt_cu(roll.total_cost_cu.sum()), f"incremental revenue {fmt_cu(roll.incremental_revenue_cu.sum())}", delta_color="off", delta_arrow="off")
k3.metric("Expected net profit (rollout)", fmt_cu(roll.net_profit_cu.sum()))
k4.metric("Test cells: expected net", fmt_cu(test.net_profit_cu.sum()), f"cost {fmt_cu(test.total_cost_cu.sum())}", delta_color="off", delta_arrow="off")
chart(C.net_profit_by_arm(econ), key="np")
chart(C.breakeven_vs_assumed(econ), key="be")
show = econ[["audience_label", "arm", "role", "contacted", "baseline_rate", "uplift_pp", "breakeven_uplift_pp", "incremental_buyers",
             "incremental_revenue_cu", "discount_cost_cu", "contact_cost_cu", "net_profit_cu"]].copy()
show["baseline_rate"] = (100 * show["baseline_rate"]).round(1)
show = show.round({"contacted": 0, "breakeven_uplift_pp": 2, "incremental_buyers": 0, "incremental_revenue_cu": 0, "discount_cost_cu": 0,
                   "contact_cost_cu": 0, "net_profit_cu": 0})
show.columns = ["Audience", "Arm", "Role", "Contacted", "Buys anyway (%)", "Assumed lift (pp)", "Break-even lift (pp)", "Incremental buyers",
                "Incremental revenue (CU)", "Discount cost (CU)", "Contact cost (CU)", "Net profit (CU)"]
table(show, hide_index=True, width="stretch")
callout("<b>The pattern behind the numbers:</b> a discount is paid on every redeemed order, including orders from customers who would have "
        "bought anyway, and an incremental buyer is worth about one order. Where a quarter or more of the audience buys anyway, a coupon needs "
        "a lift of 5+ points to break even, more than win-back campaigns usually deliver. Content and early access cost almost nothing, so even a "
        "small lift pays. The two discount cells are there to measure this instead of assuming it.")
st.markdown("**Scenarios (default arms):**")
chart(C.scenario_bars(mart("campaign_scenarios")), key="scen")

# ----------------------------------------------------------------------------- 3. budget
st.subheader("3. The budget ask, and where the next CU goes")
c1, c2 = st.columns([3, 2])
with c1:
    bl = mart("campaign_budget")
    table(bl.assign(cost_cu=bl.cost_cu.round(0)).rename(columns={"line": "Line", "cost_cu": "CU", "note": "How it is calculated"}),
                 hide_index=True, width="stretch")
with c2:
    st.markdown(
        f"""
**If the budget is cut**, drop in this order:
1. the At Risk 10% test cell (keeps the content win-back; the offer question waits a season),
2. paid social for the New Customers journey (email still reaches a third of them),
3. the New Customers coupon cell (last, because the second order is where a discount is most likely to pay).

Content arms and email are never cut: together they cost about {fmt_cu(roll[~roll.use_paid_social].total_cost_cu.sum())}.
"""
    )
pos = econ[(econ.role == "Rollout") & (econ.net_profit_cu > 0)]
max_budget = float(max(pos.total_cost_cu.sum(), 1.0))
budget = st.slider("Budget for the rollout arms (CU)", 0.0, round(max_budget * 1.2, -2), round(max_budget * 0.5, -2), 100.0, key="budget")
alloc = CP.allocate_budget(econ, budget)
k1, k2, k3 = st.columns(3)
k1.metric("Budget used", fmt_cu(alloc.funded_cost_cu.sum()), f"of {fmt_cu(budget)}", delta_color="off", delta_arrow="off")
k2.metric("Expected incremental revenue", fmt_cu(alloc.funded_incremental_revenue_cu.sum()))
k3.metric("Expected net profit", fmt_cu(alloc.funded_net_profit_cu.sum()))
table(alloc[["audience_label", "arm", "profit_per_cu", "total_cost_cu", "funded_share", "funded_cost_cu", "funded_net_profit_cu"]]
             .assign(funded_share=lambda x: (100 * x.funded_share).round(0).astype(int).astype(str) + "%")
             .round({"profit_per_cu": 2, "total_cost_cu": 0, "funded_cost_cu": 0, "funded_net_profit_cu": 0})
             .rename(columns={"audience_label": "Audience", "arm": "Arm", "profit_per_cu": "Net profit per CU spent", "total_cost_cu": "Full cost (CU)",
                              "funded_share": "Funded", "funded_cost_cu": "Funded cost (CU)", "funded_net_profit_cu": "Funded net profit (CU)"}),
             hide_index=True, width="stretch")
note("Rollout arms are funded in order of net profit per CU spent; a partly funded arm runs on a random subset of its audience. "
     "Test cells are a fixed learning cost and are not ranked here.")

# ----------------------------------------------------------------------------- 4. measurement
st.subheader("4. Measurement plan")
pr = camp["pooled_read"]
st.markdown(
    f"""
**Control condition.** In every audience, 10% of the reachable customers are held out by a salted hash of customer ID (stratified by audience),
checked at launch for balance on 12-month spend and subscriber share. The holdout gets **no autumn campaign communication** (no campaign emails,
no personal app messages or early-access links, excluded from paid-social audiences and lookalike seeds) but keeps the business-as-usual
newsletter, Black Friday and Christmas sends that everyone gets. So we measure the campaign *on top of* business as usual.

**Estimand.** Intention-to-treat: everyone assigned to an arm counts, opened or not, matched in paid social or not; the assumed lifts are ITT lifts.
Opens and clicks are only diagnostics.

**KPIs.** Primary, pre-registered for every arm: **90-day repurchase rate** (the most sensitive metric). Secondary: revenue per customer
(winsorised at the 99th percentile, adjusted for 12-month spend) and net profit after discount and contact cost.

**What we will know on {CP.READ_DATE}:**
- **Campaign-wide lift** from the pooled holdout ({fmt_n(pr['holdout_customers'])} customers): detectable from **{pr['mde_rate_pp']:.2f} pp**, against
  {pr['expected_lift_pp']:.2f} pp expected if the arms deliver their assumptions.
- **The two discount decisions**: both test cells are sized so their detectable lift is at most two thirds of their break-even, so a "no" is informative.
- **Everything else is directional**: single content arms are too small to read alone at content-sized lifts (table below); they are judged by the
  pooled read and kept as always-on journeys only if it is positive.

**Decision rules.** Scale an offer in the next wave only if the 95% lower bound of its lift over the content cell clears its break-even.
The day-30 read covers delivery and guardrails only (unsubscribes, complaints): no decisions on lift before day 90. Comparisons within
At Risk are Holm-adjusted.
"""
)
labels = inputs.set_index("audience")["audience_label"]
c1, c2 = st.columns(2)
key = c1.selectbox("Audience", list(labels.index), index=list(labels.index).index("at_risk_181_364_high"),
                   format_func=lambda k: labels[k], key="mde_aud")
share = c2.slider("Holdout share", 0.05, 0.30, 0.10, 0.01, key="mde_share")
row = inputs.set_index("audience").loc[key]
paid = bool(plan[(plan.audience == key) & (plan.role != "Not run")].use_paid_social.any())
pop = row.customers * (1.0 if paid else row.newsletter_share)
mde_r = 100 * PW.mde_rate(row.baseline_rate, pop * (1 - share), pop * share)
mde_v = PW.mde_mean(row.sd_revenue, pop * (1 - share), pop * share)
assumed = float(plan[(plan.audience == key) & (plan.role == "Rollout")].uplift_pp.iloc[0])
k1, k2, k3, k4 = st.columns(4)
k1.metric("Reachable population", f"{round(pop):,}", "email + paid social" if paid else "newsletter subscribers only",
          delta_color="off", delta_arrow="off")
k2.metric("Holdout customers", f"{round(pop * share):,}")
k3.metric("Detectable lift, repurchase rate", f"{mde_r:.2f} pp", f"assumed +{assumed:.1f} pp", delta_color="off", delta_arrow="off")
k4.metric("Detectable lift, revenue per customer", f"{mde_v:.1f} CU", f"baseline {row.revenue_per_customer:.1f} CU",
          delta_color="off", delta_arrow="off")
chart(C.mde_by_holdout(mart("holdout_power"), key, assumed, share), key="mde")
arm_tbl = econ[econ.role != "Not run"][["audience_label", "arm", "role", "experiment_population", "holdout", "contacted", "uplift_pp",
                                        "breakeven_uplift_pp", "mde_rate_pp", "mde_revenue_cu", "readable_alone", "powered_for_decision"]].copy()
arm_tbl = arm_tbl.round({"experiment_population": 0, "holdout": 0, "contacted": 0, "breakeven_uplift_pp": 2, "mde_rate_pp": 2, "mde_revenue_cu": 1})
arm_tbl["readable_alone"] = arm_tbl["readable_alone"].map({True: "yes", False: "no: pooled read"})
arm_tbl["powered_for_decision"] = np.where(arm_tbl.role == "Test cell", arm_tbl["powered_for_decision"].map({True: "yes", False: "no"}), "-")
arm_tbl.columns = ["Audience", "Arm", "Role", "Reachable population", "Holdout", "Arm size", "Assumed lift (pp)", "Break-even (pp)",
                   "Detectable lift (pp)", "Detectable revenue lift (CU)", "Readable alone?", "Sized for its decision?"]
table(arm_tbl, hide_index=True, width="stretch")

# ----------------------------------------------------------------------------- 5. timeline
st.subheader("5. Timeline")
table(pd.DataFrame([
    {"When": "2020-09-23 to 09-25", "What": "Build audiences with the production SQL; hash-split into arms and holdout; balance check; QA counts vs this plan"},
    {"When": "2020-09-28 (launch day)", "What": "Re-score audiences; week-1 sends: At Risk (all cells), Slipping Regulars, Potential Loyalists, Needs Attention; New Customers journey starts"},
    {"When": "2020-09-29", "What": "Champions early-access link (48 h before the public launch)"},
    {"When": "2020-10-05 (week 2)", "What": "Loyal basket-building picks; reminders (Slipping day 10, At Risk day 7) to those who have not bought"},
    {"When": "2020-10-19 (week 4)", "What": "Lost reactivation email"},
    {"When": "2020-10-28 (day 30)", "What": "Interim read: delivery, guardrails, paid-social match rates. No lift decisions"},
    {"When": "2020-12-27 (day 90)", "What": "Final read vs holdout; decide which journeys stay always-on and whether either offer scales in the next wave"},
]), hide_index=True, width="stretch")

how_to_read(
    """
**Section 1 - the plan** is what the CRM team executes: who (audience rule), what, when, which channel, which products, what we expect, how we
measure and what result would change the decision. "Rollout" rows are the recommended actions. "Test cell" rows are small groups where a
discount is tried, to learn whether it pays before anyone rolls it out. "Not run" rows were considered and rejected.

**Section 2 - economics.** For each arm: extra buyers = people assigned x assumed lift; extra revenue = extra buyers x one order (base case);
profit = extra revenue x margin, minus discount and contact costs. A coupon is also used by customers who would have bought anyway, so its cost
lands on many orders that are not extra. The **break-even lift** (red diamond) is how much an arm must raise the repurchase rate just to cover
its cost. Blue dot left of the red diamond = expected loss. Try the sliders: halve all lifts, or value buyers at the average buyer's spend.

**Section 3 - budget.** The ask in CU by cost type, the order in which to cut it, and a slider that funds the arms with the best return first.

**Section 4 - measurement.** The holdout is a random group that does not get the campaign, so contacted minus holdout is the effect of the
campaign itself, not of the season or a sale. "Detectable lift" is the smallest effect the test can reliably spot: if the true lift is smaller,
the test will probably say "no difference". Small content lifts are therefore read together, campaign-wide, while each discount decision gets
a test cell big enough to give a clear answer.
"""
)
