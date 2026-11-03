import pandas as pd
import streamlit as st

from common import callout, chart, fmt_cu, fmt_n, how_to_read, mart, metrics, page_header, pct, table
from rfm import campaign as CP
from rfm import charts as C
from rfm.segments import SEGMENT_INFO, SEGMENT_ORDER

page_header(
    "RFM Segmentation for the Autumn Campaign",
    "Which customers should get what in a budget-limited autumn campaign, and what is at stake if we do nothing?",
)

m = metrics()
d, h, camp = m["data"], m["headline"], m["campaign"]
seg = m["segments"]
sc = camp["scenarios"]

c1, c2, c3, c4 = st.columns(4)
c1.metric("Customers", fmt_n(d["customers_with_orders"], 2),
          help="Distinct customers with at least one order between 2018-09-20 and 2020-09-22")
c2.metric("Active (12 months)", fmt_n(d["active_12m_customers"]), f"{pct(d['pct_active_12m'])} of customers",
          delta_color="off", delta_arrow="off")
c3.metric("Revenue (12 months)", fmt_cu(d["revenue_12m_cu"]), "2019-09-24 to 2020-09-22", delta_color="off", delta_arrow="off",
          help="CU = price x 590 (scaled retail price; currency undisclosed). Gross demand: the data has no returns.")
c4.metric("At Risk, next 90 days", fmt_cu(h["at_risk_expected_90d_cu"]),
          f"{fmt_cu(h['at_risk_gap_90d_cu'])} below their usual pace", delta_color="off", delta_arrow="off",
          help="What look-alike customers spent after 2019-09-22, re-weighted to today's mix")

st.subheader("Three things the CRM Manager needs to know")
st.markdown(
    f"""
1. **High value is concentrated, and it does not need discounts.** Champions are {pct(h['champions_pct_customers'], 0)} of customers and
   {pct(h['champions_pct_revenue_12m'], 0)} of 12-month revenue; the {fmt_n(h['vip_customers'])} VIPs (1,000+ CU a year) alone bring in
   {pct(h['vip_pct_revenue_12m'], 0)}. {pct(seg['Champions']['repurchase_rate_90d_base'], 0)} of Champions buy again within 90 days without any
   campaign, so the plan protects them with early access and service, not coupons.
2. **Two groups are drifting away: {fmt_n(h['at_risk_customers'])} At Risk customers and {fmt_n(h['slipping_customers'])} Slipping Regulars.**
   At Risk used to buy often or a lot and has been quiet for 4-12 months: left alone they spend about {fmt_cu(h['at_risk_expected_90d_cu'])} in the
   next 90 days instead of {fmt_cu(h['at_risk_run_rate_90d_cu'])} at their usual pace, and {fmt_n(h['at_risk_non_buyers_90d'])} of them will not buy
   at all. Slipping Regulars are frequent buyers already 61-120 days quiet ({pct(h['slipping_pct_revenue_12m'], 0)} of revenue, gap about
   {fmt_cu(h['slipping_gap_90d_cu'])}). Much of this gap is natural slowdown that no email reverses: the plan expects to win back about
   {fmt_cu(h['at_risk_addressable_90d_cu'])} from At Risk ({fmt_cu(h['at_risk_addressable_content_90d_cu'])} of it from content emails), and measures it.
3. **Online-only shoppers are not a problem to fix.** {fmt_n(h['online_only_active_customers'])} active customers ({pct(h['pct_online_only_active'], 0)})
   had no identified store purchase in the last 12 months. Online baskets are about twice the size of store baskets
   ({h['aov_online_order_omni']:.0f} vs {h['aov_store_order_omni']:.0f} CU for the same omnichannel customers), but online-only customers come back
   slightly less often; neither supports paying to push them into stores. They are reached online (email, app, paid social).
"""
)

callout(
    f"<b>Recommended autumn plan:</b> content-led actions for every segment that is worth contacting (cost {fmt_cu(sc['Base | Rollout']['total_cost_cu'])}); "
    f"discounts only in two test cells sized to tell whether they pay (10% off a New Customer's second order; 10% off for long-lapsed high-value At Risk); "
    f"no spend on Hibernating or the Review List. <b>Budget ask {fmt_cu(camp['budget_total_cu'])}</b>. "
    f"Expected net of the rollout: <b>{fmt_cu(sc['Base | Rollout']['net_profit_cu'])}</b> (pessimistic {fmt_cu(sc['Pessimistic | Rollout']['net_profit_cu'])}, "
    f"optimistic {fmt_cu(sc['Optimistic | Rollout']['net_profit_cu'])}); the test cells are expected to cost {fmt_cu(-camp['test_cells_net_profit_cu'])} "
    f"to learn from. Measured against a 10% holdout in every audience (campaign-wide lift detectable from {camp['pooled_read']['mde_rate_pp']:.2f} pp)."
)

prof = mart("segment_profile")
chart(C.segment_share(prof), data=prof[["segment", "customers", "pct_customers", "pct_revenue_12m", "pct_revenue_2y"]]
      .assign(pct_customers=lambda x: (100 * x.pct_customers).round(1), pct_revenue_12m=lambda x: (100 * x.pct_revenue_12m).round(1),
              pct_revenue_2y=lambda x: (100 * x.pct_revenue_2y).round(1))
      .rename(columns={"pct_customers": "% customers", "pct_revenue_12m": "% 12m revenue", "pct_revenue_2y": "% 2y revenue"}))

st.subheader("Segments and what each one gets")
econ = mart("campaign_economics")
rows = []
for s in SEGMENT_ORDER:
    p = prof.set_index("segment").loc[s]
    arms = econ[(econ.segment == s) & (econ.role != "Not run")]
    action = CP.NO_CAMPAIGN.get(s) or "; ".join(
        f"{r.audience_label + ': ' if r.audience_label != s else ''}{r.arm}{' (test cell)' if r.role == 'Test cell' else ''}"
        for r in arms.itertuples())
    rows.append({
        "Segment": s,
        "Who (plain language)": SEGMENT_INFO[s]["plain"],
        "Customers": int(p["customers"]),
        "% customers": round(100 * p["pct_customers"], 1),
        "% 12m revenue": round(100 * p["pct_revenue_12m"], 1),
        "Autumn action": action,
        "Expected net (CU, base)": None if arms.empty else round(float(arms.net_profit_cu.sum())),
    })
table(pd.DataFrame(rows), hide_index=True, width="stretch",
             column_config={"Customers": st.column_config.NumberColumn(format="%d"),
                            "Expected net (CU, base)": st.column_config.NumberColumn(format="%d"),
                            "Autumn action": st.column_config.TextColumn(width="large"),
                            "Who (plain language)": st.column_config.TextColumn(width="medium")})

how_to_read(
    """
**What this page is.** The one-page answer to the CRM Manager's request. Everything below it in the menu is the evidence.

**The top numbers.** "Customers with a purchase" counts everyone who bought at least once in the two years of data. "Active in the last
12 months" is the standard CRM definition of an active customer. Money is shown in **CU** (currency units): the public data hides real
prices, but every price multiplied by 590 lands exactly on a shelf price like 9.99 or 19.99, so CU behaves like a major currency. It is
gross demand: the data contains no returns. Shares and ratios do not depend on the unit at all.

**The bar chart.** For each segment, the grey bar is its share of customers and the blue bar its share of 12-month revenue. When blue is
much longer than grey (Champions), a small group carries a big part of the business. When grey is longer (Hibernating, Lost), there are many
customers who are worth little today. Lost shows 0% because, by definition, they did not buy in the last 12 months.

**"Expected next 90 days" for At Risk.** We found customers who looked like today's At Risk customers on 2019-09-22 (same season one year
earlier) and measured what they actually spent in the next 90 days. Applied to today's group, that is the forecast if we do nothing. The
"usual pace" is what they spent per 90 days over the last year; the gap between the two is not all winnable - a good part is the normal
slowdown after a strong year - which is why the plan's own expected recovery is much smaller and is measured with a holdout.

**Expected net profit** comes from planning assumptions (how much each action lifts the chance of buying, valued at one extra order).
They are not measured yet. Treat the CU amounts as orders of magnitude; the holdout test turns them into facts.
"""
)
