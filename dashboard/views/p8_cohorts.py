import pandas as pd
import streamlit as st

from common import chart, how_to_read, mart, metrics, note, page_header, pct
from rfm import charts as C

page_header(
    "Appendix: Cohorts & LTV",
    "Do customers who started in different months, or in different channels, keep buying at different rates and build up different value?",
)

m = metrics()
coh = mart("cohort_retention")
months = sorted(pd.to_datetime(coh["cohort_month"]).dt.strftime("%Y-%m").unique())

st.subheader("1. Retention by first-order month")
horizon = st.slider("Months to show", 6, 22, 12, 1, key="coh_h")
chart(C.cohort_heatmap(coh, horizon), key="heat")
note("Left-censoring: the data starts 2018-09-20, so a 'first order' in late 2018 is often an existing customer's first order in the window. "
     "Those early rows overstate retention. From about 2019-03 onwards a cohort had 5+ months without any order before joining, so it is mostly new customers.")

st.subheader("2. Observed lifetime value by first channel")
c1, c2 = st.columns(2)
first = c1.select_slider("First cohort", options=months, value="2019-01", key="ltv_a")
last = c2.select_slider("Last cohort", options=months, value="2019-08", key="ltv_b")
if first > last:
    first, last = last, first
max_follow = (pd.Period("2020-08", "M") - pd.Period(last, "M")).n
n_months = min(12, max_follow)
chart(C.ltv_curves(coh, f"{first}-01", f"{last}-01", n_months), key="ltv")
note(f"Showing {n_months} months of follow-up, the most every selected cohort has. Revenue is cumulative CU per customer of the cohort.")

st.subheader("3. The order ladder")
lad = mart("order_ladder")
chart(C.order_ladder(lad), table=lad.round(3), key="ladder")
ol = m["order_ladder"]["new: first order 2019-03-01 to 2019-09-22"]
st.markdown(
    f"For likely new customers, {pct(ol['1'], 0)} place a second order within a year; once they have two orders, {pct(ol['2'], 0)} place a third, "
    f"and the chance keeps rising. The first repeat purchase is the hardest step, which is why the second-order journey is the one place "
    "where the plan rolls out a discount."
)

how_to_read(
    """
**Cohort.** All customers whose first order (in this data) fell in the same month. Row 2019-06 = everyone who first bought in June 2019.

**Heatmap.** Each cell = share of the cohort that bought again in that later month (M1 = the next calendar month). Darker = more customers came back.
Read across a row to see how one cohort fades; read down a column to compare cohorts at the same age. The first rows (late 2018) look much better
because many of those "new" customers were really existing customers whose first order in the data happened to be in that month.

**LTV curves.** Observed lifetime value = cumulative revenue per customer, month by month after their first order. It is what they actually spent,
not a prediction. The lines compare customers whose first order was online, in store, or both on the same day. Pick cohorts with the sliders;
the chart only shows months that every selected cohort has fully completed.

**Order ladder.** Of the customers who have placed n orders, how many go on to place one more within a year of their first order.
The biggest drop is from the first to the second order; after that, customers become steadily more loyal.
"""
)
