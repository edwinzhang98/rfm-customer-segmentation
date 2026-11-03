# 02 — Metric definitions

Every number in this project is built from the definitions on this page. They are written so that a second analyst can rebuild any figure from the raw files and get the same result to the cent. Each metric gives the meaning in plain words first, then the exact rule, the unit, where it is computed and what to watch out for. "Check value" rows give the result at the 2020-09-22 snapshot, so a rebuild can be compared line by line.

**Conventions used throughout**

- **Parameters** (snapshot dates, windows, thresholds, Review List rule, economics) live in [`config.yaml`](../config.yaml). The SQL files repeat the same values as defaults so each file can run on its own; `python run.py` passes the config values in.
- **Dates** are calendar dates. "Days between" two dates is a plain date difference (2020-09-22 minus 2020-09-21 = 1). Windows include both end dates unless stated otherwise.
- **Money** is in CU (section 1.5), stored as integer cents (`*_cents` columns) so that every total adds up exactly; it is divided by 100 only for display. All revenue is gross demand (section 1.6).
- **"Customers"** means the 1,362,281 customers with at least one order between 2018-09-20 and 2020-09-22, unless stated otherwise. Review List accounts are inside every total.
- **Rates** are shares of customers; differences in rates are in percentage points (pp).
- Assumptions behind the economics and the backtests are logged in [assumptions.md](assumptions.md); the checks behind the inputs are in [03_data_quality_checks.md](03_data_quality_checks.md).

---

## 1. Building blocks

### 1.1 Snapshot date

| | |
|---|---|
| **Plain words** | The day we freeze the customer base and look back from. Everything "as of" a snapshot uses only orders on or before that day. |
| **Rule** | Current snapshot = **2020-09-22**, the last transaction date in the data. Two backtest snapshots use exactly the same rules: **2019-09-22** (same season one year earlier, `backtest_seasonal`) and **2020-06-24** (the last full 90 days, `backtest_recent`). |
| **Unit** | date |
| **Computed in** | `config.yaml` → `snapshot`; `sql/05_customer_rfm.sql` (CTE `snapshots`), one row per snapshot × customer in `customer_rfm.parquet` |
| **Caveats** | Recency 0 means "bought on the snapshot day". For the campaign the audiences are rebuilt with the same SQL on launch day (2020-09-28); the segment a customer has on that day is the segment of record for the measurement, even if they move later (section 6.1). |

### 1.2 Item row and units

| | |
|---|---|
| **Plain words** | One row in the transactions file is one item bought. There is no quantity column, so two identical T-shirts bought together appear as two identical rows. |
| **Rule** | Rows with the same customer, date, article, price and channel are collapsed into one sales line; `units` = number of identical rows; `line_revenue_cents` = `units` × `unit_price_cents`. |
| **Unit** | units (items) |
| **Computed in** | `sql/02_fct_sales_lines.sql` → `fct_sales_lines.parquet` (grain: customer × date × channel × article × unit price) |
| **Check value** | 31,788,324 rows → 28,813,419 sales lines carrying the same 31,788,324 units; 2,974,905 rows (9.4%) are extra units of an item already on the line (data-quality check 6) |
| **Caveats** | Deleting the repeats would remove 9.4% of units and 9.7% of revenue. The same article bought at two different prices in one order stays as two lines. |

### 1.3 Order

| | |
|---|---|
| **Plain words** | One shopping trip or one online checkout: everything a customer bought on one day in one channel. |
| **Rule** | `GROUP BY customer_id, order_date, sales_channel_id` over the sales lines; `n_lines`, `n_units` and `revenue_cents` are summed. |
| **Unit** | orders |
| **Computed in** | `sql/03_fct_orders.sql` → `fct_orders.parquet` |
| **Check value** | 9,174,457 orders over two years; 4,408,759 in the 12 months to 2020-09-22 |
| **Caveats** | The data has no order id. (1) Several online orders placed on the same day collapse into one order, so order counts (and Frequency) are a lower bound and online AOV an upper bound compared with a system that has order ids; the size of this effect cannot be measured from this data. (2) A store visit and an online order on the same day are two orders: 94,278 of 9,080,179 customer-days (1.0%). (3) A store purchase is only recorded when the shopper identifies as a member (section 2.10). |

### 1.4 Sales channel

| | |
|---|---|
| **Plain words** | Whether an order was placed in a store or online. |
| **Rule** | `sales_channel_id` 1 = **Store**, 2 = **Online** (column `channel` in `fct_orders`). |
| **Unit** | category |
| **Computed in** | `sql/03_fct_orders.sql`; encoding checked in `sql/01_data_quality_checks.sql` (checks 14 and 15) |
| **Caveats** | The source only says 1 or 2. The labels follow from the COVID store closures: channel 1 has no sales on 45 of the 47 days from 2020-03-20 to 2020-05-05 (9 stray rows on the other two) while channel 2 jumps, and channel 1 comes back when stores reopen on 2020-05-06. |

### 1.5 CU (currency unit) and the ×590 price scale

| | |
|---|---|
| **Plain words** | The public file disguises prices by dividing them by a constant. Multiplying by 590 gives back normal shelf prices (9.99, 19.99, 14.99 …). All money in this project is in these units, called CU. The currency is not disclosed; the price points are on the scale of a major currency. |
| **Rule** | `unit_price_cents = ROUND(price × 590 × 100)` (BIGINT). CU = cents ÷ 100. |
| **Unit** | CU, stored as integer cents of CU |
| **Computed in** | `sql/02_fct_sales_lines.sql`; scale in `config.yaml` → `money.price_scale`; evidence in data-quality checks 17 and 18 and in `price_points.parquet` |
| **Evidence** | price × 590 is a whole number of cents on every one of the 31.8M rows (largest deviation 7×10⁻¹²); the three most common results are 9.99, 19.99 and 14.99 CU; the 15 most common price points cover 68% of items sold; the most expensive item is 349.00 CU. |
| **Caveats** | Shares, ratios and rankings do not depend on the unit. CU amounts must not be converted into any real currency. The planning costs (0.01 CU per email, 0.30 CU per paid-social contact) are set on this major-currency scale. |

### 1.6 Revenue (gross demand)

| | |
|---|---|
| **Plain words** | What customers paid at the till or the online checkout, before any returns. |
| **Rule** | Sum of `line_revenue_cents` (units × unit price paid). Markdowns are already in the paid price. |
| **Unit** | CU |
| **Computed in** | `sql/02`–`sql/05`; totals reconciled in `sql/13_reconciliation_checks.sql` |
| **Check value** | 521,941,124.69 CU over two years; 247,265,062.98 CU in the 12 months to 2020-09-22 |
| **Caveats** | The data has **no returns**, so every revenue figure is gross demand. Fashion return rates are typically much higher online than in store, so online-vs-store value comparisons lean towards online. The campaign economics take returns out inside the contribution margin (section 5.4). The 25% online / 8% store returns haircut shown on the drill-down page is illustrative only, not a measured rate. |

---

## 2. Customer measures (the RFM inputs)

All measures in this section are computed per snapshot × customer in `sql/05_customer_rfm.sql` → `customer_rfm.parquet`.

### 2.1 Active customer (12 months)

| | |
|---|---|
| **Plain words** | A customer who bought at least once in the last 12 months: the standard CRM definition of "active". |
| **Rule** | `frequency_12m > 0`, i.e. at least one order with `snapshot_date − order_date < 365`. For the current snapshot the window is **2019-09-24 to 2020-09-22** inclusive (365 days; 2020 is a leap year). Equivalent to `recency_days ≤ 364`. The backtest windows are 2018-09-23 to 2019-09-22 and 2019-06-26 to 2020-06-24. |
| **Unit** | customers |
| **Computed in** | `sql/05_customer_rfm.sql` (flag `in_12m`); `metrics.json` → `data.active_12m_customers` |
| **Check value** | 993,492 active customers = 72.9% of customers with an order |
| **Caveats** | Includes 679 active Review List accounts. Analyses that leave the Review List out (channel comparison, K-Means check) start from 992,813 active customers. |

### 2.2 Recency (`recency_days`)

| | |
|---|---|
| **Plain words** | Days since the customer's last order. Smaller is better. |
| **Rule** | `snapshot_date − last_order_date`, where `last_order_date` is the latest order on or before the snapshot. |
| **Unit** | days (integer; 0 = bought on the snapshot day) |
| **Computed in** | `sql/05_customer_rfm.sql` (CTE `measures`) |
| **Caveats** | Capped by the start of the data: at most 733 days at 2020-09-22 and 367 days at 2019-09-22. That cap is why the 2019 backtest cannot describe Lost customers (section 4.5). |

### 2.3 Frequency (`frequency_12m`)

| | |
|---|---|
| **Plain words** | Number of orders in the last 12 months. |
| **Rule** | Count of orders (section 1.3) inside the 12-month window (section 2.1). |
| **Unit** | orders |
| **Computed in** | `sql/05_customer_rfm.sql` |
| **Check value** | Sum over all customers = 4,408,759 (reconciliation check "orders 12m") |
| **Caveats** | Inherits the order definition: same-day online orders count once; a store visit plus an online order on the same day count twice. 34% of active customers have exactly one order and 16% have two. |

### 2.4 Monetary (`monetary_12m`)

| | |
|---|---|
| **Plain words** | What the customer spent in the last 12 months. |
| **Rule** | Sum of `revenue_cents` over the same window → `monetary_12m_cents` (integer cents); `monetary_12m_cu` = `monetary_12m_cents` ÷ 100. 0 when there is no order in the window. |
| **Unit** | CU (stored as integer cents) |
| **Computed in** | `sql/05_customer_rfm.sql` |
| **Check value** | Sum = 247,265,062.98 CU (reconciliation check "revenue 12m") |
| **Caveats** | Gross demand. Thresholds compare the exact value: 199.99 CU scores M3, 200.00 CU scores M4. |

### 2.5 Tenure (`tenure_days`)

| | |
|---|---|
| **Plain words** | How long ago the customer's first order in the data was. |
| **Rule** | `snapshot_date − first_order_date` (first order on or after 2018-09-20). |
| **Unit** | days |
| **Computed in** | `sql/05_customer_rfm.sql` |
| **Caveats** | Left-censored: the data starts 2018-09-20, so the first order in the data is not always the first order ever, and tenure is a lower bound. It is used only for the New Customer rule (section 3.3). |

### 2.6 R, F and M scores

**Plain words.** Each customer gets a score from 1 to 5 on each of the three measures (0 if they have not bought in 12 months). Higher is better.

| Score | R: days since last order | F: orders in 12 months | M: CU spent in 12 months |
|---|---|---|---|
| 5 | 0–30 | 10+ | 400+ |
| 4 | 31–60 | 5–9 | 200 to under 400 |
| 3 | 61–120 | 3–4 | 100 to under 200 |
| 2 | 121–180 | 2 | 50 to under 100 |
| 1 | 181–364 | 1 | under 50 |
| 0 | 365+ (Lost) | none | none |

**Rule.** `CASE` statements in `sql/05_customer_rfm.sql` (CTE `scored`); `rfm_code` concatenates the three digits (e.g. `554`). The dashboard uses a Python copy of the same rules (`src/rfm/segments.py`, `score`), and `tests/test_segments_parity.py` checks that both give the same scores and segment for every customer at all three snapshots. Thresholds: `config.yaml` → `rfm_thresholds`.

**Why these cut-offs, not quintiles.**

- **R and M** are set near the quintiles of active customers, then moved to business periods and round amounts the CRM team can say out loud: R quintile edges 23 / 60 / 112 / 215 days → 30 / 60 / 120 / 180; M quintile edges 40 / 85 / 166 / 352 CU → 50 / 100 / 200 / 400. The recency cut-offs also read as business periods: 30 / 60 days = a normal purchase cycle for good customers, 120 = a season missed, 180 = two seasons, 365 = a full year.
- **F** is set by hand: 34% of active customers have exactly one order and 16% two, so the quintile edges fall on 1 / 2 / 3 / 7 orders and would split customers with identical behaviour at random.
- **Fixed, not re-cut every month.** Quintile edges move with the customer base; an audience called "R5" has to mean the same thing in October as in September.
- **What the recency curve does and does not show.** The chance of buying again within 90 days falls smoothly with recency, with no knee (repeat buyers in the 2019 backtest: 78% at 0–14 days, 43% at 120–134 days; `recency_return_curve.parquet`). That supports recency as the main axis; it does not prove where the cut-offs should sit.

**How much the segments depend on the cut-offs.** Change in segment size when every cut-off in one group moves by 25% (one group at a time):

<!-- BEGIN:threshold_sensitivity -->
<!-- generated by `python run.py --steps docs` from the pipeline outputs; edit src/rfm/docgen.py, not this block -->

| Segment             | Frequency cut-offs +25%   | Frequency cut-offs -25%   | Monetary cut-offs +25%   | Monetary cut-offs -25%   | Recency cut-offs +25%   | Recency cut-offs -25%   |
|:--------------------|:--------------------------|:--------------------------|:-------------------------|:-------------------------|:------------------------|:------------------------|
| Champions           | -9%                       | +8%                       | -10%                     | +9%                      | +9%                     | -13%                    |
| Loyal               | -42%                      | +62%                      | +58%                     | -53%                     | +15%                    | -21%                    |
| Slipping Regulars   | -29%                      | +38%                      | +0%                      | +0%                      | -22%                    | +20%                    |
| Potential Loyalists | +26%                      | -28%                      | +0%                      | +0%                      | +22%                    | -25%                    |
| Needs Attention     | +13%                      | -17%                      | +0%                      | +0%                      | +18%                    | -31%                    |
| At Risk             | -27%                      | +73%                      | -8%                      | +16%                     | -27%                    | +53%                    |
| Hibernating         | +9%                       | -23%                      | +2%                      | -5%                      | -13%                    | +16%                    |

<!-- END:threshold_sensitivity -->

**Caveats.** Segment sizes are a consequence of where the lines are drawn: Champions move by at most 13%, narrow segments (Loyal, Slipping Regulars, At Risk) by much more. That is why the thresholds are frozen in `config.yaml` and change only with the CRM Manager's sign-off.

### 2.7 Purchase cycle (median days between orders)

| | |
|---|---|
| **Plain words** | A segment's usual time between two orders. |
| **Rule** | Per customer with 2+ orders in the 12-month window: `avg_days_between_orders_12m` = (last order date − first order date in the window) ÷ (`frequency_12m` − 1). Per segment: the median of that value (`median_days_between_orders`). |
| **Unit** | days |
| **Computed in** | `sql/05_customer_rfm.sql` (customer); `sql/09_segment_profile.sql` (segment) |
| **Check value** | Champions 32.6 days; Slipping Regulars 39.8; At Risk 38.0 |
| **Caveats** | Only customers with 2+ orders in the window count, so it describes a segment's repeat buyers. For New Customers it is squeezed into at most 90 days (11 days); Lost has none. A store and an online order on the same day add a zero gap. |

### 2.8 Average order value (AOV)

| | |
|---|---|
| **Plain words** | What a typical order is worth. |
| **Rule** | Total revenue ÷ number of orders over the group (a ratio of sums, not the average of each customer's AOV). Variants: **segment AOV** = 12-month revenue ÷ 12-month orders (`aov_12m_cu`; Lost: two-year revenue ÷ two-year orders, `aov_2y_cu`); **audience AOV** in the campaign model = the same ratio over the audience (`campaign_inputs.aov_cu`); **order-channel AOV** = revenue ÷ orders by the channel of the order, over the 12-month window (`channel_order_aov.parquet`). |
| **Unit** | CU per order |
| **Computed in** | `sql/09_segment_profile.sql`; `src/rfm/campaign.py` (`audience_inputs`); `src/rfm/analysis.py` (`channel_tables`) |
| **Check value** | Champions 58.7 CU; Loyal 23.8 CU. For the same omnichannel customers an online order is 69.6 CU and a store order 33.4 CU. |
| **Caveats** | Gross demand. Same-day online orders collapse into one order (section 1.3), which raises online AOV a little. |

### 2.9 Email reach (fashion-news subscription)

| | |
|---|---|
| **Plain words** | Customers we can email at almost no cost. |
| **Rule** | `is_newsletter_subscriber` = `fashion_news_frequency` is "Regularly" or "Monthly". "NONE", "None" and missing = not reachable. Segment email reach = share of subscribers in the segment (`pct_newsletter`). |
| **Unit** | customers; share |
| **Computed in** | `sql/04_dim_customers.sql`; `sql/09_segment_profile.sql` |
| **Check value** | 478,258 subscribers = 34.9% of the 1,371,980 customers in the customer file and 37.1% of active customers |
| **Caveats** | Subscription is not deliverability: bounces and recent unsubscribes are not in the data. The customer file is one undated extract, so the same status is used at every snapshot, including the backtests. The `FN` and `Active` fields are not used. Email-only arms can reach subscribers only, so their experiment population is the subscribers (section 5.1). |

### 2.10 Channel profile

| | |
|---|---|
| **Plain words** | Whether a customer buys only online, only in store, or both. |
| **Rule** | **Operational, 12 months (`channel_12m`)**: "No 12m orders" if `frequency_12m` = 0; "Online only" if there is no store order in the window; "Store only" if there is no online order; otherwise "Omnichannel". Rebuilt at every snapshot. **Context, two years (`channel_profile_2y`, from `dim_customers.channel_profile`)**: the same rule over every order from 2018-09-20 to 2020-09-22. |
| **Unit** | category |
| **Computed in** | `sql/05_customer_rfm.sql` (`channel_12m`); `sql/04_dim_customers.sql` (`channel_profile`) |
| **Check value** | Active customers outside the Review List: 482,607 online only (48.6%), 187,556 store only, 322,650 omnichannel |
| **Leakage rule** | The two-year profile includes orders made *after* each backtest date. It is never joined to backtest outcomes: every backtest, the composition adjustment and the channel comparison use the `channel_12m` rebuilt at that snapshot. |
| **Caveats** | "Online only" means "no *identified* store purchase": store purchases appear only when the shopper identifies as a member. The 12-month profile is what audiences and the channel treatment rules use. |

### 2.11 Value tier

| | |
|---|---|
| **Plain words** | How much a customer is worth today, independent of where they are in the lifecycle. |
| **Rule** | On `monetary_12m_cu`: **VIP** 1,000+ CU; **High** 400 to under 1,000; **Mid** 200 to under 400; **Low** under 200 (with at least one order); **None** = no order in 12 months. High and Mid reuse the M5 and M4 cut-offs. |
| **Unit** | category |
| **Computed in** | `sql/05_customer_rfm.sql`; `src/rfm/segments.py` (`value_tier`); `value_grid.parquet` |
| **Check value** | 41,118 VIP customers (3.0% of customers) with 27.9% of 12-month revenue |
| **Caveats** | Gross demand, so customers who return a lot are ranked too high. The tier decides paid reach (paid social only for At Risk customers 181–364 days quiet with 200+ CU) and keeps VIPs visible wherever they sit. |

---

## 3. Segments

### 3.1 Segment rules

**Plain words.** Ten groups, each tied to one CRM action. Rules are applied in this order; the first rule that matches wins.

| Order | Segment | Rule | In plain words |
|---|---|---|---|
| 1 | Review List | `is_excluded` (section 3.4) | Bulk or near-daily buying pattern |
| 2 | Lost | recency ≥ 365 days | No order in the last 12 months |
| 3 | New Customers | tenure < 90 days | First order within the last 90 days |
| 4 | Champions | R ≥ 4 and F ≥ 4 and M ≥ 4 | Bought in the last 60 days, 5+ orders and 200+ CU in 12 months |
| 5 | Loyal | R ≥ 4 and F ≥ 4 | Bought in the last 60 days, 5+ orders, under 200 CU (frequent, small baskets) |
| 6 | Slipping Regulars | R = 3 and F ≥ 4 | 5+ orders in 12 months, but 61–120 days quiet |
| 7 | Potential Loyalists | R ≥ 4 | Bought in the last 60 days, 1–4 orders, not new |
| 8 | Needs Attention | R = 3 | 61–120 days quiet, 1–4 orders |
| 9 | At Risk | F ≥ 3 or M ≥ 4 (R is 1 or 2 by this point) | 121–364 days quiet, but used to buy often (3+ orders) or a lot (200+ CU) |
| 10 | Hibernating | everything else | 121–364 days quiet, 1–2 orders and under 200 CU |

**Computed in.** `sql/05_customer_rfm.sql` (final `CASE`, column `segment`); Python copy in `src/rfm/segments.py` (`assign_segments`), checked by the parity test. The full audience specification is in [segmentation_spec.md](segmentation_spec.md).

**Expected counts** for anyone rebuilding the audiences (current snapshot):

<!-- BEGIN:segment_counts -->
<!-- generated by `python run.py --steps docs` from the pipeline outputs; edit src/rfm/docgen.py, not this block -->

| Segment                                         | Customers     | 12-month revenue (CU)   | Two-year revenue (CU)   |
|:------------------------------------------------|:--------------|:------------------------|:------------------------|
| Champions                                       | 190,320       | 133,882,338             | 252,123,399             |
| Loyal                                           | 33,612        | 4,990,355               | 11,012,863              |
| Slipping Regulars                               | 61,655        | 25,619,860              | 51,038,065              |
| Potential Loyalists                             | 124,517       | 19,235,065              | 40,676,007              |
| New Customers                                   | 71,117        | 4,895,660               | 4,895,660               |
| Needs Attention                                 | 137,675       | 17,669,055              | 36,532,607              |
| At Risk                                         | 89,848        | 23,417,805              | 48,390,667              |
| Hibernating                                     | 284,069       | 16,276,889              | 37,425,234              |
| Lost                                            | 368,604       | 0                       | 37,088,648              |
| Review List                                     | 864           | 1,278,036               | 2,757,975               |
| **Total with an order**                         | **1,362,281** | **247,265,063**         | **521,941,125**         |
| Registered, no order in the window (not scored) | 9,699         | 0                       | 0                       |
| **All customers in customers.csv**              | **1,371,980** |                         |                         |

<!-- END:segment_counts -->

**Caveats.** Because of the order, a customer in their first 90 days is always a New Customer even if their orders would already make them a Champion, and the Review List overrides everything. Segments change fast (section 3.7), so audiences are always rebuilt on the day they are used.

### 3.2 Lost and churn

| | |
|---|---|
| **Plain words** | A customer who has not bought for a full year has churned, for CRM purposes. |
| **Rule** | **Lost** = `recency_days ≥ 365` (no order in the 12-month window), so every customer with an order is either active or Lost. **Churn risk** = At Risk; **early warning** = Slipping Regulars. The "churn signal" headline counts both: 151,503 customers (11.1%). A **churn rate** quoted for a segment is the share of it that is Lost one quarter later (section 3.7): about 8% of the At Risk customers of 2020-06-24 were Lost by 2020-09-22. |
| **Unit** | customers; share |
| **Computed in** | `sql/05_customer_rfm.sql`; `sql/14_segment_flow.sql`; `metrics.json` → `headline.churn_signal_*`, `headline.at_risk_to_lost_one_quarter` |
| **Caveats** | Churn here means inactivity, not a cancelled contract: Lost customers do come back (6.3% are expected to buy in the next 90 days, section 4.2). Lost has no 12-month spend, so it has no usual pace and no gap (section 4.6). |

### 3.3 New Customer

| | |
|---|---|
| **Plain words** | Someone whose first order was in the last 90 days. |
| **Rule** | `tenure_days < 90` (0–89 days), applied after Review List and Lost and before every other rule. At 2020-09-22: first order between 2020-06-25 and 2020-09-22. |
| **Unit** | customers |
| **Computed in** | `sql/05_customer_rfm.sql`; `config.yaml` → `rfm_thresholds.new_customer_days` |
| **Check value** | 71,117 customers |
| **Caveats** | "First order in the data": a customer whose earlier purchases were all before 2018-09-20 looks new. At the current snapshot a New Customer has had no order in the 21 months before, so few are affected; at the 2019-09-22 backtest the clean history is only 9 months, so that backtest's New Customers include more returning customers. The same applies to first-order cohorts (section 4.9). |

### 3.4 Review List

| | |
|---|---|
| **Plain words** | Accounts that buy in bulk or almost every day. The data cannot say whether they are staff, resellers, business accounts or very large households, so they are not labelled; they are held back from offers until someone has checked them. |
| **Rule** | `is_excluded` = TRUE if any of: (a) 20+ units of one article in one order (summed across price lines); (b) 100+ units in one order; (c) purchases on 150+ different days in the two-year window (734 calendar days). Evaluated once over the full two years. |
| **Unit** | accounts |
| **Computed in** | `sql/04_dim_customers.sql` (`flag_bulk_same_article`, `flag_bulk_order`, `flag_very_frequent`, `is_excluded`); thresholds in `config.yaml` → `exclusion` |
| **Check value** | 864 accounts (0.06% of customers, 0.5% of two-year revenue): 644 meet (a), 85 meet (b), 165 meet (c); some meet both (a) and (b) |
| **Caveats** | Kept in every total and revenue share, so all tables reconcile. No offers or paid media until reviewed by CRM / retail ops; service messages continue. Because the flag uses the full two years, at the backtest dates it also reflects later behaviour (761 and 847 accounts at the two backtests); at 0.5% of revenue this does not move any segment result. |

### 3.5 Segment shares

| | |
|---|---|
| **Plain words** | How big a segment is and how much of the business it brings in. |
| **Rule** | % customers = segment customers ÷ 1,362,281. % 12-month revenue = segment `monetary_12m` ÷ 247.3M CU. % two-year revenue = the segment's customers' revenue from 2018-09-20 to 2020-09-22 ÷ 521.9M CU (the only value measure that is not zero for Lost). The ten groups, Review List included, add up to 100%. |
| **Unit** | share |
| **Computed in** | `sql/09_segment_profile.sql` → `segment_profile.parquet`; checked in the reconciliation |
| **Caveats** | "High value" in the headline = Champions + Loyal + Slipping Regulars (21% of customers, 67% of 12-month revenue). |

### 3.6 Affinity index and category focus

| | |
|---|---|
| **Plain words** | Which products a segment buys more of than the average customer: what to put in front of them now. |
| **Rule** | Affinity index = (category's share of the segment's revenue) ÷ (category's share of all customers' revenue) × 100, with the same window on both sides: the last 12 months for active segments; the full two years for Lost (against all customers' two years). Review List accounts are left out of the baseline. Categories come from the article file: department (`index_group_name`), product group and garment group. **Category focus** in the campaign = up to two garment groups or departments with index ≥ 120 *and* at least 5% of the segment's revenue; a segment with none "mirrors the overall mix". |
| **Unit** | index (100 = same as everyone) |
| **Computed in** | `sql/10_segment_mix.sql` → `segment_mix.parquet`; `src/rfm/campaign.py` (`category_focus`) |
| **Check value** | At Risk: Knitwear 123, Outdoor 122 |
| **Caveats** | Affinity reflects *when* a group last bought as much as what it likes: the 181-364-day At Risk customers last bought in autumn / winter 2019-20 (that is where the knitwear / outdoor skew comes from), the 121-180-day At Risk group during the spring 2020 closure, Needs Attention in summer. The campaign therefore uses the same rule per audience (`data/marts/audience_mix.parquet`). It describes past purchases; it does not show that featuring a category causes a purchase. |

### 3.7 Segment migration

| | |
|---|---|
| **Plain words** | Where last quarter's customers are now. |
| **Rule** | Each customer's segment at 2020-06-24 (`from_segment`; customers with no order by then = "Not yet a customer") against their segment at 2020-09-22. Share = customers moving from A to B ÷ customers in A. "Changed segment" = 1 − (customers in the same segment at both dates ÷ all customers who had a segment in June). |
| **Unit** | share |
| **Computed in** | `sql/14_segment_flow.sql` → `segment_flow.parquet`; `metrics.json` → `headline.customers_changed_segment_one_quarter`, `headline.champions_stayed_one_quarter`, `headline.champions_to_slipping_one_quarter` |
| **Check value** | 51% of customers changed segment in one quarter; 68% of June's Champions were still Champions in September and 20% had become Slipping Regulars |
| **Caveats** | Most movement is the clock (recency crossing a cut-off) plus normal buying; it is not the effect of any action. This is why audiences are rebuilt on launch day. |

---

## 4. "If we do nothing": backtest metrics

### 4.1 Backtest and outcome window

| | |
|---|---|
| **Plain words** | We pretend it is an earlier date, put every customer into a segment using only what we knew then, and look at what they actually did in the next 90 days. |
| **Rule** | Features and segments are rebuilt at 2019-09-22 and 2020-06-24 with the current rules. Outcome window = the 90 days after the snapshot, (snapshot date, snapshot date + 90]: **2019-09-23 to 2019-12-21** and **2020-06-25 to 2020-09-22**. Per customer: `orders_next_90d`, `revenue_next_90d_cents`, `purchased_next_90d` (at least one order). |
| **Unit** | customers, orders, CU |
| **Computed in** | `sql/05_customer_rfm.sql`, `sql/06_customer_outcomes_90d.sql` → `customer_outcomes_90d.parquet`; per segment `sql/07_segment_outcomes_90d.sql` |
| **Caveats** | There is no campaign data, so this is business as usual: it already contains the normal newsletters and sales of those periods. The 2019 window is the base (same season); the 2020 window is the reopening summer after the store closures. |

### 4.2 Repurchase rate (90 days)

| | |
|---|---|
| **Plain words** | The share of a group who buy again within 90 days. For New Customers this is the second-order rate; for Lost, the reactivation rate. |
| **Rule** | mean(`purchased_next_90d`) over the group's customers at a backtest date. Three versions, each named where it is used: **(1) raw**, for a segment or campaign audience at one backtest date (`segment_outcomes_90d.repurchase_rate`; the campaign's "buys anyway" rate `campaign_inputs.baseline_rate` is the raw rate of the audience rule at 2019-09-22, or at 2020-06-24 where the 2019 audience has fewer than 10,000 customers, i.e. Lost); **(2) composition-adjusted**, used in the revenue-at-risk table: the cell rates of section 4.4 weighted by today's number of customers per cell; **(3) Lost by time away** (section 4.5). |
| **Unit** | share of customers |
| **Computed in** | `sql/07_segment_outcomes_90d.sql`; `src/rfm/analysis.py` (`revenue_at_risk`); `src/rfm/campaign.py` (`audience_inputs`) |
| **Check value** | Champions 83.2% raw (2019), 82.6% adjusted. At Risk 35.9% raw, 34.7% adjusted. Lost 7.1% raw (2020-06-24), 6.3% by time away |
| **Caveats** | Raw and adjusted rates differ by less than 2 points for every segment the campaign contacts; quote the version that belongs to the table you are next to. The same metric is the primary KPI of the campaign (section 6.2). |

### 4.3 Usual 90-day pace

| | |
|---|---|
| **Plain words** | What a group would spend in 90 days if it kept buying exactly as it did over its last 12 months. |
| **Rule** | `run_rate_90d` = `monetary_12m` × 90 ÷ 365, summed over the group. |
| **Unit** | CU |
| **Computed in** | `sql/06_customer_outcomes_90d.sql` (backtests); `src/rfm/analysis.py` (`revenue_at_risk`, current snapshot) |
| **Check value** | At Risk 5.8M CU |
| **Caveats** | Ignores seasonality within the year; the season-matched backtest takes care of it. Lost has no pace. |

### 4.4 Realisation (aggregate and composition-adjusted)

| | |
|---|---|
| **Plain words** | The share of their usual pace that customers who looked the same actually spent in the next 90 days. 1.0 = kept their pace; 0.64 = spent 64% of it. |
| **Rule** | **Aggregate**: Σ `revenue_next_90d` ÷ Σ `run_rate_90d` over the segment's customers at a backtest date (`realisation_raw_*`). **Composition-adjusted** (used for the forecast of every segment with a usual pace): the same ratio computed separately for each cell of R score × F score × M score × 12-month channel inside the segment at the backtest date; cells with fewer than 30 customers take the segment's aggregate ratio; the cell ratios are then averaged with weights = **today's** usual pace in each cell. |
| **Unit** | ratio |
| **Computed in** | `src/rfm/analysis.py` (`revenue_at_risk`, `_cell_ratios`) → `revenue_at_risk.parquet` |
| **Check value** | At Risk: 64.3% aggregate and 63.5% adjusted (2019-09-22), 62.8% adjusted (2020-06-24), 58.3% pessimistic. In the base case, matched cells cover at least 95% of today's pace in every segment with a usual pace except the Review List (78%) |
| **Caveats** | The adjustment matters because today's mix differs from both backtests: 60% of today's At Risk customers last bought in March–May 2020 (last order dated 2020-03-01 to 2020-05-31), and they are more online-only. It corrects for differences *between* cells; it cannot correct for lockdown-era buyers behaving differently from 2019 buyers with the same scores. |

### 4.5 Expected 90-day revenue if we do nothing

| | |
|---|---|
| **Plain words** | The forecast of what a segment spends in the next 90 days without the campaign. |
| **Rule** | Usual pace × composition-adjusted realisation. **Base** = the 2019-09-22 backtest, except where the segment had fewer than 10,000 customers at that date (Lost, Review List), which use 2020-06-24. **Lost** (no pace): today's Lost customers are grouped by time since the last order (365–449, 450–539, 540–629, 630+ days); each group gets the average 90-day revenue per customer of Lost customers with the same time away at 2020-06-24; expected buyers are built the same way. |
| **Unit** | CU |
| **Computed in** | `src/rfm/analysis.py` (`revenue_at_risk`) → `revenue_at_risk.parquet` (`expected_90d_cu_base`, `_seasonal`, `_recent`, `_pessimistic`) |
| **Check value** | At Risk 3.7M CU; Lost 1.8M CU |
| **Caveats** | The 2019 backtest has only 3,144 Lost customers (the data starts a year before it). Today's longest-lapsed customers (up to 733 days) are only partly represented at 2020-06-24, where time away is at most 643 days. |

### 4.6 Gap vs usual pace

| | |
|---|---|
| **Plain words** | How far a segment is expected to fall below its usual pace if we do nothing. It is **not** an amount a campaign can win back. |
| **Rule** | Gap = usual pace − expected 90-day revenue, for segments with a pace. Three scenarios: **base** (2019-09-22, adjusted), **recent** (2020-06-24, adjusted) and **pessimistic** (per cell, the lower of the two ratios). The range shown runs from the lowest to the highest of the three. The gap is always shown next to the **plan's expected incremental revenue** for the same segment (`addressable_90d_cu` = sum of the incremental revenue of the segment's live arms, rollout and test cells). |
| **Unit** | CU |
| **Computed in** | `src/rfm/analysis.py` (`revenue_at_risk`) → `revenue_at_risk.parquet`; `metrics.json` → `segments.*.gap_90d_cu_*`, `headline.at_risk_gap_90d_cu*` |
| **Check value** | At Risk 2.1M CU (range 2.1M to 2.4M), against 44.5K CU of expected incremental revenue from the plan; Slipping Regulars 1.0M CU, against 20K CU |
| **Caveats** | Part of every gap is natural slowdown: customers selected for a strong 12 months fall back (in the 2019 backtest, Champions spending 400+ CU realised 86% of their pace, those at 200–399 CU 105%), so Champions' gap is not churn. Negative gaps (Loyal, Potential Loyalists, New Customers) belong to groups whose 12-month history is short or still building. Lost has no gap. |

### 4.7 Sampling-noise interval

| | |
|---|---|
| **Plain words** | How much the base forecast could move through random noise alone. |
| **Rule** | 95% delta-method interval for a ratio of sums on the 2019 backtest: r = Σy ÷ Σx, with y = 90-day revenue and x = usual pace per customer; se = √(var(y − r·x) ÷ n) ÷ mean(x); interval r ± 1.96·se. The interval is moved by the composition adjustment (adjusted ratio − aggregate ratio) and turned into a gap with pace × (1 − ratio), so it is centred on the base gap. |
| **Unit** | CU |
| **Computed in** | `src/rfm/analysis.py` (`_ratio_ci`, `revenue_at_risk`) |
| **Check value** | At Risk: about ±55K CU around the 2.1M CU base gap |
| **Caveats** | Covers customer-level sampling noise within one backtest year only, not the choice of reference year or the COVID effect. The scenario range (section 4.6) is the uncertainty to quote. |

### 4.8 Expected non-buyers

| | |
|---|---|
| **Plain words** | How many customers in a segment are expected not to buy at all in the next 90 days. |
| **Rule** | customers × (1 − composition-adjusted repurchase rate); Lost: customers − expected buyers by time away. |
| **Unit** | customers |
| **Computed in** | `src/rfm/analysis.py` (`revenue_at_risk`) |
| **Check value** | At Risk 58,643 (65% of the segment) |

### 4.9 Supporting backtest views

| View | Rule | Computed in |
|---|---|---|
| Recency return curve | 90-day return rate by 15-day recency bucket and frequency group (1 order / 2+ orders / no order in 12 months); Review List accounts left out | `sql/08_recency_return_curve.sql` |
| Realisation by M score | Realisation (section 4.4, aggregate) by M score inside each segment, 2019 backtest: the regression-to-the-mean check | `src/rfm/analysis.py` (`regression_to_mean`) |
| Order ladder | Share of customers with at least n orders who place an (n+1)-th within 12 months of their first order. Two cohorts: everyone whose first order in the data is 2018-09-20 to 2019-09-22 (includes existing customers), and likely new customers whose first order is 2019-03-01 to 2019-09-22. Likely new customers: 62% place a second order within a year, 69% of those with two place a third | `src/rfm/analysis.py` (`order_ladder`) |
| Cohort retention and observed LTV | Cohort = month of the first order in the data (2018-10 to 2020-08; the partial months 2018-09 and 2020-09 are dropped). Retention = share of the cohort with an order in calendar month n after the cohort month; observed LTV = cumulative revenue per cohort customer. Review List accounts left out. Left-censored before about 2019-03 | `sql/11_cohort_retention.sql` |

---

## 5. Campaign economics

Everything in this section is a planning estimate for the 90 days after launch. The inputs marked as assumptions are logged in [assumptions.md](assumptions.md); the holdout test replaces them with measurements. Model: `src/rfm/campaign.py` (`economics`) → `campaign_economics.parquet`; full plan in [campaign_plan.md](campaign_plan.md).

**Symbols**

| Symbol | Meaning | Value | Source |
|---|---|---|---|
| N | customers in the audience at the snapshot | per audience | `campaign_inputs.customers` |
| s | subscriber share of the audience | per audience | `campaign_inputs.newsletter_share` |
| a | the arm's share of the reachable population | 0.30–0.90 | arm definitions in `src/rfm/campaign.py` |
| u | assumed ITT lift in the 90-day repurchase rate (assumption) | 0.2–3.0 pp | arm definitions |
| p₀ | share of the audience that buys anyway (raw BAU rate, section 4.2) | per audience | `campaign_inputs.baseline_rate` |
| AOV | audience AOV (section 2.8) | per audience | `campaign_inputs.aov_cu` |
| V | value of one incremental buyer (assumption) | one order = AOV | `config.yaml` → `economics.incremental_value` |
| m | contribution margin (assumption) | 40% | `economics.contribution_margin` |
| d | discount, as a share of one order | 0 or 10% | arm definitions |
| ρ | share of would-be buyers who use a coupon they receive (assumption) | 50% | `economics.baseline_redemption_share` |
| e, g | cost per email, per paid-social target (assumptions) | 0.01 CU, 0.30 CU | `economics.contact_cost_cu` |

### 5.1 Reachable population, contacted and holdout

| | |
|---|---|
| **Plain words** | Who we can reach in an audience, and how many of them each arm gets. |
| **Rule** | Reachable (experiment) population = N × s for email-only audiences; N for the two audiences with a live paid-social arm (New Customers; At Risk 181–364 days with 200+ CU), where non-subscribers are reached through paid social. **Contacted** = reachable × a. **Holdout** = reachable × 10%. Emails = contacted × s in paid-social arms (all contacted in email-only arms); paid-social targets = contacted − emails. |
| **Unit** | customers |
| **Check value** | Rollout arms: 445,473 contacted (414,129 by email, 31,344 by paid social); test cells: 39,191 |
| **Caveats** | "Contacted" means **assigned** to the arm (intention to treat), not delivered, opened or matched by the ad platform. |

### 5.2 Incremental buyers

| | |
|---|---|
| **Plain words** | Customers who buy in the 90 days *because of* the campaign, on top of those who would have bought anyway. |
| **Rule** | contacted × u |
| **Unit** | customers |
| **Check value** | Rollout: 2,722 (base case) |
| **Caveats** | u is a planning assumption until the holdout measures it. |

### 5.3 Incremental revenue and the value of an incremental buyer

| | |
|---|---|
| **Plain words** | The extra revenue those buyers bring. |
| **Rule** | incremental buyers × V. **Base**: V = one order at the audience AOV. **Optimistic**: V = the backtest's average 90-day revenue per buyer (`campaign_inputs.revenue_per_buyer`); for example 88 CU instead of 52 CU for New Customers, 202 CU instead of 59 CU for Champions. |
| **Unit** | CU |
| **Check value** | Rollout: 157.2K CU (base) |
| **Caveats** | One order is deliberately conservative: an incremental buyer is not assumed to keep buying within the 90 days. |

### 5.4 Contribution

| | |
|---|---|
| **Plain words** | The part of the extra revenue that is profit before campaign costs. |
| **Rule** | incremental revenue × m. m = 40% in the base case: H&M group gross margin (52.6% in FY2019, full-year report; 49.4% in the first half of 2020, six-month report) less about 10 pp for fulfilment and returns on mostly online orders; 30% / 50% in the pessimistic / optimistic scenarios. |
| **Unit** | CU |
| **Caveats** | To be confirmed with Finance. |

### 5.5 Discount cost

| | |
|---|---|
| **Plain words** | The value of the coupons redeemed, including coupons used by customers who would have bought anyway. |
| **Rule** | redemptions × d × AOV, with redemptions = contacted × (p₀ × ρ + u): would-be buyers redeem at rate ρ, incremental buyers always redeem. |
| **Unit** | CU |
| **Check value** | Test cells: 40,325 CU (New Customers 28,487; At Risk 181–364 days 200+ CU 11,838) |
| **Caveats** | Most of the coupon cost lands on orders we would have had anyway; this is why a coupon needs a lift of 5+ points where a quarter or more of an audience buys anyway. |

### 5.6 Contact cost

| | |
|---|---|
| **Plain words** | What it costs to send the message. |
| **Rule** | emails × e + paid-social targets × g. Per assigned customer: c = e in email-only arms; c = s × e + (1 − s) × g in paid-social arms. |
| **Unit** | CU |
| **Check value** | Rollout: 13.5K CU (email 4,141 + paid social 9,403) |
| **Caveats** | One email cost per contacted subscriber per arm, however many sends the arm has. |

### 5.7 Net profit

| | |
|---|---|
| **Plain words** | What the arm earns after all campaign costs. |
| **Rule** | contribution − discount cost − contact cost |
| **Unit** | CU |
| **Check value** | Rollout: +53.4K CU; test cells: −21.0K CU (base case) |

### 5.8 Break-even lift

**Plain words.** The smallest lift at which an arm pays for itself.

**Formula.** Net profit per assigned customer = u × V × m − d × AOV × (p₀ × ρ + u) − c. Setting it to zero:

> **break-even lift u\* = (d × AOV × p₀ × ρ + c) ÷ (V × m − d × AOV)**

For content arms (d = 0) this is simply c ÷ (V × m). If V × m ≤ d × AOV, the arm can never break even.

**Worked examples.**

- Champions early access (email only): 0.01 ÷ (58.66 × 0.40) = 0.04 pp.
- New Customers welcome journey + 10% off the second order: c = 0.33 × 0.01 + 0.67 × 0.30 = 0.204 CU; u\* = (0.10 × 51.60 × 0.285 × 0.5 + 0.204) ÷ (51.60 × 0.40 − 5.16) ≈ 0.94 ÷ 15.48 = 6.07 pp.

**Computed in.** `src/rfm/campaign.py` (`economics`, column `breakeven_uplift_pp`).

**Caveats.** The break-even is stated against no contact (the holdout). The coupon decision compares the coupon cell with its content cell, which pays the same contact cost, so the true hurdle for "coupon over content" is slightly lower than the printed figure; using the printed figure is the conservative choice.

### 5.9 Scenarios, budget ask and the cost of measuring

| Metric | Rule | Computed in |
|---|---|---|
| Scenarios | Every live arm recomputed under three sets: **Pessimistic** = margin 30%, one-order value, paid social 0.60 CU, coupon use 60%, all lifts × 0.5; **Base**; **Optimistic** = margin 50%, average-buyer value, paid social 0.30 CU, coupon use 40%, all lifts × 1.5 | `config.yaml` → `economics.scenarios`; `campaign.scenario_table` → `campaign_scenarios.parquet` |
| Budget ask | Rollout email + rollout paid social + test-cell discounts + test-cell contacts = 61.9K CU | `campaign.budget_lines` → `campaign_budget.parquet` |
| Profit given up by the holdout (memo) | Sum over rollout arms of holdout × (u × V × m − c) = 6.5K CU: the price of being able to measure | same |

---

## 6. Measurement metrics

The full design is in [measurement_plan.md](measurement_plan.md); this section fixes the definitions.

### 6.1 Assignment, holdout and segment of record

| | |
|---|---|
| **Plain words** | Who gets the campaign and who is kept back for comparison. |
| **Rule** | On launch day (2020-09-28) every customer is re-scored with the production SQL; the launch-day segment and audience are the **segment of record**. Within each audience's reachable population, a salted hash of customer id puts 10% in the holdout and splits the rest across the arms in the plan's shares (stratified by audience). The hash depends only on customer id and the salt, so re-scoring never moves a customer between holdout and treatment. **Balance check** at launch, per audience: 12-month spend and subscriber share, holdout vs treated. The holdout gets **no campaign communication** (no campaign emails, app messages or early-access links; excluded from paid-social audiences and lookalike seeds) but keeps the business-as-usual newsletters, Black Friday and Christmas sends. |
| **Caveats** | Customers outside the reachable population (non-subscribers in email-only audiences) are not part of the test. Customers who join a segment after launch day are outside this read. |

### 6.2 Outcome window and KPIs

| | |
|---|---|
| **Outcome window** | Orders dated **2020-09-28 to 2020-12-26** (the 90 days from launch), the same window for every arm and the holdout; final read on **2020-12-27**. Arms that start later (Loyal in week 2, Lost in week 4) keep the same window; that is part of their intention-to-treat effect. |
| **Primary KPI** | **90-day repurchase rate** = share of assigned customers with at least one order in the window (for New Customers: the second-order rate). |
| **Secondary KPIs** | **Revenue per assigned customer** = 90-day revenue over all assigned customers, zeros included, winsorised at the 99th percentile of the audience and adjusted for 12-month spend by regression. **Measured net profit** = measured incremental revenue × margin − coupon value actually redeemed − actual contact cost. |
| **Guardrails (day 30, 2020-10-28)** | Delivery, unsubscribes, complaints, paid-social match rate. No lift decisions. |

### 6.3 ITT lift

| | |
|---|---|
| **Plain words** | The effect of being assigned to the campaign, whether or not the customer opened or saw anything. |
| **Rule** | lift (pp) = repurchase rate of everyone assigned to the arm − repurchase rate of the same audience's holdout. Coupon cells are compared with their content cell (coupon effect) and with the holdout. Revenue lift is defined the same way per assigned customer. |
| **Caveats** | Opens and clicks are diagnostics only. All planning lifts (section 5) are ITT lifts. |

### 6.4 Minimum detectable effect (MDE)

| | |
|---|---|
| **Plain words** | The smallest true lift the test will spot four times out of five. A smaller true lift will probably read as "no difference". |
| **Rule** | Two-sided test, α = 0.05, power 0.80, normal approximation: MDE (rate) = (z₀.₉₇₅ + z₀.₈₀) × √(p₀ (1 − p₀) (1/n_T + 1/n_C)), with z₀.₉₇₅ + z₀.₈₀ = 1.960 + 0.842 = 2.802. MDE (revenue per customer) = 2.802 × sd × √(1/n_T + 1/n_C), sd = standard deviation of 90-day revenue per customer in the 2019 backtest audience. n_T = arm size, n_C = holdout. |
| **Unit** | pp; CU per customer |
| **Computed in** | `src/rfm/power.py`; per arm in `campaign.economics` (`mde_rate_pp`, `mde_revenue_cu`); by holdout share in `holdout_power.parquet` |
| **Caveats** | The revenue MDE uses the raw (not winsorised, not adjusted) sd, so it is conservative. The coupon cells' MDE is computed against the holdout; against the larger content cell it is smaller. |

### 6.5 Readable alone and sized for its decision

| | |
|---|---|
| **Readable alone** | MDE (rate) ≤ the arm's assumed lift. No content arm meets this at a 10% holdout: content arms are directional and are judged through the pooled read. |
| **Sized for its decision** (test cells) | MDE (rate) ≤ 2/3 × break-even lift, so a "no" is informative. New Customers coupon cell: 1.66 pp against a 6.07 pp break-even; At Risk coupon cell: 2.92 pp against 5.08 pp. |
| **Computed in** | `campaign.economics` (`readable_alone`, `powered_for_decision`) |

### 6.6 Pooled campaign-wide read (stratified estimator)

| | |
|---|---|
| **Plain words** | One answer to "did the autumn campaign work overall?", using every audience's holdout together. |
| **Rule** | lift = Σₛ wₛ × (p̂_T,s − p̂_C,s), where s = audience, wₛ = audience s's reachable population ÷ total reachable population (538,515), T = everyone assigned to any live arm of s and C = its holdout. Var = Σₛ wₛ² × pₛ (1 − pₛ) × (1/n_T,s + 1/n_C,s); MDE = 2.802 × √Var. Expected lift if every arm hits its assumption = Σ (contacted × u) ÷ Σ contacted. |
| **Unit** | pp |
| **Computed in** | `src/rfm/campaign.py` (`pooled_read`) → `metrics.json` → `campaign.pooled_read` |
| **Check value** | 53,852 holdout customers; weighted baseline 37.1%; MDE 0.51 pp against 0.84 pp expected |
| **Caveats** | Because every audience has the same 10% holdout share, treated and holdout have the same audience mix, so even a simple pooled comparison is unbiased; the stratified estimator is used for precision. |

### 6.7 Decision rule, multiple comparisons and guardrails

- **Scale an offer** in the next wave only if the 95% lower bound of its lift over the content cell clears its break-even (section 5.8).
- **Multiple comparisons:** comparisons within At Risk (three audiences, plus coupon vs content) are Holm-adjusted.
- **Day 30** is for guardrails only; no lift decisions before day 90.
- **Always-on journeys:** a content arm (e.g. the Slipping Regulars reminder) becomes always-on only if the pooled read passes and the arm's own estimate is above zero; the New Customers welcome journey, which pays for paid social, is kept only if the lower bound of its lift clears its break-even of 0.99 pp (measurement plan, section 7).

---

## 7. Where the quoted numbers come from

The dashboard reads these numbers from [`reports/metrics.json`](../reports/metrics.json) and the marts, and the tables in the README and the docs are generated from the same files. Numbers in prose (README, readout, campaign plan) are typed, and this table is the list to check them against.

| Number as quoted | Exact value | Metric (section) | Source |
|---|---|---|---|
| 31.8M item rows; 1.36M customers | 31,788,324; 1,362,281 | 1.2; universe | `data.transaction_rows`, `data.customers_with_orders` |
| 993K active customers (73%) | 993,492; 72.9% | 2.1 | `data.active_12m_customers`, `data.pct_active_12m` |
| 247.3M CU of 12-month revenue | 247,265,063 | 1.6, 2.4 | `data.revenue_12m_cu` |
| Champions: 14% of customers, 54% of 12-month revenue | 13.97%; 54.15% | 3.1, 3.5 | `headline.champions_pct_customers`, `headline.champions_pct_revenue_12m` |
| Champions + Loyal + Slipping Regulars: 21% of customers, 67% of revenue | 20.97%; 66.53% | 3.5 | `headline.high_value_pct_customers`, `headline.high_value_pct_revenue_12m` |
| 41K VIPs (3% of customers), 28% of revenue | 41,118; 27.87% | 2.11 | `headline.vip_customers`, `headline.vip_pct_revenue_12m` |
| 83% of Champions buy again within 90 days with business-as-usual contact only | 82.55% | 4.2 (adjusted) | `segments.Champions.repurchase_rate_90d_base` |
| 89.8K At Risk customers (6.6%) | 89,848 | 3.1 | `headline.at_risk_customers`, `headline.at_risk_pct_customers` |
| At Risk: 3.7M CU expected in 90 days vs 5.8M CU at usual pace | 3,668,360; 5,774,253 | 4.5, 4.3 | `headline.at_risk_expected_90d_cu`, `headline.at_risk_run_rate_90d_cu` |
| At Risk gap 2.1M CU (scenarios 2.1M to 2.4M) | 2,105,894; 2,105,894 to 2,408,597 | 4.6 | `headline.at_risk_gap_90d_cu`, `_low`, `_high` |
| About 59K At Risk customers (65%) are expected not to buy | 58,643 | 4.8 | `headline.at_risk_non_buyers_90d` |
| The plan expects about 45K CU of incremental revenue from At Risk | 44,510 | 4.6 | `headline.at_risk_addressable_90d_cu` |
| ... of which about 26K from content emails and 19K from the 10% offer test cell | 25,700; 18,810 | 4.6, 5.7 | `headline.at_risk_addressable_content_90d_cu`; the difference |
| 61.7K Slipping Regulars, 10.4% of revenue, gap 1.0M CU | 61,655; 10.36%; 965,169 | 3.1, 4.6 | `headline.slipping_customers`, `headline.slipping_pct_revenue_12m`, `headline.slipping_gap_90d_cu` |
| 11% of customers show a churn signal; gap 3.1M CU | 151,503 (11.13%); 3,071,063 | 3.2, 4.6 | `headline.churn_signal_customers`, `headline.churn_signal_pct_customers`, `headline.churn_signal_gap_90d_cu` |
| The win-back plan expects about 65K CU of incremental revenue from them (At Risk 45K + Slipping Regulars 20K) | 64,830; 44,510; 20,320 | 4.6 | `headline.churn_signal_addressable_90d_cu`, `headline.at_risk_addressable_90d_cu`, `headline.slipping_addressable_90d_cu` |
| 60% of At Risk last bought in March–May 2020 | 59.79% | 4.4 | `headline.at_risk_lockdown_share` |
| Champions at 400+ CU realised 86% of their pace, at 200–399 CU 105% | 86.48%; 105.43% | 4.6 | `headline.champions_realisation_m5`, `headline.champions_realisation_m4` |
| 483K active customers (49%) are online only | 482,607; 48.61% | 2.10 | `headline.online_only_active_customers`, `headline.pct_online_only_active` |
| 147K of them are on email; 56K are Champions, Loyal or Slipping Regulars | 147,213; 55,909 | 2.9, 2.10 | `headline.online_only_active_subscribers`, `headline.online_only_high_value_customers` |
| An online order is about twice a store order (70 vs 33 CU, same omnichannel customers) | 69.59; 33.38 | 2.8 | `headline.aov_online_order_omni`, `headline.aov_store_order_omni` |
| At 5–9 orders: online only 474 vs omnichannel 357 CU (gross; 355 vs 287 after the illustrative returns haircut) and they come back 64% vs 69% | 473.6; 357.2; 355.2; 286.7; 63.56%; 68.71% | 2.10, 4.2 | `headline.rev_per_customer_5_9_*`, `headline.rev_net_5_9_*`, `headline.repurchase_5_9_*` |
| 51% of customers changed segment in one quarter; 68% of Champions stayed; 20% slipped | 50.59%; 67.73%; 20.40% | 3.7 | `headline.customers_changed_segment_one_quarter`, `headline.champions_stayed_one_quarter`, `headline.champions_to_slipping_one_quarter` |
| Rollout: 445K contacted, cost 13.5K CU, incremental revenue 167K CU, net +53K CU | 445,473; 13,544; 167,432; 53,428 | 5.1–5.7 | `campaign.rollout_*` |
| Net range: pessimistic +2.2K CU, optimistic +239K CU | 2,167; 239,033 | 5.9 | `campaign.scenarios` |
| Test cells expected to cost 21K CU | −21,031 | 5.7 | `campaign.test_cells_net_profit_cu` |
| Budget ask 61.9K CU | 61,915 | 5.9 | `campaign.budget_total_cu` |
| The 10% holdout gives up 6.5K CU of profit | 6,478 | 5.9 | `campaign.holdout_opportunity_cost_cu` |
| Break-even lifts: coupon cells 6.07 / 5.08 pp; rejected 20% offer 14.2 pp, Loyal voucher 11.5 pp | 6.07; 5.08; 14.24; 11.53 | 5.8 | `campaign.arms.*.breakeven_uplift_pp` |
| Campaign-wide lift detectable from 0.51 pp (0.84 pp expected); 53.9K holdout customers | 0.511; 0.842; 53,852 | 6.6 | `campaign.pooled_read` |
| 16 checks pass, 7 flagged, 0 failed; 19 of 19 reconciliation checks pass | 16; 7; 0; 19 / 19 | [03](03_data_quality_checks.md) | `data.dq_pass`, `data.dq_flag`, `data.dq_fail`, `data.reconciliation_checks_*` |
