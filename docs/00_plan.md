# 00 — Project plan (one page)

**Project:** RFM customer segmentation & autumn CRM campaign plan — H&M transactions 2018-09-20 → 2020-09-22
**Author role:** Marketing Analyst, CRM / Marketing Analytics team (reporting to the CRM Manager)
**Status:** plan approved; work started after writing this page.

## 1. Data

| Source | Rows | Use |
|---|---|---|
| `transactions_train.csv` | 31,788,324 item rows, 1,362,281 customers, 2018-09-20 → 2020-09-22 | orders, RFM, cohorts, channel |
| `customers.csv` | 1,371,980 customers | age, club status, newsletter subscription (= email reach) |
| `articles.csv` | 105,542 articles | category hierarchy for segment profiles |

Read from `~/projects/data-projects/datasets/p3-comp-hm-2020/` (configurable in `config.yaml` / `.env`), staged to Parquet with DuckDB (full staging takes ~5 s, so all development runs on the **full** data, not a sample). Raw data is never committed.

Findings from the first profiling pass that shape the plan:
- **Channel encoding verified against a known event:** channel 1 has *zero* rows from 2020-03-23 to 2020-04-26 (COVID store closures) while channel 2 spikes → 1 = store, 2 = online.
- **Prices are scaled:** `price × 590` lands exactly on retail price points (9.99, 19.99, 14.99 …) for 100% of rows. We report money as **CU (currency units) = price × 590**; the currency itself is not disclosed. Shares and ratios are unaffected by the unit.
- **No quantity column:** 2.97M rows (9.4%) are exact repeats of another row = extra units of the same item, not errors.
- **Extreme buyers exist:** e.g. one customer bought 569 identical units in one day; another bought on 427 of 734 days → staff / reseller rule needed.

## 2. Analysis outline

1. **Scope & metrics first** — `01_request_and_scope.md`, `02_metric_definitions.md` (Recency / Frequency / Monetary, active, churn, order, CU).
2. **Data quality** (`sql/01_data_quality_checks.sql`, `notebooks/01_cleaning`) — row-count reconciliation, keys, nulls, price outliers, duplicates, time range, extreme customers → `03_data_quality_checks.md`.
3. **RFM scoring** (`sql/05_customer_rfm.sql`, `notebooks/02_rfm`) — snapshot 2020-09-22; F and M over trailing 12 months; **business thresholds vs quantile cut compared**; thresholds justified with the observed "chance of buying again in the next 90 days by recency" curve.
4. **Segmentation** (`notebooks/03_segments_and_actions`) — 8 rule-based lifecycle segments + an *Excluded* group (staff/reseller). K-Means on log-RFM as a comparison only.
5. **Segment profiles** — customers, revenue share, AOV, purchase cycle, category affinity, store vs online, age, newsletter reach.
6. **"If we do nothing" counterfactual** — apply the same segment rules at 2019-09-22 (same season one year earlier) and 2020-06-24 (most recent quarter), observe actual next-90-day behaviour, project the current At Risk / Needs Attention revenue for the next 90 days → revenue at risk with a range.
7. **Campaign plan & measurement** — one row per segment (goal, action, timing, channel, category, expected lift, KPI, cost, risk), break-even lift, randomised holdout with minimum detectable effect per segment.
8. **Cohorts** (`notebooks/04_cohort`) — retention and cumulative revenue per customer (observed LTV) by first-purchase month and first channel.

## 3. Deliverables

`docs/` (request & scope, metric definitions, data quality, assumptions, readout, segmentation spec, campaign plan), `sql/` (standalone DuckDB files + a single-query RFM), `notebooks/` 01–04 executed and exported to HTML, `dashboard/` multi-page Streamlit app, `reports/report.html` (standalone) + one-page action plan, `README.md`, one-command pipeline (`make all`).

## 4. What we borrow from the reference projects and what we add

- **Borrow:** the classic R/F/M 1–5 scoring and named segment map (joaolcorreia/RFM-analysis, klaudia-nazarko/rfm-analysis-python: segment size, value, demographics, behaviour); the idea of *comparing cut methods* (gianfelton: quartiles vs Jenks vs HDBSCAN → here quantile vs business thresholds vs K-Means); an interactive RFM app (mertbozkir Streamlit RFM).
- **Add (what those projects, and the H&M Kaggle notebooks that all do recommender systems, don't do):** 31.8M-row DuckDB pipeline; store vs online channel (validated with the COVID closure); category affinity per segment; staff/reseller exclusion; revenue at risk from a season-matched backtest; campaign economics with break-even lift; holdout design with power; stakeholder docs a CRM team can execute from.

## 5. Decisions

| Decision | Choice | Why |
|---|---|---|
| Dataset | H&M (primary), not Olist | real, recent, large, has customer attributes, article hierarchy and store/online channel — all needed for the questions asked |
| Snapshot / Recency base date | 2020-09-22 (last day in data) | required by the brief; recency 0 = bought on the last day |
| F & M window | trailing 365 days | one full fashion season cycle; "12-month active" is the standard CRM convention; identical features can be rebuilt at backtest dates |
| Scoring | fixed business thresholds (quantiles shown as comparison) | 34% of active customers have exactly 1 order, so quintile cuts on F tie and split identical customers; fixed thresholds keep segment definitions stable month to month |
| Segments | 8 rule-based lifecycle segments + Excluded | each segment maps to one CRM journey; rules are SQL `CASE WHEN`s the CRM team can reuse |
| K-Means | comparison only, not used for targeting | brief says not to cluster for its own sake; clusters move every refit and are hard to explain |
| Money unit | CU = price × 590 | reconstructed retail price points; documented in assumptions; all shares unit-free |
| Counterfactual | season-matched backtest (2019-09-22) as base, recent backtest (2020-06-24) as range | transparent "what happened last year to customers who looked like this" — no black-box churn model |
| Cohort page | added as an appendix page after the 7 required pages | brief lists cohort as a supplement; keeps the required story order intact |

## 6. Risks / known limitations (tracked in `assumptions.md`)
Store purchases are only visible when the member identifies (online over-represented, "online-only" may include anonymous store shoppers) · 2020 is a COVID year · first purchase in data ≠ first purchase ever (left-censoring) · no campaign or margin data, so lift and cost are planning assumptions that the holdout test is designed to replace.
