# 00 — Project plan

**Project:** RFM customer segmentation and autumn CRM campaign plan, H&M transactions 2018-09-20 to 2020-09-22
**Owner:** Marketing Analyst, CRM / Marketing Analytics (requester: CRM Manager)
**Version:** 1.0 · data snapshot 2020-09-22 · campaign launch assumed for the week of 2020-09-28

## 1. Data

| Source | Rows | Used for |
|---|---|---|
| `transactions_train.csv` | 31,788,324 item rows; 1,362,281 customers; 2018-09-20 to 2020-09-22 | orders, RFM, backtests, cohorts, channel |
| `customers.csv` | 1,371,980 customers | age, club status, newsletter subscription (= email reach) |
| `articles.csv` | 105,542 articles | category hierarchy for segment profiles |

Source: H&M Personalized Fashion Recommendations dataset (public, 2022). Files are read from the folder set in `config.yaml` / `.env` and staged to Parquet with DuckDB; the full data is processed (staging takes a few seconds, so no sampling was needed). Raw data is never committed.

What the first profiling pass established:
- **Channel encoding confirmed by a known event:** channel 1 has no sales from 2020-03-20 to 2020-05-05 (COVID store closures; stores reopened 2020-05-06) while channel 2 jumps, so 1 = store and 2 = online.
- **Prices are scaled:** `price × 590` lands exactly on retail price points (9.99, 19.99, 14.99 …) for every row, so money is reported as **CU (currency units)**; the currency itself is not disclosed. Revenue is gross demand: the file has no returns.
- **No quantity column:** 2.97M rows (9.4%) repeat another row exactly; they are extra units of the same item, not errors.
- **Some accounts buy like a business** (569 identical units in one day; purchases on 427 of 734 days), which needs a review rule.

## 2. Analysis outline

1. **Scope and metric definitions first:** `01_request_and_scope.md`, `02_metric_definitions.md`.
2. **Data quality** (`sql/01`, `sql/13`, notebook 01): row counts, keys, nulls, prices, duplicates, time range, extreme accounts, reconciliation → `03_data_quality_checks.md`.
3. **RFM scoring** (`sql/05`, notebook 02): snapshot 2020-09-22, F and M over the trailing 12 months, fixed thresholds compared with quintiles, the recency return curve, threshold sensitivity, K-Means as a cross-check.
4. **Segments** (notebook 03): 9 lifecycle segments + a Review List, a value tier as second axis, profiles (size, value, AOV, cycle, category affinity, channel, age, email reach), backtest validation, quarter-on-quarter migration.
5. **"If we do nothing"** (notebook 03): the same rules applied at 2019-09-22 (same season) and 2020-06-24 (last quarter), next-90-day behaviour observed and re-weighted to today's customer mix.
6. **Campaign plan and economics:** one row per audience; break-even lift; three scenarios; budget ask.
7. **Measurement:** the same 10% holdout in every audience, power per arm, decision rules → `measurement_plan.md`.
8. **Cohorts** (notebook 04): retention and observed LTV by first-order month and first channel; the order ladder.

## 3. Deliverables

`docs/` (request and scope, metric definitions, data quality, assumptions, segmentation spec, campaign plan, measurement plan, readout), `sql/` (standalone DuckDB files plus a single-query version of the segmentation), `notebooks/` 01–04 executed and exported to HTML, `dashboard/` (Streamlit, 8 pages in presentation order), `reports/report.html` (standalone) and `reports/action_plan.html`, one-command pipeline (`make all`).

## 4. Prior work reviewed

Public RFM write-ups usually stop at quintile scores, segment sizes and generic actions, and the public notebooks on this dataset are almost all about product recommendations rather than customer segmentation. This plan keeps the standard R / F / M scoring and named segments, compares cut methods (quintiles vs fixed thresholds vs K-Means) instead of assuming one, and adds what a CRM team needs to act: full-data SQL, store vs online, category affinity, a do-nothing projection from a backtest, campaign economics with break-even lifts, and a holdout design with power.

## 5. Decision log

| Stage | Decision | Why | Consulted |
|---|---|---|---|
| Scoping | Use the H&M data, not Olist | real, large, has customer attributes, article hierarchy and store/online channel, all needed for the questions asked | CRM Manager (brief) |
| Scoping | Snapshot 2020-09-22; F and M over the trailing 365 days | last day in the data; one full fashion season cycle; the same features can be rebuilt at backtest dates | — |
| Method | Fixed thresholds, quintiles shown for comparison | R and M cut-offs set near the quintiles, then moved to business periods and round amounts; F ties on one order (34% of active customers); fixed numbers keep audiences stable month to month | CRM team (naming) |
| Data | Money in CU = price × 590, gross demand | reconstructed shelf prices; shares and ratios do not depend on the unit; no returns in the data | Finance to confirm margin |
| Method | K-Means as a cross-check only | no natural clusters (separation best at k = 2); clusters move when refit; CRM tools need rules | — |
| Method review | Split Loyal into Loyal and Slipping Regulars; add a value tier | 65% of the original Loyal group were frequent buyers already 61–120 days quiet; high spenders also sit outside Champions | method review |
| Method review | Do-nothing projection = gap vs usual pace, re-weighted to today's mix, with scenarios | part of every gap is natural slowdown; today's At Risk group is unlike either backtest (60% last bought in the 2020 lockdown) | method review |
| Plan | Content-led rollout; discounts only in two sized test cells | valued at one order, a coupon needs a 5+ point lift to pay back where a quarter or more buy anyway | Finance (margin), CRM Manager (budget) |
| Measurement | Same 10% holdout in every audience; ITT; repurchase rate as primary KPI | unequal holdout shares would bias the pooled read; revenue is too noisy to be the primary KPI | — |
| Data | Review List instead of "exclude" for bulk / near-daily buyers | the data cannot prove staff or reseller status; 0.5% of revenue, so no result depends on it | Retail ops to review |
| Plan review | One low-cost email for Hibernating as well as Lost | the plan's own economics: a single email pays back at a lift of about 0.05 points, and Hibernating customers are more recent than Lost | CRM Manager |
| Presentation | Cohort analysis as an appendix page after the seven presentation pages | supports the New Customers decision without changing the story order | — |

## 6. Known limitations (tracked in `assumptions.md`)

Store purchases are only visible when the member identifies · revenue is before returns · 2020 is a COVID year · the first order in the data is not always a customer's first order ever · there is no past campaign, coupon or margin data, so lifts and costs are planning assumptions until the holdout measures them.
