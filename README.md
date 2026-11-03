# RFM Customer Segmentation & Autumn CRM Campaign Plan

RFM segmentation of 1.36M H&M customers from 31.8M real transactions (2018-09 to 2020-09), turned into a budget-limited autumn campaign: who gets what, when, through which channel, what it costs, and how a holdout will measure it. DuckDB SQL + Python, Streamlit demo, standalone HTML report.

![Champions are 14% of customers but 54% of 12-month revenue](reports/figures/segment_share.png)

**What each segment gets this autumn** (expected 90-day net profit at base-case planning assumptions):

<!-- BEGIN:campaign_short -->
| Audience                        | Action                                          | When                                          | Channel             | Category focus                                        | Discount   | Expected net (CU)   |
|:--------------------------------|:------------------------------------------------|:----------------------------------------------|:--------------------|:------------------------------------------------------|:-----------|:--------------------|
| Champions                       | Autumn early access                             | 2020-09-29, two days before the public launch | Email + member app  | mirrors the overall mix (no category at index >= 120) | none       | 8,669               |
| Loyal                           | Basket-building picks                           | Week 2 (from 2020-10-05)                      | Email + member app  | Accessories (179), Jersey Basic (148)                 | none       | 551                 |
| Slipping Regulars               | Purchase-cycle reminder: autumn picks           | Week 1 (2020-09-28), reminder day 10          | Email + member app  | mirrors the overall mix (no category at index >= 120) | none       | 7,882               |
| Potential Loyalists             | Complete-the-look recommendations               | Week 1 (from 2020-09-28)                      | Email + member app  | Sport dept. (126)                                     | none       | 9,360               |
| New Customers                   | Welcome journey                                 | Starts day 7 after the first order            | Email + paid social | Swimwear (141), Sport dept. (124)                     | none       | 3,371               |
| New Customers                   | Welcome journey + 10% off 2nd order (test cell) | Same as the journey (parallel cell)           | Email + paid social | Swimwear (141), Sport dept. (124)                     | 10%        | -15,208             |
| Needs Attention                 | Summer-to-autumn new-arrivals edit              | Week 1 (from 2020-09-28)                      | Email + member app  | Swimwear (184)                                        | none       | 9,907               |
| At Risk, 121-180 days           | Win-back content (email only)                   | Week 1 (from 2020-09-28)                      | Email only          | Knitwear (123), Outdoor (122)                         | none       | 3,596               |
| At Risk, 181-364 days, 200+ CU  | Win-back content + paid social                  | Week 1 (from 2020-09-28)                      | Email + paid social | Knitwear (123), Outdoor (122)                         | none       | 3,002               |
| At Risk, 181-364 days, 200+ CU  | Win-back + 10% off (test cell)                  | Week 1, in parallel with the content cell     | Email + paid social | Knitwear (123), Outdoor (122)                         | 10%        | -5,823              |
| At Risk, 181-364 days, < 200 CU | Win-back content (email only)                   | Week 1 (from 2020-09-28)                      | Email only          | Knitwear (123), Outdoor (122)                         | none       | 451                 |
| Lost                            | One reactivation email                          | Week 4 (from 2020-10-19)                      | Email only          | Baby/Children dept. (330), Menswear dept. (125)       | none       | 3,276               |
| Hibernating                     | no autumn spend                                 | -                                             | -                   | -                                                     | -          | -                   |
| Review List                     | no autumn spend                                 | -                                             | -                   | -                                                     | -          | -                   |

<sub>Generated from the pipeline outputs by `python run.py --steps docs`; do not edit by hand.</sub>
<!-- END:campaign_short -->

---

## The business question

The CRM Manager asked: *"The autumn campaign budget is limited. Who are the high-value customers we need to keep, who is about to churn and needs winning back, and who only buys online and never comes into a store? Give me segments, a recommendation per segment, and how we will measure whether this campaign worked."* Clarified questions, decision maker and decision points: [docs/01_request_and_scope.md](docs/01_request_and_scope.md).

## Three findings

1. **High value is concentrated and does not need discounts.** Champions are **14% of customers and 54% of 12-month revenue**; the 41K VIPs (1,000+ CU a year, 3% of customers) bring in **28%**. 83% of Champions buy again within 90 days without any campaign, so a discount would mostly pay for orders we get anyway.
2. **Two groups are drifting away.** **89.8K At Risk customers** (6.6%; used to buy often or a lot, quiet for 4-12 months) are expected to spend **3.7M CU in the next 90 days instead of 5.8M at their usual pace**, and 58.6K of them will not buy at all. **61.7K Slipping Regulars** (frequent buyers already 61-120 days quiet, 10.4% of revenue) show a further 1.0M CU gap. Much of these gaps is natural slowdown: the plan expects to win back about **45K CU** from At Risk, and measures it instead of promising the gap.
3. **Online-only is not a problem to fix.** **483K active customers (49%)** had no identified store purchase in 12 months. Their baskets are bigger because online orders are about twice the size of store orders even for the same customers (70 vs 33 CU), and they come back slightly *less* often (64% vs 69% at 5-9 orders). Nothing supports paying to push them into stores; channel decides the message.

## Recommendation

- **Content-led autumn wave** for every segment worth contacting: early access for Champions, purchase-cycle reminders for Slipping Regulars, a welcome journey for New Customers, knitwear-and-outerwear win-back for At Risk (their winter categories), no spend on Hibernating or the Review List. Rollout cost **12.8K CU**.
- **Discounts only where they can pay, and only as tests:** 10% off a New Customer's second order, and 10% off for long-lapsed high-value At Risk customers, each in a cell sized to give a clear answer. A 20% offer and a Loyal voucher were considered and rejected (break-even lifts of 14 and 12 points).
- **Budget ask 61.2K CU.** Expected rollout net **+50K CU** (pessimistic +1K, optimistic +227K); the test cells are expected to cost 21K CU, the price of learning whether offers pay.
- **Measure everything against the same 10% holdout in every audience.** The campaign-wide lift is detectable from 0.57 percentage points; offers scale in the next wave only if their measured lift clears break-even. Final read 2020-12-27.

Full plan and rules: [campaign_plan.md](docs/campaign_plan.md) · measurement: [measurement_plan.md](docs/measurement_plan.md) · audience spec: [segmentation_spec.md](docs/segmentation_spec.md) · one-page memo: [readout.md](docs/readout.md) · printable action plan: [reports/action_plan.html](reports/action_plan.html).

## Key charts

| | |
|---|---|
| ![If we do nothing](reports/figures/run_rate_vs_expected.png) | ![Break-even vs assumed lift](reports/figures/breakeven_vs_assumed.png) |
| ![Value tier grid](reports/figures/value_grid.png) | ![Segments predict behaviour](reports/figures/segment_outcomes.png) |
| ![Online vs store, forward-looking](reports/figures/channel_forward.png) | ![Segment migration in one quarter](reports/figures/segment_flow.png) |

## The demo app (8 pages, in presentation order)

`streamlit run dashboard/app.py`. Each page starts with the question it answers and ends with a "How to read this" box. Pages 3, 6 and 7 recompute on the fly: re-segment 1.36M customers with your own thresholds, define your own at-risk audience, edit the campaign assumptions and budget.

| | |
|---|---|
| ![Overview](docs/images/dashboard_1_overview.png) **1. Overview** | ![Data checks](docs/images/dashboard_2_data_checks.png) **2. Data & Sanity Checks** |
| ![RFM scoring](docs/images/dashboard_3_rfm_scoring.png) **3. RFM Scoring** | ![Segments](docs/images/dashboard_4_segments.png) **4. Segments Overview** |
| ![Drill-down](docs/images/dashboard_5_drill_down.png) **5. Segment Drill-down** | ![At risk](docs/images/dashboard_6_at_risk.png) **6. At-risk Revenue** |
| ![Campaign](docs/images/dashboard_7_campaign.png) **7. Campaign Plan & Measurement** | ![Cohorts](docs/images/dashboard_8_cohorts.png) **8. Appendix: Cohorts & LTV** |

The same charts, with the full narrative, are in [reports/report.html](reports/report.html) (one file, opens offline). Notebook exports: [01 cleaning](reports/01_cleaning.html) · [02 RFM](reports/02_rfm.html) · [03 segments and actions](reports/03_segments_and_actions.html) · [04 cohorts](reports/04_cohort.html).

## Method and data

- **Data:** H&M Personalized Fashion Recommendations dataset (public, 2022): 31,788,324 item rows, 1,362,281 customers with an order, 105,542 articles, 2018-09-20 to 2020-09-22. All of it is processed with DuckDB; nothing is sampled.
- **Cleaning** ([03_data_quality_checks.md](docs/03_data_quality_checks.md)): 23 checks (16 pass, 7 flagged with a documented handling, 0 fail) and 19 reconciliation checks from raw rows to segments. Channel 1 = store, confirmed by the COVID store closures (no store sales 2020-03-20 to 2020-05-05). Money = **CU = price × 590** (every price lands on a retail price point; gross demand, no returns). Identical rows are extra units. 864 bulk or near-daily buyers go on a Review List (kept in totals, no offers).
- **RFM** ([02_metric_definitions.md](docs/02_metric_definitions.md)): snapshot 2020-09-22; Recency = days since last order; Frequency and Monetary over the trailing 12 months (order = customer × day × channel). Fixed thresholds (R 30/60/120/180 days, F 1/2/3-4/5-9/10+, M 50/100/200/400 CU): R and M are the quintiles rounded to sayable numbers, F is set by hand because a third of active customers have one order. K-Means was run as a cross-check and not used (no natural clusters; clusters move when refit).
- **Segments:** 9 lifecycle segments + Review List, plus a value tier (VIP / High / Mid / Low). Validated by applying the same rules at two past dates and checking what customers did next.
- **"If we do nothing":** same rules at 2019-09-22 (same season one year earlier), 90 days of observed behaviour, re-weighted to today's mix (recency × frequency × spend × channel); scenarios from the 2020-06-24 quarter and a pessimistic case.
- **Campaign economics:** an incremental buyer is worth one order at the audience's AOV, 40% contribution margin, coupons also used by customers who would buy anyway; break-even lift per arm; three scenarios.
- **Measurement:** randomised 10% holdout in every audience, intention-to-treat, 90-day repurchase rate as the primary KPI, test cells sized so a "no" is informative.

<!-- BEGIN:segment_summary -->
| Segment             | Rule (scores)                                                                                 | In plain words                                                                             | Customers     | % customers   | % 12m revenue   | AOV (CU)   | Orders / 12m   | Email reach   |
|:--------------------|:----------------------------------------------------------------------------------------------|:-------------------------------------------------------------------------------------------|:--------------|:--------------|:----------------|:-----------|:---------------|:--------------|
| Champions           | R >= 4 and F >= 4 and M >= 4                                                                  | Bought in the last 60 days, 5+ orders and 200+ CU in the last 12 months                    | 190,320       | 14.0%         | 54.1%           | 58.7       | 12.0           | 47%           |
| Loyal               | R >= 4 and F >= 4 (remaining)                                                                 | Bought in the last 60 days, 5+ orders in 12 months, under 200 CU (frequent, small baskets) | 33,612        | 2.5%          | 2.0%            | 23.8       | 6.2            | 48%           |
| Slipping Regulars   | R = 3 and F >= 4                                                                              | 5+ orders in 12 months, but no order in the last 61-120 days                               | 61,655        | 4.5%          | 10.4%           | 55.1       | 7.5            | 44%           |
| Potential Loyalists | R >= 4 (remaining)                                                                            | Bought in the last 60 days, 1-4 orders in 12 months (not new)                              | 124,517       | 9.1%          | 7.8%            | 56.8       | 2.7            | 38%           |
| New Customers       | tenure < 90 days                                                                              | First order within the last 90 days                                                        | 71,117        | 5.2%          | 2.0%            | 51.6       | 1.3            | 33%           |
| Needs Attention     | R = 3 (remaining)                                                                             | Last order 61-120 days ago, 1-4 orders in 12 months                                        | 137,675       | 10.1%         | 7.1%            | 56.6       | 2.3            | 37%           |
| At Risk             | R <= 2 and (F >= 3 or M >= 4)                                                                 | Last order 121-364 days ago but used to buy often (3+ orders) or a lot (200+ CU)           | 89,848        | 6.6%          | 9.5%            | 69.5       | 3.7            | 35%           |
| Hibernating         | R <= 2 (remaining)                                                                            | Last order 121-364 days ago, 1-2 orders and under 200 CU                                   | 284,069       | 20.9%         | 6.6%            | 46.6       | 1.2            | 29%           |
| Lost                | recency >= 365 days                                                                           | No order in the last 365 days                                                              | 368,604       | 27.1%         | 0.0%            | 55.4       | 0.0            | 29%           |
| Review List         | >= 20 units of one article in an order, >= 100 units in an order, or purchases on >= 150 days | Bulk or near-daily buying pattern: no offers or paid media until reviewed                  | 864           | 0.1%          | 0.5%            | 64.9       | 22.8           | 37%           |
| **Total**           |                                                                                               | all customers with an order 2018-09-20 to 2020-09-22                                       | **1,362,281** | **100.0%**    | **100.0%**      |            |                |               |

<sub>Generated from the pipeline outputs by `python run.py --steps docs`; do not edit by hand.</sub>
<!-- END:segment_summary -->

## Limitations

- Revenue is gross demand: the data has no returns (online returns are typically higher than store returns).
- Store purchases are only recorded when the member identifies, so "online only" means "no identified store purchase".
- Autumn 2020 is a COVID autumn; the backtests are autumn 2019 and the 2020 reopening summer. A second wave would change behaviour.
- Lifts, margin, coupon use and paid-social costs are planning assumptions until the holdout replaces them with measurements ([assumptions.md](docs/assumptions.md)).
- No order id (same-day online orders count as one order) and left-censoring (the first order in the data is not always the first ever).

## How to run

Requirements: Python 3.11+ (tested on 3.12), ~2 GB free disk for the Parquet files, Google Chrome for PNG export and screenshots.

```bash
make setup
```

```bash
make all
```

```bash
make dashboard
```

The raw H&M CSVs are read from `data.raw_dir` in [config.yaml](config.yaml) (default `~/projects/data-projects/datasets/p3-comp-hm-2020`). To point elsewhere without editing the config, copy `.env.example` to `.env` and set `HM_RAW_DIR=/path/to/folder`. No raw or derived data is committed (`data/` is gitignored); `make all` rebuilds everything: staging → data quality → marts → reconciliation → analysis → figures → report → docs → notebooks.

Other targets: `make test` (SQL/Python parity, every dashboard page, interactive controls), `make data`, `make notebooks`, `make screenshots`. Any single SQL file runs on its own: `python scripts/run_sql.py sql/05_customer_rfm.sql`. Last full run on the full 31.8M rows:

<!-- BEGIN:run_timings -->
| Step      | Seconds   |
|:----------|:----------|
| dq        | 37.9      |
| marts     | 18.9      |
| reconcile | 0.6       |
| analysis  | 23.7      |

<sub>Generated from the pipeline outputs by `python run.py --steps docs`; do not edit by hand.</sub>
<!-- END:run_timings -->

## Repository map

```
config.yaml            every parameter (snapshot, thresholds, exclusion rule, economics)
run.py / Makefile      one-command pipeline
sql/                   00-14 standalone DuckDB files (staging, checks, marts, RFM, backtests, flow) + rfm_single_query.sql
src/rfm/               segments (Python copy of the rules), analysis, campaign economics, power, charts, report, docgen
notebooks/             01_cleaning, 02_rfm, 03_segments_and_actions, 04_cohort (executed)
dashboard/             Streamlit app: app.py + views/
reports/               report.html, action_plan.html, notebook exports, figures/, metrics.json
docs/                  plan, scope, metric definitions, data quality, assumptions, segmentation spec,
                       campaign plan, measurement plan, readout
tests/                 parity of SQL and Python rules; every dashboard page renders
```
