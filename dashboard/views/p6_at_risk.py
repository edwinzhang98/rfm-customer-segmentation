import numpy as np
import pandas as pd
import streamlit as st

from common import backtest, callout, chart, customers, fmt_cu, fmt_n, how_to_read, mart, metrics, note, page_header, pct, table
from rfm import charts as C

page_header(
    "At-risk Revenue",
    "If we do nothing, what will the customers who are drifting away spend in the next 90 days, how far is that below their usual pace, "
    "and how much of it can a campaign realistically win back?",
)

m = metrics()
h = m["headline"]
rar = mart("revenue_at_risk")
ar = m["segments"]["At Risk"]
sl = m["segments"]["Slipping Regulars"]

c1, c2, c3, c4 = st.columns(4)
c1.metric("At Risk customers", fmt_n(ar["customers"]), f"{pct(ar['pct_customers'])} of customers", delta_color="off", delta_arrow="off")
c2.metric("Expected next 90 days if we do nothing", fmt_cu(ar["expected_90d_cu_base"]),
          f"usual pace {fmt_cu(ar['run_rate_90d_cu'])}", delta_color="off", delta_arrow="off")
c3.metric("Gap vs usual pace", fmt_cu(ar["gap_90d_cu_base"]), f"scenarios {fmt_cu(ar['gap_90d_cu_low'])} to {fmt_cu(ar['gap_90d_cu_high'])}",
          delta_color="off", delta_arrow="off")
c4.metric("Expected non-buyers", fmt_n(ar["expected_non_buyers_base"]), f"{pct(1 - ar['repurchase_rate_90d_base'], 0)} of the segment",
          delta_color="off", delta_arrow="off")

callout(
    f"<b>How to say it to the CRM Manager.</b> Left alone, At Risk customers will spend about {fmt_cu(ar['expected_90d_cu_base'])} in the next 90 days, "
    f"{pct(ar['gap_90d_cu_base'] / ar['run_rate_90d_cu'], 0)} below the {fmt_cu(ar['run_rate_90d_cu'])} they spent per quarter over the last year, and "
    f"{fmt_n(ar['expected_non_buyers_base'])} of them will not buy at all. The early-warning group, Slipping Regulars, shows a further gap of "
    f"{fmt_cu(sl['gap_90d_cu_base'])}. <b>The autumn plan expects to win back about {fmt_cu(h['at_risk_addressable_90d_cu'])} from At Risk</b> "
    f"({fmt_cu(h['at_risk_addressable_content_90d_cu'])} from content emails, the rest from the 10% offer test cell): most of the gap "
    "is the normal slowdown of customers who are past their peak, not money a campaign can recover. That is why the plan is cheap and measured, "
    "and why the number we promise is the measured lift, not the gap."
)

st.subheader("1. Usual pace vs expected, every segment")
chart(C.run_rate_vs_expected(rar), key="rr")
tbl = rar[["segment", "customers", "run_rate_90d_cu", "expected_90d_cu_base", "gap_90d_cu_base", "gap_90d_cu_low", "gap_90d_cu_high",
           "addressable_90d_cu", "repurchase_rate_base", "expected_non_buyers_base", "base_basis"]].copy()
tbl.columns = ["Segment", "Customers", "Usual 90-day pace (CU)", "Expected, do nothing (CU)", "Gap vs pace (CU)", "Gap low (CU)", "Gap high (CU)",
               "Plan's expected incremental revenue (CU)", "Buy again within 90 days", "Expected non-buyers", "Reference date"]
tbl["Reference date"] = tbl["Reference date"].map({"seasonal": "2019-09-22", "recent": "2020-06-24"})
for c in ["Usual 90-day pace (CU)", "Expected, do nothing (CU)", "Gap vs pace (CU)", "Gap low (CU)", "Gap high (CU)",
          "Plan's expected incremental revenue (CU)", "Expected non-buyers"]:
    tbl[c] = tbl[c].round(0)
tbl["Buy again within 90 days"] = (100 * tbl["Buy again within 90 days"]).round(1).astype(str) + "%"
table(tbl, hide_index=True, width="stretch")
rtm = mart("regression_to_mean")
ch5 = rtm[(rtm.segment == "Champions") & (rtm.m_score == 5)].realisation.iloc[0]
ch4 = rtm[(rtm.segment == "Champions") & (rtm.m_score == 4)].realisation.iloc[0]
note(f"Champions' gap is not a churn signal: top spenders fall back after a strong year while the rest catch up (in the backtest, Champions spending "
     f"400+ CU realised {pct(ch5, 0)} of their pace, those spending 200-399 CU {pct(ch4, 0)}). Negative gaps (New Customers, Potential Loyalists, Loyal) "
     "are customers whose 12-month history is short or still building. Lost has no 12-month pace: only its expected reactivation revenue is shown.")

st.subheader("2. Define your own at-risk audience")
st.caption("Pick the audience with the sliders. Today's customers matching the rule are compared with customers who matched the same rule at the "
           "reference date (simple ratio, not re-weighted to today's mix).")
c1, c2, c3, c4 = st.columns(4)
rec_lo, rec_hi = c1.slider("Days since last order", 31, 364, (121, 364), 1, key="ar_rec")
min_f = c2.slider("...and at least this many orders in 12 months", 1, 10, 3, key="ar_f")
min_m = c3.slider("...or at least this much spend (CU, 12 months)", 0, 1000, 200, 25, key="ar_m", help="Set to 0 to use the orders rule only")
basis = c4.radio("Reference date", ["2019-09-22 (same season)", "2020-06-24 (last quarter)"], key="ar_basis")
snap = "backtest_seasonal" if basis.startswith("2019") else "backtest_recent"


def audience(df: pd.DataFrame) -> pd.Series:
    used_to_buy = df.frequency_12m >= min_f
    if min_m > 0:
        used_to_buy = used_to_buy | (df.monetary_12m_cu >= min_m)
    return df.recency_days.between(rec_lo, rec_hi) & used_to_buy & ~df.is_excluded


cur = customers()
sel = cur[audience(cur)]
bt = backtest()
bt = bt[bt.snapshot_name == snap]
bsel = bt[audience(bt)]
run_rate = float(sel.monetary_12m_cu.sum()) * 90 / 365
if len(bsel) and bsel.run_rate_90d_cu.sum() > 0 and len(sel):
    ratio = float(bsel.revenue_next_90d_cu.sum() / bsel.run_rate_90d_cu.sum())
    rate = float(bsel.purchased_next_90d.mean())
    aov = float(sel.monetary_12m_cu.sum() / max(sel.frequency_12m.sum(), 1))
    expected = run_rate * ratio
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Customers in your audience", f"{len(sel):,}", f"{pct(len(sel) / len(cur))} of customers", delta_color="off", delta_arrow="off")
    k2.metric("Would buy again within 90 days anyway", pct(rate, 0), f"{len(bsel):,} look-alikes in the backtest", delta_color="off", delta_arrow="off")
    k3.metric("Expected non-buyers", f"{round(len(sel) * (1 - rate)):,}")
    k4.metric("Gap vs usual pace, next 90 days", fmt_cu(run_rate - expected), f"{pct(1 - ratio, 0)} below usual pace", delta_color="off", delta_arrow="off")
    chart(C.shortfall_waterfall(run_rate, expected, "Your audience"), key="wf")

    st.subheader("3. How much could a win-back campaign recover?")
    c1, c2 = st.columns(2)
    lift = c1.slider("Assumed lift in the 90-day repurchase rate (percentage points)", 0.0, 10.0, 1.0, 0.5, key="ar_lift")
    reach = c2.slider("Share of the audience assigned to the campaign", 0.1, 1.0, 0.90, 0.05, key="ar_reach",
                      help="Default 90% = everyone except the 10% holdout")
    inc_buyers = len(sel) * reach * lift / 100
    inc_rev = inc_buyers * aov
    k1, k2, k3 = st.columns(3)
    k1.metric("Incremental buyers", f"{round(inc_buyers):,}")
    k2.metric("Incremental revenue", fmt_cu(inc_rev), f"one extra order of {aov:.0f} CU each", delta_color="off", delta_arrow="off")
    k3.metric("Share of the gap recovered", pct(inc_rev / max(run_rate - expected, 1)))
    note("Even a strong campaign recovers a small slice of the gap. A 10-point lift would already be exceptional for a win-back programme.")
else:
    st.warning("No customers match this definition. Widen the recency window or lower the thresholds.")

st.subheader("4. How sure are we?")
r = rar.set_index("segment").loc["At Risk"]
st.markdown(
    f"""
| Scenario for At Risk | Realisation (share of usual pace) | Expected 90 days | Gap vs pace |
|---|---|---|---|
| **Base: same season last year** (2019-09-22), re-weighted to today's mix | {pct(r.realisation_seasonal, 1)} | {fmt_cu(r.expected_90d_cu_seasonal)} | {fmt_cu(r.gap_90d_cu_seasonal)} |
| Last quarter (2020-06-24, the reopening summer), re-weighted | {pct(r.realisation_recent, 1)} | {fmt_cu(r.expected_90d_cu_recent)} | {fmt_cu(r.gap_90d_cu_recent)} |
| Pessimistic: the worse of the two for every customer type | {pct(r.realisation_pessimistic, 1)} | {fmt_cu(r.expected_90d_cu_pessimistic)} | {fmt_cu(r.gap_90d_cu_pessimistic)} |

- **Re-weighting matters because today's At Risk group is unusual:** {pct(h['at_risk_lockdown_share'], 0)} of them last bought during the
  March-May 2020 lockdown, and they are more online-only than either backtest group. The realisation is therefore computed separately for each
  type of customer (recency x frequency x spend x channel) and averaged with today's weights. No past period shows how lockdown-era online
  shoppers behave in an autumn, which is the main reason for the pessimistic row.
- **Sampling noise is small:** with ~90K customers the 95% interval on the base case is about {fmt_cu(r.gap_ci_lo)} to {fmt_cu(r.gap_ci_hi)}. It only covers
  random noise within one backtest year; the scenario table above is the uncertainty to quote.
- **Autumn 2020 is not autumn 2019:** if a second wave closes stores again, store-heavy customers will spend less than any scenario here.
- **"Do nothing" means business as usual:** the backtest periods already include the normal newsletters and sales, so the campaign's lift is
  measured on top of that.
"""
)

how_to_read(
    """
**The idea in one sentence.** To estimate what happens if we do nothing, we look at what happened last year to customers who looked like
today's customers, and assume the same happens again.

**Usual pace (grey bars).** What a segment would spend in 90 days if it kept buying like it did over the last 12 months (12-month revenue x 90/365).
**Expected (blue bars).** The usual pace multiplied by the share of it that look-alike customers actually spent in the 90 days after 2019-09-22.
For At Risk that share is about 64%, so they are expected to spend about a third less. The label on each blue bar is the difference.

**Why the gap is not "money we can win back".** Customers are put in a segment *because* of their last 12 months. A group selected for a strong
year (Champions) naturally falls back a little; a group selected for going quiet (At Risk) keeps slowing down. Part of every gap is this
natural movement. The realistic prize is the plan's expected incremental revenue in the table, a few percent of the gap.

**Your audience (section 2).** Change who counts as "at risk": how long since their last order, and what made them valuable before
(enough orders, or enough spend). Try a window of 61-120 days with 5+ orders to see the Slipping Regulars.

**Section 3** turns an assumed campaign effect into money, valuing each extra buyer at one extra order.

**Section 4** lists three scenarios. The base case uses the same season one year earlier; the others use last quarter, or the worse of
the two for every customer type. Quote the range, not one number.
"""
)
