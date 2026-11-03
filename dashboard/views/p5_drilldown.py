import pandas as pd
import streamlit as st

from common import chart, fmt_cu, fmt_n, how_to_read, mart, metrics, note, page_header, pct, segment_select
from rfm import charts as C
from rfm.campaign import category_focus

page_header(
    "Segment Drill-down",
    "For each segment: what do they buy, where do they buy it (store vs online), and who are they? And who only buys online?",
)

m = metrics()
h = m["headline"]
mix = mart("segment_mix")
prof = mart("segment_profile").set_index("segment")

c1, c2 = st.columns([1, 2])
with c1:
    seg = segment_select("Segment", default="At Risk", key="dd_seg")
with c2:
    dim_label = st.radio("Category level", ["Garment group", "Department", "Product group"], horizontal=True, key="dd_dim")
dim = {"Garment group": "garment_group", "Department": "index_group", "Product group": "product_group"}[dim_label]

p = prof.loc[seg]
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Customers", fmt_n(p.customers), f"{pct(p.pct_customers)} of all", delta_color="off")
k2.metric("12-month revenue", fmt_cu(p.revenue_12m_cu), f"{pct(p.pct_revenue_12m)} of all", delta_color="off")
k3.metric("Average order value", f"{(p.aov_12m_cu if pd.notna(p.aov_12m_cu) else p.aov_2y_cu):.1f} CU",
          "two-year AOV" if pd.isna(p.aov_12m_cu) else None, delta_color="off")
online = p.pct_online_only_12m if pd.notna(p.pct_online_only_12m) else p.pct_online_only_2y
k4.metric("Online only", pct(online, 0), "last 12 months" if pd.notna(p.pct_online_only_12m) else "two years", delta_color="off")
k5.metric("Reachable by email", pct(p.pct_newsletter, 0), "fashion-news subscribers", delta_color="off")

st.subheader(f"1. What {seg} bought in their last active period")
d = mix[(mix.segment == seg) & (mix.dimension == dim) & (mix.value != "Unknown")]
chart(C.category_affinity(mix, seg, dim), table=d[["value", "amount", "segment_share", "overall_share", "affinity_index"]]
      .rename(columns={"value": "category", "amount": "revenue (CU)"}).round(3), key=f"aff_{seg}_{dim}")
note(f"Category focus used in the campaign (index >= 120 and >= 5% of the segment's revenue): {category_focus().get(seg, '-')}. "
     "Window: last 12 months vs all customers' last 12 months; Lost: two years vs all customers' two years. Affinity also reflects "
     "when a segment last bought (At Risk last bought in winter, Needs Attention in summer), so read it as 'what to show them now'.")

st.subheader("2. Who only buys online, and does it matter?")
aud = mart("channel_audience")
oo = aud[(aud.channel == "Online only") & ~aud.segment.isin(["Lost", "Review List"])].copy()
oo["share"] = oo.customers / oo.customers.sum()
top = oo.sort_values("customers", ascending=False).head(2)
st.markdown(
    f"""
**The audience.** {fmt_n(h['online_only_active_customers'])} of the customers active in the last 12 months ({pct(h['pct_online_only_active'], 0)})
had **no identified store purchase** in that time; {fmt_n(h['online_only_active_subscribers'])} of them are reachable by email.
{pct(top.share.iloc[0], 0)} are {top.segment.iloc[0]} and {pct(top.share.iloc[1], 0)} {top.segment.iloc[1]}; {fmt_n(h['online_only_high_value_customers'])}
are Champions, Loyal or Slipping Regulars. {fmt_n(h['store_only_active_customers'])} active customers are the mirror image: store only.
"""
)
c1, c2 = st.columns(2)
with c1:
    chart(C.channel_mix(mix, seg), key="chmix")
with c2:
    net = st.toggle("Apply an illustrative returns haircut (25% online, 8% store)", value=False, key="net_toggle")
    cv = mart("channel_value")
    chart(C.channel_value(cv, net_of_returns=net), table=cv.round(1), key=f"chval_{net}")
c1, c2 = st.columns([3, 2])
with c1:
    chart(C.channel_forward(mart("channel_forward")), key="chfwd")
with c2:
    aov = mart("channel_order_aov")
    st.markdown("**Same customers, different baskets**")
    st.dataframe(aov.round(2).rename(columns={"customers_group": "customers", "order_channel": "order channel", "aov_cu": "AOV (CU)",
                                              "units_per_order": "items per order"}), hide_index=True, width="stretch")
    st.caption("Among omnichannel customers (who use both), an online order is about twice a store order: the 'online-only spend more' pattern "
               "is mostly basket size, not a different kind of customer.")
st.markdown(
    f"""
**What it means for the campaign.** Online-only customers are not low-value, but they are not better customers either: their bigger baskets
are a property of the online channel (and are before returns, which in fashion tend to be much higher online), and looking forward they come back slightly
*less* often than omnichannel customers ({pct(h['repurchase_5_9_online_only'], 0)} vs {pct(h['repurchase_5_9_omni'], 0)} at 5-9 orders). Nothing here shows
that getting them into a store would make them more valuable, so the plan does not pay to push them there. Channel decides the *message*:

| Channel in the last 12 months | Treatment rule in every arm |
|---|---|
| Online only | online creative, delivery and free-returns message, app; excluded from store events |
| Store only | store-led creative (new in store, click-and-collect, in-store returns); no online-only vouchers |
| Omnichannel | both; click-and-collect as the bridge |

A store-visit incentive for online-only customers can be tested later as its own holdout arm if Retail asks for it.
"""
)
note("Caveat: store purchases are only recorded when the shopper identifies as a member, so 'online only' means 'no identified store purchase'.")

st.subheader(f"3. Who {seg} are")
c1, c2 = st.columns([3, 2])
with c1:
    chart(C.age_mix(mix, seg), key=f"age_{seg}")
with c2:
    attr = mix[(mix.segment == seg) & mix.dimension.isin(["value_tier", "club_member_status", "newsletter_frequency", "first_order_channel"])]
    st.dataframe(attr.assign(share=(100 * attr.segment_share).round(1), all_customers=(100 * attr.overall_share).round(1),
                             index=attr.affinity_index.round(0))[["dimension", "value", "share", "all_customers", "index"]]
                 .rename(columns={"share": f"% of {seg}", "all_customers": "% of all customers"}),
                 hide_index=True, width="stretch", height=420)

how_to_read(
    """
**Affinity index (section 1).** For each category we compare the share of the segment's revenue that goes to it with the same share for all
customers over the same window. 100 = same as everyone; 124 = this segment spends 24% more of its money on that category (blue);
below 100 = less (red). It tells the campaign team which products to put in front of each segment right now.

**Online-only (section 2).** The stacked bars show, per segment, who bought only online, in both channels, or only in store in the last 12 months.
The middle chart compares 12-month spend at the same number of orders: online-only customers show the highest spend, but the table next to the
forward-looking chart explains why - an online order is about twice the size of a store order even for the same customers. Switch on the returns
toggle to see the gap shrink once (illustrative) returns are taken off. The forward-looking chart uses the 2019 backtest: grouped by channel and
orders in the year before, how many came back in the next 90 days.

**Who they are (section 3).** Age comes from the customer file (about 1% missing). The table shows value tier, club status, newsletter status
and the channel of the first order, each compared with all customers.

**Use the selectors** at the top to switch segment and category level; every segment-specific chart on the page updates.
"""
)
