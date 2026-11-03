# 01 — Request and scope

## The request (verbatim, from the CRM Manager)

> 「秋季 campaign 预算有限，我想知道该给哪些客户发什么。谁是高价值要维护的，谁快流失了要挽回，谁只在线上买从不进店？给我分群和每群的建议，还有这次 campaign 怎么衡量效果。」

English translation:

> "The autumn campaign budget is limited, so I want to know which customers should get what. Who are the high-value customers we need to keep, who is about to churn and needs winning back, and who only buys online and never comes into a store? Give me segments and a recommendation per segment, plus how we will measure whether this campaign worked."

Standard outputs for this kind of request on our team: segmentation rule document, segment profiles with target counts, campaign recommendation table, measurement plan (holdout).

## Clarified analysis questions

| # | Business question | Analysis question (what we will actually compute) | Output |
|---|---|---|---|
| Q1 | Who is high value and must be retained? | Which customers bought recently, often and for a high amount in the 12 months to 2020-09-22, and what share of revenue do they drive? | Champions / Loyal segment counts, revenue share, profile |
| Q2 | Who is about to churn and worth winning back? | Which previously valuable customers have stopped buying (121–364 days since last order), how likely are they to come back on their own within 90 days, and how much revenue do we lose in the next 90 days if we do nothing? | At Risk / Needs Attention segments, 90-day revenue-at-risk estimate with range |
| Q3 | Who only buys online and never visits a store? | What share of each segment has *only* online orders in the full two-year window, and how do they differ in value and category from store-only and omnichannel customers? | channel overlay per segment |
| Q4 | What should each segment receive? | Per segment: goal, action (offer / message), timing, channel, category focus, expected lift, cost and the lift needed to break even | campaign plan table |
| Q5 | How do we measure the campaign? | Randomised holdout per segment: size, primary KPI, minimum detectable effect, read-out dates | measurement plan |

## Decision maker and decision points

- **Decision maker:** CRM Manager (budget owner for the autumn campaign). Consulted: e-commerce (online placements), retail operations (store events / in-store offers), finance (margin and discount budget).
- **Decisions this analysis informs:**
  1. Which segments get *paid* actions (discounts, paid media) vs *free* actions (newsletter content, member-app messages) vs nothing.
  2. Discount depth per segment (no discount for customers who buy anyway).
  3. Size of the holdout group that is kept out of the campaign so we can measure incremental revenue.
- **When needed:** before the autumn campaign brief is locked (campaign assumed to launch in the week of 2020-09-28; data snapshot 2020-09-22).

## What would change the decision

- If the At Risk segment's natural 90-day return rate is already high (customers come back without help), a discount there mostly subsidises purchases that would happen anyway → move budget to cheaper content or to lower-return groups.
- If the break-even lift for an offer is above what is plausible, do not fund that offer at full scale — test it on a smaller cell first.
- If online-only customers are not less valuable than omnichannel ones at the same RFM level, a "visit the store" push has no clear upside.

## Scope

**In scope:** customers with at least one purchase between 2018-09-20 and 2020-09-22 (1,362,281); RFM as of 2020-09-22; segment rules a CRM tool can apply; 90-day counterfactual; campaign plan and holdout design; cohorts by first-purchase month.

**Out of scope (and why):** product recommendations per customer (different problem, Kaggle competition's original task); predicted CLV models (rules + backtest are enough for this decision); price elasticity (no list-price vs paid-price data); store-level planning (no store ID).

## Data limitations the CRM Manager should know up front

- Store purchases are only recorded when the shopper identifies as a member, so "online-only" means "no *identified* store purchase".
- Prices in the public data are scaled; money is shown in reconstructed currency units (CU), see `02_metric_definitions.md`.
- 2020 includes COVID store closures (stores fully closed 2020-03-23 → 2020-04-26 in this data).
- There is no past campaign, coupon or margin data: expected lifts are planning assumptions that the holdout test will replace with measured numbers.
