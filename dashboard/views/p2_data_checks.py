import pandas as pd
import streamlit as st

from common import chart, fmt_cu, fmt_n, how_to_read, mart, metrics, note, page_header, pct
from rfm import charts as C

page_header(
    "Data & Sanity Checks",
    "Can we trust the numbers: is the data complete, are the fields what we think they are, and how were the messy parts handled?",
)

m = metrics()
d = m["data"]
c1, c2, c3, c4 = st.columns(4)
c1.metric("Transaction rows", fmt_n(d["transaction_rows"]), "one row = one item", delta_color="off")
c2.metric("Orders (customer x day x channel)", fmt_n(d["orders"]), delta_color="off")
c3.metric("Data quality checks", f"{d['dq_pass']} pass / {d['dq_flag']} flagged", f"{d['dq_fail']} failed", delta_color="off",
          help="FLAG = known issue that is handled as described in the table")
c4.metric("Reconciliation checks", f"{d['reconciliation_checks_passed']} / {d['reconciliation_checks_total']} pass",
          "units, revenue, customers add up at every step", delta_color="off")

st.subheader("1. Data quality checks on the raw files")
dq = mart("dq_checks")


def _status_style(v: str) -> str:
    return {"PASS": "background-color:#e6f4e6;color:#006300", "FLAG": "background-color:#fdf1d8;color:#7a5200",
            "FAIL": "background-color:#fbe3e3;color:#9b1c1c"}.get(v, "")


view = dq[["check_id", "area", "check_name", "status", "observed", "expectation", "handling"]].rename(
    columns={"check_id": "#", "check_name": "check"})
st.dataframe(view.style.map(_status_style, subset=["status"]), hide_index=True, width="stretch", height=420)
note("Known row counts come from the Kaggle competition's data page. SQL: sql/01_data_quality_checks.sql")

st.subheader("2. Two fields that needed detective work")
left, right = st.columns(2)
with left:
    chart(C.weekly_channel(mart("weekly_channel_trend")), key="weekly")
with right:
    pp = mart("price_points")
    chart(C.price_points(pp), table=pp[["price_cu", "units"]].head(15).rename(columns={"price_cu": "price x 590", "units": "items sold"}),
          key="prices")

st.subheader("3. How the messy parts were handled")
st.markdown(
    """
| Issue | What we found | What we did | Why |
|---|---|---|---|
| **Identical repeated rows** | 2.97M rows (9.4%) repeat another row exactly (same customer, day, item, price, channel) | Kept, collapsed into a `units` column | There is no quantity column: two identical rows = two units bought. Deleting them would remove 9.4% of revenue |
| **Price outliers** | No zero or negative prices; 4,682 rows below 0.50 CU; ~0.1% of revenue far from the item's usual price | Kept and flagged | They are real paid amounts (markdowns). Scores use thresholds, so a few cents cannot move a customer's segment |
| **Extreme buyers** | Up to 569 identical units in one day; one account bought on 427 of 734 days | 864 accounts put on a **Review List**: kept in every total, no offers or paid media until CRM / retail ops have reviewed them | Bulk or near-daily buying looks like staff, resellers or business accounts, but the data cannot prove it; the rule moves 0.5% of revenue, so no segment result depends on it |
| **Recency base date** | Data ends 2020-09-22 | Snapshot = 2020-09-22 (recency 0 = bought that day) | Required by the brief; the campaign brief is written in the week after |
"""
)

st.subheader("4. Try the extreme-buyer rule yourself")
st.caption("Move the thresholds: the flagged count and revenue share are recomputed on all 1.36M customers.")
ex = mart("app_exclusion")
c1, c2, c3 = st.columns(3)
t_article = c1.slider("Units of ONE article in one order >=", 5, 60, 20, 1)
t_order = c2.slider("Units in one order >=", 30, 300, 100, 10)
t_days = c3.slider("Purchase days in two years >=", 60, 300, 150, 10)
flag_a = ex.max_units_same_article >= t_article
flag_b = ex.max_units_per_order >= t_order
flag_c = ex.lifetime_purchase_days >= t_days
flag = flag_a | flag_b | flag_c
total_rev = float(ex.lifetime_revenue_cu.sum())
k1, k2, k3, k4 = st.columns(4)
k1.metric("Accounts flagged", f"{int(flag.sum()):,}", f"{pct(flag.mean(), 3)} of customers", delta_color="off")
k2.metric("Their share of revenue", pct(ex.lifetime_revenue_cu[flag].sum() / total_rev, 2))
k3.metric("Flagged by bulk article / bulk order", f"{int(flag_a.sum()):,} / {int(flag_b.sum()):,}")
k4.metric("Flagged by very frequent buying", f"{int(flag_c.sum()):,}")
note(f"Default rule (20 / 100 / 150) flags {m['data']['review_list_customers']:,} accounts. "
     "Lowering the article threshold below ~10 starts to catch normal family shoppers (multipacks, kids' basics).")

st.subheader("5. Reconciliation: do the totals add up across tables?")
rec = mart("reconciliation_checks")
st.dataframe(rec.assign(passed=rec.passed.map({True: "PASS", False: "FAIL"}))
             .style.map(_status_style, subset=["passed"]).format({"left_value": "{:,.2f}", "right_value": "{:,.2f}", "difference": "{:,.2f}"}),
             hide_index=True, width="stretch")
note("Revenue is stored in integer cents, so these totals are exactly equal (difference 0.00), not just close. SQL: sql/13_reconciliation_checks.sql")

how_to_read(
    """
**Why this page exists.** In a company, the first question about any analysis is "are these numbers right?". This page is the evidence.

**Check table.** Each row is one test on the raw files. PASS = as expected. FLAG = we found something odd, decided how to handle it,
and wrote the decision in the last column. FAIL would stop the pipeline (there are none).

**Orders-by-channel chart.** The data only says channel 1 or 2. In spring 2020 shops closed because of COVID: channel 1 falls to zero
for those weeks while channel 2 jumps. That can only happen if 1 = store and 2 = online, so the labels are confirmed by a known event.

**Price chart.** Prices in the public file are disguised (e.g. 0.0508). Multiplying by 590 turns every price into a normal shelf price
(29.99, 19.99, 9.99 ...). That is why money in this project is shown in CU: it behaves like real currency, but we do not know which one.

**Extreme-buyer sliders.** Some accounts buy like a business (dozens of identical items, or almost every day). They could be staff,
resellers or business accounts; the data cannot tell which, so they go on a Review List instead of being labelled. Moving the sliders shows
how many accounts a stricter or looser rule would catch. They stay in all totals (so everything reconciles) but get no offers or paid
media until someone has checked them.

**Reconciliation table.** Every step of the pipeline (raw rows -> items -> orders -> customers -> segments) is checked to give exactly the
same total units, revenue and customers. If one step dropped or double-counted rows, a check would fail.
"""
)
