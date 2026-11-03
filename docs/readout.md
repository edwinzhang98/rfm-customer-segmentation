# Autumn campaign readout

**To:** CRM Manager · **From:** Marketing Analyst, CRM / Marketing Analytics · **Data as of:** 2020-09-22 · **Launch:** 2020-09-28

**Subject: Autumn campaign: who gets what, a 61K CU budget, and how we will know it worked**

<sub>Source: H&M Personalized Fashion Recommendations dataset (Kaggle, 2022), 2018-09-20 to 2020-09-22. CU = the file's price x 590, which lands on shelf prices such as 9.99 (currency not disclosed).</sub>

## The short answer

- **Keep: Champions.** 190K customers (14%) bring in 54% of 12-month revenue, and 83% buy again within 90 days without any campaign. They get early access, not a discount.
- **Win back: At Risk.** 90K customers who used to buy often or a lot have gone quiet for 4-12 months: left alone, they are expected to spend 3.7M CU in the next 90 days instead of their usual 5.8M CU. The plan expects to win back about 45K CU of the difference (26K from content emails, the rest from the offer test cell). **Catch early:** 62K Slipping Regulars (5+ orders a year, 61-120 days quiet).
- **Online-only: reach them online.** 483K active customers (49%) had no identified store purchase in 12 months; nothing shows that a store push would raise their value.
- **Measure** against the same 10% holdout in every audience: the share who buy again within 90 days, with the final read on 27 December.

## What I recommend for autumn

<!-- BEGIN:campaign_short -->
| Audience                        | Action                                          | When                                          | Channel             | Category focus                                         | Discount   | Expected net (CU)   |
|:--------------------------------|:------------------------------------------------|:----------------------------------------------|:--------------------|:-------------------------------------------------------|:-----------|:--------------------|
| Champions                       | Autumn early access                             | 2020-09-29, two days before the public launch | Email + member app  | their own top categories (no category at index >= 120) | none       | 8,669               |
| Loyal                           | Basket-building picks                           | Week 2 (from 2020-10-05)                      | Email + member app  | Accessories (179), Jersey Basic (148)                  | none       | 551                 |
| Slipping Regulars               | Purchase-cycle reminder: autumn picks           | Week 1 (2020-09-28), reminder day 10          | Email + member app  | their own top categories (no category at index >= 120) | none       | 7,882               |
| Potential Loyalists             | Complete-the-look recommendations               | Week 1 (from 2020-09-28)                      | Email + member app  | Sport dept. (126)                                      | none       | 9,360               |
| New Customers                   | Welcome journey                                 | Starts day 7 after the first order            | Email + paid social | Swimwear (141), Sport dept. (124)                      | none       | 3,371               |
| New Customers                   | Welcome journey + 10% off 2nd order (test cell) | Same as the journey (parallel cell)           | Email + paid social | Swimwear (141), Sport dept. (124)                      | 10%        | -15,208             |
| Needs Attention                 | Summer-to-autumn new-arrivals edit              | Week 1 (from 2020-09-28)                      | Email + member app  | Swimwear (184)                                         | none       | 9,907               |
| At Risk, 121-180 days           | Win-back content (email only)                   | Week 1 (from 2020-09-28)                      | Email only          | their own top categories (no category at index >= 120) | none       | 3,596               |
| At Risk, 181-364 days, 200+ CU  | Win-back content + paid social                  | Week 1 (from 2020-09-28)                      | Email + paid social | Outdoor (165), Knitwear (155)                          | none       | 3,002               |
| At Risk, 181-364 days, 200+ CU  | Win-back + 10% off (test cell)                  | Week 1, in parallel with the content cell     | Email + paid social | Outdoor (165), Knitwear (155)                          | 10%        | -5,823              |
| At Risk, 181-364 days, < 200 CU | Win-back content (email only)                   | Week 1 (from 2020-09-28)                      | Email only          | Knitwear (162), Menswear dept. (128)                   | none       | 451                 |
| Lost                            | One reactivation email                          | Week 4 (from 2020-10-19)                      | Email only          | Baby/Children dept. (330), Menswear dept. (125)        | none       | 3,276               |
| Hibernating                     | no autumn spend                                 | -                                             | -                   | -                                                      | -          | -                   |
| Review List                     | no autumn spend                                 | -                                             | -                   | -                                                      | -          | -                   |

<sub>Generated from the pipeline outputs by `python run.py --steps docs`; do not edit by hand.</sub>
<!-- END:campaign_short -->

<sub>Expected net = 90-day profit after discount and contact costs, under base-case planning assumptions (not measured yet); the two negative rows are the test cells' expected learning cost.</sub>

- **No discounts for customers who buy anyway** (83% of Champions, 68% of Loyal): a coupon would mostly be redeemed on orders they place anyway, while an extra buyer is worth about one order.
- **Discounts only in two test cells.** 10% off must add about 6 percentage points of repurchase (New Customers' second order) or 5 (At Risk 181-364 days, 200+ CU) to break even, twice what I assume; 20% off and a Loyal voucher (14 and 12 points needed) were dropped.
- **Content first.** At 0.01 CU an email, most content actions break even at a lift of 0.1 points or less; paid social goes only to New Customers and long-lapsed high spenders, two thirds of whom are not on email.
- **Channel decides the message, not a store push.** Online-only customers' higher spend at the same number of orders is mostly basket size, before returns (an online order is about twice a store order, 70 vs 33 CU, even for the same customers), and they come back slightly less often. They get online creative and no store invitations.
- **Audiences are rebuilt on launch day:** 51% of customers changed segment in one quarter.

## What it costs and what it should return

- **Budget ask: 61K CU.** 13K for the content rollout and 48K for the two test cells, 40K of it coupon value.
- **Rollout:** expected +50K CU profit within 90 days on 157K CU of extra revenue, valuing each extra buyer at one order; +1.4K CU in the pessimistic case (half the lifts, 30% margin, paid social at double cost), +227K CU in the optimistic one.
- **Test cells are a learning cost:** expected -21K CU (range -49K to +39K) to find out whether the offers pay before anyone scales them. If the budget shrinks, the At Risk test cell goes first.
- **Recovery next to the gap:** At Risk is 2.1M CU below its usual pace (up to 2.4M), Slipping Regulars 965K CU; the plan expects to win back about 45K and 20K CU. Much of each gap is natural slowdown that no email reverses (even Champions are 3.4M CU below pace, which is not churn), so judge the campaign on its measured lift.

## How we will know it worked

- **The holdout:** 10% of every audience, picked at random and checked to look like the rest, gets no campaign messages but keeps the normal newsletters, Black Friday and Christmas sends. Everyone assigned counts, opened or not. It costs about 6K CU of forgone profit.
- **On 27 December we will know** whether the campaign as a whole works, our main read (the holdout can show a lift as small as 0.57 points; we expect 0.94), and whether each offer pays (each test cell is big enough to show a lift two thirds the size of its break-even).
- **We will not know** which single content email works on its own, what a second order is worth beyond 90 days, or how much is returned. Day 30 (28 October) is a health check only: delivery, unsubscribes, complaints.

## What I need from you

1. **Sign-off on the plan and the 61K CU budget** this week, before audiences are built for the 28 September launch.
2. **Finance to confirm the 40% margin** (H&M gross margin 50.0% in FY2020, 52.6% in FY2019, less about 10 points for fulfilment and returns); the offers' break-even depends on it.
3. **Retail ops, with CRM, to review the 864 Review List accounts** (bulk or near-daily buying, 0.5% of revenue); no offers or paid media until then.
4. **Agreement that offers scale only on measured results:** only if the low end of the 95% range for their lift over the content-only cell clears break-even.

## Caveats

- **Gross demand.** The data has no returns, so every revenue figure is before returns; in fashion, returns tend to be higher online.
- **A COVID autumn.** 60% of today's At Risk last bought in the March-May lockdown (stores closed 2020-03-20 to 2020-05-05); another closure would push store-heavy customers below every scenario.
- **"Online-only" means no identified store purchase:** store purchases count only when the member identifies.
- **Planning assumptions.** Lifts, coupon use, contact costs and margin stay assumptions until the holdout measures them.

<sub>Detail: segment rules in the [segmentation spec](segmentation_spec.md), actions, timing and economics in the [campaign plan](campaign_plan.md), holdout and test sizes in the [measurement plan](measurement_plan.md).</sub>
