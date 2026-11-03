import pandas as pd
import streamlit as st

from common import chart, customers, how_to_read, mart, note, page_header, pct, table
from rfm import charts as C
from rfm.segments import SEGMENT_ORDER, Thresholds, assign_segments, quantile_edges, quantile_scores, score, segment_summary

page_header(
    "RFM Scoring",
    "How do we turn Recency, Frequency and Monetary into scores, and why these cut-offs rather than the textbook quintiles?",
)

DEFAULT = Thresholds.from_config()

st.subheader("1. Recency: what the data says about time since the last order")
basis = st.radio("Reference date for the backtest", ["2019-09-22 (same season last year)", "2020-06-24 (last quarter)"],
                 horizontal=True, key="rc_basis")
curve = mart("recency_return_curve")
snap = "backtest_seasonal" if basis.startswith("2019") else "backtest_recent"
chart(C.return_curve(curve, snap), data=curve[curve.snapshot_name == snap][
    ["frequency_group", "recency_bucket_start", "recency_bucket_end", "customers", "return_rate_90d"]], key="curve")
st.markdown(
    "The curve falls smoothly (about 4-5 points every 15 days for repeat buyers) with no cliff, so it supports recency as the main "
    "axis but does not pick the cut-offs. The cut-offs are chosen as round numbers close to the quintiles (section 2) that match how the "
    "CRM team works: **30 / 60 days** (a normal purchase cycle for good customers), **120 days** (a season missed), **180 days** "
    "(two seasons) and **365 days** (a full year without buying = Lost, the standard 12-month-active definition). At 120 days, "
    "repeat buyers still come back at about 44%, which is why the 61-120-day groups get a cheap nudge, not a win-back offer."
)

st.subheader("2. Fixed business thresholds vs quintiles")
cust = customers()
active = cust[cust.frequency_12m > 0]
method = st.radio("Scoring method", ["Business thresholds (used)", "Quintiles (textbook alternative)"], horizontal=True)
if method.startswith("Business"):
    sc = score(active, DEFAULT).rename(columns={"r_score": "r", "f_score": "f", "m_score": "m"})
    chart(C.score_distribution(sc, "fixed business thresholds"), key="dist_b")
else:
    q = quantile_scores(active).rename(columns={"r_q": "r", "f_q": "f", "m_q": "m"})
    chart(C.score_distribution(q, "quintiles"), key="dist_q")
    n_f = q["f"].nunique()
    st.warning(f"With quintiles the frequency score only takes **{n_f} distinct values**: {pct((active.frequency_12m == 1).mean(), 0)} of "
               "active customers have exactly one order, so several quintile edges fall on the same value and the bands collapse.")
edges = quantile_edges(active)
business = {"recency_days": "30 / 60 / 120 / 180 (365+ = Lost)", "frequency_12m": "1 / 2 / 3-4 / 5-9 / 10+",
            "monetary_12m_cu": "50 / 100 / 200 / 400"}
table(C.quantile_vs_business(edges, business), hide_index=True, width="stretch")
st.markdown(
    "**Why fixed thresholds.** Recency and Monetary cut-offs are the active-customer quintiles rounded to numbers people can say out loud "
    f"(R {' / '.join(f'{v:.0f}' for v in edges['recency_days'])} days -> 30 / 60 / 120 / 180; "
    f"M {' / '.join(f'{v:.0f}' for v in edges['monetary_12m_cu'])} CU -> 50 / 100 / 200 / 400). Frequency is set by hand, because "
    f"{pct((active.frequency_12m == 1).mean(), 0)} of active customers have exactly one order and {pct((active.frequency_12m == 2).mean(), 0)} two, "
    "so quintile edges tie and would split identical customers at random. Once chosen, the numbers stay fixed: quintile edges move every month "
    "with the customer base, and an audience called 'R5' must mean the same thing in October as in September."
)
sens = mart("threshold_sensitivity")
with st.expander("Sensitivity: segment sizes if every cut-off in a group moves by 25%", expanded=False):
    piv = sens[sens.variant != "Default"].pivot(index="segment", columns="variant", values="pct_change")
    piv = piv.reindex([s for s in SEGMENT_ORDER if s in piv.index and s not in ("Lost", "Review List", "New Customers")])
    table((100 * piv).round(0).astype(int).astype(str) + "%", width="stretch")
    big = piv.loc["Champions"].abs().max()
    st.caption(f"Champions move by {100 * big:.0f}% at most. Segments whose borders are only a few orders wide (Loyal, Slipping Regulars, "
               "At Risk) move a lot more, e.g. At Risk grows sharply when 'used to buy often' starts at 2 orders instead of 3. Segment sizes "
               "depend on where the lines are drawn; that is why the thresholds are frozen, documented in the segmentation spec, and "
               "changed only with the CRM Manager's sign-off.")

st.subheader("3. Move the thresholds and watch the segments change")
st.caption("Recomputed live on all 1.36M customers with the same rules as sql/05_customer_rfm.sql.")
with st.expander("Thresholds", expanded=True):
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown("**Recency (days since last order)**")
        r5 = st.slider("R5 if at most", 7, 60, DEFAULT.r5_max_days, key="r5")
        r4 = st.slider("R4 if at most", 31, 120, DEFAULT.r4_max_days, key="r4")
        r3 = st.slider("R3 if at most", 61, 240, DEFAULT.r3_max_days, key="r3")
        r2 = st.slider("R2 if at most", 91, 300, DEFAULT.r2_max_days, key="r2")
    with c2:
        st.markdown("**Frequency (orders in 12 months)**")
        f5 = st.slider("F5 if at least", 6, 20, DEFAULT.f5_min_orders, key="f5")
        f4 = st.slider("F4 if at least", 3, 9, DEFAULT.f4_min_orders, key="f4")
        f3 = st.slider("F3 if at least", 2, 5, DEFAULT.f3_min_orders, key="f3")
    with c3:
        st.markdown("**Monetary (CU in 12 months)**")
        m5 = st.slider("M5 if at least", 200, 1000, int(DEFAULT.m5_min_cu), 25, key="m5")
        m4 = st.slider("M4 if at least", 100, 500, int(DEFAULT.m4_min_cu), 25, key="m4")
        m3 = st.slider("M3 if at least", 50, 250, int(DEFAULT.m3_min_cu), 10, key="m3")
        m2 = st.slider("M2 if at least", 10, 120, int(DEFAULT.m2_min_cu), 5, key="m2")
    with c4:
        st.markdown("**Lifecycle**")
        new_days = st.slider("New Customer if first order within (days)", 30, 180, DEFAULT.new_customer_days, 10, key="new")
        lost_days = st.slider("Lost if no order for (days)", 181, 365, 365, 5, key="lost",
                              help="F and M are always measured over 12 months; this only moves the Lost boundary")


def increasing(values: list[int], step: int = 1) -> tuple[list[int], bool]:
    """Force strictly increasing cut-offs (each at least `step` above the previous)."""
    out, fixed = [values[0]], False
    for v in values[1:]:
        if v <= out[-1]:
            v, fixed = out[-1] + step, True
        out.append(v)
    return out, fixed


(r5, r4, r3, r2, lost_days), fix_r = increasing([r5, r4, r3, r2, lost_days])
(f3, f4, f5), fix_f = increasing([f3, f4, f5])
(m2, m3, m4, m5), fix_m = increasing([m2, m3, m4, m5], 5)
if fix_r or fix_f or fix_m:
    st.info(f"Cut-offs must increase, so they were adjusted to: R {r5}/{r4}/{r3}/{r2}/{lost_days} days, "
            f"F {f3}/{f4}/{f5} orders, M {m2}/{m3}/{m4}/{m5} CU.")

th = DEFAULT.with_changes(r5_max_days=r5, r4_max_days=r4, r3_max_days=r3, r2_max_days=r2, f5_min_orders=f5, f4_min_orders=f4,
                          f3_min_orders=f3, m5_min_cu=m5, m4_min_cu=m4, m3_min_cu=m3, m2_min_cu=m2,
                          new_customer_days=new_days, lookback_days=lost_days)
base = segment_summary(cust, cust["segment"])
new = segment_summary(cust, assign_segments(cust, th))
chart(C.segment_size_compare(base, new), key="cmp")
tbl = base.merge(new, on="segment", suffixes=(" (default)", " (yours)"))
tbl = tbl[["segment", "customers (default)", "customers (yours)", "pct_revenue_12m (default)", "pct_revenue_12m (yours)"]]
for col in ("pct_revenue_12m (default)", "pct_revenue_12m (yours)"):
    tbl[col] = (100 * tbl[col]).round(1)
tbl.columns = ["Segment", "Customers (default)", "Customers (yours)", "% 12m revenue (default)", "% 12m revenue (yours)"]
table(tbl, hide_index=True, width="stretch")
note("Things to try: raise 'Lost if no order for' to see how many Hibernating customers sit just inside the 12-month window; "
     "lower F4 to 4 orders to see Loyal and Champions grow.")

st.subheader("4. Where customers sit on the Recency x Frequency grid")
what = st.radio("Show", ["customers", "12-month revenue"], horizontal=True, key="grid_what")
grid = mart("rf_grid")
chart(C.rf_heatmap(grid, "customers" if what == "customers" else "revenue_12m_cu"), data=grid, key="grid")

how_to_read(
    """
**R, F and M in one line each.** *Recency* = days since the customer's last order (smaller is better). *Frequency* = number of orders
in the last 12 months (an order = everything bought on one day in one channel). *Monetary* = what they spent in those 12 months, in CU.

**Section 1 - the curve.** Each dot is a group of customers who had last ordered a similar number of days before a past date.
The height is the share of them who came back within the next 90 days. Customers who ordered recently (left) come back far more often.
The blue line (customers with 2+ orders) falls from about 78% to about 12% over a year. Because there is no sudden drop, the cut-offs
are chosen to match how the CRM team works (monthly cycle, one season, two seasons, one year).

**Section 2 - two ways to give scores.** The textbook way is quintiles: sort customers and give the top 20% a 5, the next 20% a 4 and so on.
It breaks here because a third of active customers bought exactly once, so you cannot split them into different 20% groups without
cutting identical customers apart. Fixed thresholds also keep the meaning of "R5" the same every month.

**Section 3 - sliders.** This is a live re-segmentation. Grey bars = segment sizes with our rules, blue bars = with your thresholds;
the numbers above the blue bars show how many customers moved. It is a good way to show that the segments are not arbitrary:
reasonable changes move a few thousand customers between neighbouring segments, they do not reshuffle the base.

**Section 4 - the grid.** Rows = recency score, columns = frequency score; each cell shows how many customers (or how much revenue)
sit there. The top-right corner (recent and frequent) is where Champions live.
"""
)
