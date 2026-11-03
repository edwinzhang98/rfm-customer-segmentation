import pandas as pd
import streamlit as st

from common import chart, how_to_read, mart, metrics, note, page_header, pct, table
from rfm import charts as C
from rfm.segments import SEGMENT_INFO

page_header(
    "Segments Overview",
    "Who is in each segment, how much are they worth, do the segments predict what customers do next, and how fast do they change?",
)

m = metrics()
h = m["headline"]
prof = mart("segment_profile")

st.subheader("1. Size and value")
chart(C.segment_share(prof), key="share")

st.subheader("2. Profile of each segment")
view = pd.DataFrame({
    "Segment": prof["segment"],
    "Definition": prof["segment"].map(lambda s: SEGMENT_INFO[s]["plain"]),
    "Customers": prof["customers"],
    "% customers": (100 * prof["pct_customers"]).round(1),
    "% 12m revenue": (100 * prof["pct_revenue_12m"]).round(1),
    "Avg orders (12m)": prof["avg_orders_12m"].round(1),
    "AOV (CU)": prof["aov_12m_cu"].fillna(prof["aov_2y_cu"]).round(1),
    "Spend per customer (12m CU)": prof["avg_revenue_12m_cu"].round(0),
    "Median days between orders": prof["median_days_between_orders"].round(0),
    "Median days since last order": prof["median_recency_days"].round(0),
    "% online only (12m)": (100 * prof["pct_online_only_12m"].fillna(prof["pct_online_only_2y"])).round(0),
    "% email reach": (100 * prof["pct_newsletter"]).round(0),
    "% VIP": (100 * prof["pct_vip"]).round(1),
    "Median age": prof["median_age"],
})
table(view, hide_index=True, width="stretch",
             column_config={"Customers": st.column_config.NumberColumn(format="%d"),
                            "Definition": st.column_config.TextColumn(width="large")})
note("AOV = 12-month revenue / 12-month orders (Lost: two-year AOV; Lost '% online only' uses two years). Days between orders only for customers "
     "with 2+ orders in 12 months. Email reach = fashion-news subscribers. SQL: sql/09_segment_profile.sql")

st.subheader("3. Value as a second axis")
what = st.radio("Cells show", ["customers", "12-month revenue"], horizontal=True, key="vg_what")
grid = mart("value_grid")
chart(C.value_grid(grid, "customers" if what == "customers" else "revenue_12m_cu"), data=grid, key="vgrid")
st.markdown(
    "Lifecycle (rows) says **what to do**; value tier (columns) says **how much effort a customer is worth**. The tier decides paid reach "
    "(paid social only for long-lapsed At Risk customers spending 200+ CU) and keeps VIPs visible wherever they sit: "
    f"{h['vip_customers']:,} customers spend 1,000+ CU a year, mostly Champions but also Slipping Regulars and At Risk."
)

st.subheader("4. Do the segments predict behaviour? (backtest)")
so = mart("segment_outcomes_90d")
chart(C.segment_outcomes(so), data=so[["snapshot_name", "segment", "customers", "repurchase_rate", "revenue_per_customer_cu",
                                        "realisation_ratio"]].round(3), key="outcomes")
st.markdown(
    "Exactly the same rules applied at two past dates, then what each segment actually did in the following 90 days. The order holds at both "
    "dates: Champions come back most, Lost least, and Slipping Regulars sit right after Champions and Loyal - a group that still buys, but "
    "spends less than it used to (see At-risk Revenue)."
)

st.subheader("5. Segments move fast: one quarter of migration")
chart(C.segment_flow(mart("segment_flow")), key="flow")
st.markdown(
    f"{pct(h['customers_changed_segment_one_quarter'], 0)} of customers changed segment between 2020-06-24 and 2020-09-22. "
    f"{pct(h['champions_to_slipping_one_quarter'], 0)} of June's Champions slipped into Slipping Regulars, and {pct(h['at_risk_to_lost_one_quarter'], 0)} of "
    "June's At Risk became Lost before anyone contacted them. This is why the segmentation is re-run every month with the same SQL and why audiences "
    "are re-scored on launch day, not taken from an old extract."
)

st.subheader("6. Why rules and not K-Means?")
km = m["kmeans"]
chart(C.kmeans_selection(mart("kmeans_k_selection"), km["k_final"]), key="ksel")
chart(C.kmeans_crosstab(mart("kmeans_crosstab"), mart("kmeans_profile")), key="kct")
st.markdown(
    f"""
- **No natural clusters.** Separation (silhouette) is best at k = 2 ({km['silhouette_by_k']['2']:.2f}, basically "recent vs not") and falls as k grows,
  so K-Means slices a continuum, as thresholds do, but with boundaries nobody chose.
- **It agrees where it matters:** the top cluster is {pct(km['top_cluster_champion_share'], 0)} Champions.
- **Its middle cluster is the case for the value axis:** cluster {km['mixed_cluster']} holds {pct(km['mixed_cluster_pct_customers'], 0)} of customers and
  {pct(km['mixed_cluster_pct_revenue'], 0)} of revenue but mixes {km['mixed_cluster_segments']} - customers of similar value whom the rules separate by
  recency because they need different actions.
- **It moves when refit:** refitting on last quarter's data changes the cluster of {pct(km['share_reassigned_by_refit'])} of customers whose behaviour did not change.
- **CRM tools need rules:** "last order 121-364 days ago and 3+ orders" can be typed into an audience builder; a distance to a centroid cannot.

Decision: rule-based segments plus a value tier for targeting; K-Means kept as a sense check.
"""
)

how_to_read(
    """
**Profile table.** One row per segment. *AOV* (average order value) = what a typical order is worth. *Median days between orders* = the usual
purchase cycle. *% online only* = share with no identified store purchase in the last 12 months. *% email reach* = share we can reach by email
for free; the rest need the app or paid channels. *% VIP* = share spending 1,000+ CU a year.

**Value grid.** Rows are the lifecycle segments, columns the value tiers. Each cell shows how many customers (or how much revenue) sit there.
It answers "who are the high-value customers?" more precisely than one segment name can.

**Backtest chart.** We pretend it is 2019-09-22 (blue) or 2020-06-24 (orange), put every customer in a segment using only what we knew then,
and look at what happened in the next 90 days. If the segments are useful, the bars line up from high to low at both dates, and they do.

**Migration heatmap.** Each row is a segment in June; the cells show where those customers were three months later. The diagonal is "stayed".
A dark cell off the diagonal is a flow worth a journey (e.g. Champions -> Slipping Regulars).

**K-Means.** A method that groups customers automatically. Left: how cleanly separated the groups are for different numbers of groups
(higher = cleaner); it is best at 2, so there are no natural groups. Right: for each automatic group, which of our segments its customers
belong to. We use it only to check the rules.
"""
)
