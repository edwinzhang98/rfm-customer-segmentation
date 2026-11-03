# Autumn 2020 campaign: measurement plan

**Owner:** Marketing Analyst, CRM / Marketing Analytics · **Decision owner:** CRM Manager · **Assignment and launch:** 2020-09-28 · **Interim, guardrails only:** 2020-10-28 · **Final read:** 2020-12-27
This plan is fixed before launch; any later change is logged in section 11 with its date and reason. What each audience gets: [campaign plan](campaign_plan.md); who is in each audience: [segmentation spec](segmentation_spec.md).

## 1. What we will measure

We keep a random 10% of every audience out of the autumn campaign. They get everything a customer normally gets, just not the campaign, so they show what would have happened anyway. On 2020-12-27 we compare everyone assigned to the campaign with this holdout on one number, the share of customers who bought at least once in the 90 days from launch, and turn the difference into extra buyers, revenue and profit.

Three questions get an answer:

1. **Did the autumn wave as a whole make customers buy more than business as usual, and what was that worth?** This campaign-wide read is the main read.
2. **Does 10% off the second order pay for itself for New Customers?**
3. **Does 10% off pay for itself for At Risk customers 181-364 days quiet with 200+ CU?**

Single content emails are read only as a direction (section 6 explains why).

## 2. Control condition

| | Campaign arms | Holdout |
|---|---|---|
| Campaign emails, reminders, the welcome journey, day-30 hand-offs | yes | **no** |
| Personal member-app messages; Champions' early-access link | yes | **no** |
| Test-cell coupons | test cells only | **no** |
| Campaign paid social (New Customers; At Risk 181-364 days, 200+ CU) | non-subscribers in those audiences | **no**: uploaded as an exclusion audience on every campaign ad set and removed from lookalike seed lists |
| Campaign placements on site and app (early-access banner, "picked for you" modules) | yes | **switched off** |
| Business-as-usual newsletter, including the Black Friday (2020-11-27) and Christmas sends | yes | **yes** |
| Standard app and web personalisation (the recommendations every visitor sees) | yes | **yes** |
| Service and existing triggered messages (order and delivery confirmations, any trigger that already runs) | yes | **yes** |
| Brand advertising, store promotions, prices | yes | **yes** |

The read therefore measures what the campaign adds on top of business as usual. It says nothing about the value of the newsletter, Black Friday or Christmas themselves, because both groups get them.

- **How long:** holdout status covers the 90-day window (orders from 2020-09-28 to 2020-12-26), including the always-on triggers this plan starts: the Slipping Regulars reminder, and the welcome journey for customers who make a first order after launch (they get the same hash rule but are outside this read). After the window the holdout returns to normal targeting; the 12-month follow-up of the New Customers coupon compares the two treated cells and does not need it.
- **Contamination:** CRM and e-commerce log every send, app message, coupon issue and paid-social match by customer. Holdout customers with any campaign touch are counted at day 30 and day 90. They stay in the holdout for the analysis, because assignment, not receipt, defines the groups; contamination can only pull the measured lift towards zero, and its size is reported with the result.

## 3. Randomisation

- **Unit:** the customer.
- **Who is randomised:** each audience's reachable customers at the launch-day re-score, after suppressions: newsletter subscribers for the email-only audiences, everyone for New Customers and At Risk 181-364 days 200+ CU. The Review List and customers in another live test are removed before the split.
- **How:** a salted hash of the customer id gives every customer a fixed bucket from 0 to 99. The salt is new for this campaign and never reused by another test, so the holdouts of different tests are independent.

```sql
-- `pop` = the audience extract from the segmentation spec (section 8),
-- limited to reachable customers after suppressions
SET VARIABLE salt = 'autumn-2020-09-28';

SELECT
    customer_id,
    audience,                                                    -- audience of record
    CAST(('0x' || left(md5(getvariable('salt') || '|' || customer_id), 8)) AS BIGINT) % 100 AS bucket,
    CASE
        WHEN bucket < 10                                         THEN 'holdout'
        WHEN audience = 'new'                  AND bucket < 55   THEN 'journey'
        WHEN audience = 'new'                                    THEN 'journey_10pct_off'
        WHEN audience = 'at_risk_181_364_high' AND bucket < 70   THEN 'content_paid_social'
        WHEN audience = 'at_risk_181_364_high'                   THEN 'content_10pct_off'
        ELSE 'campaign'
    END AS arm
FROM pop;
```

| Bucket | New Customers | At Risk, 181-364 days, 200+ CU | Every other audience |
|---|---|---|---|
| 0-9 | holdout | holdout | holdout |
| 10-54 | welcome journey | win-back content + paid social | rollout arm |
| 55-69 | journey + 10% off 2nd order | win-back content + paid social | rollout arm |
| 70-99 | journey + 10% off 2nd order | win-back + 10% off | rollout arm |

- **The same 10% in every audience, stratified by audience.** The split is applied and checked within each audience, and effects are estimated per audience and then pooled. If holdout shares differed between audiences, the holdout's audience mix would differ from the campaign group's, and a simple pooled comparison would show a lift even if the campaign did nothing. One share plus a stratified estimate removes that.
- **Frozen assignment table:** customer id, audience of record, arm, bucket, salt, assignment date, and the pre-launch values used in the read (12-month spend and orders, recency, subscriber flag, `channel_12m`, value tier). Each customer id appears once, in one audience and one arm, and the send files are checked against it. Nobody changes it after the first send.
- **A/A balance check, before the first send:** in each audience, holdout vs each arm on 12-month spend, 12-month orders, recency, subscriber share, channel mix and value tier; every standardised difference (the gap between the two groups' averages divided by their standard deviation) must be below 0.1. Plus a placebo read: the same comparison on the 90 days *before* launch (orders from 2020-06-30 to 2020-09-27) must show no pooled difference beyond chance. A clear failure means one re-draw with a new salt, documented, before launch; never after.
- **Sample-ratio check at launch, day 30 and day 90:** observed customers per audience and arm against the planned shares (chi-square test). A p-value below 0.001 means the split or a suppression is broken; no lift is read until the cause is found.

## 4. Estimand

In plain words: how much more likely a customer is to buy at least once in the 90 days after launch because we put them in the campaign, compared with the held-out customers, counting everyone we assigned whether or not they opened anything.

- **Intention-to-treat (ITT).** Groups are defined by assignment, not by what a customer received. Emails not delivered or not opened, paid-social contacts never matched and customers who unsubscribe after launch all stay in their arm. The lifts in the campaign plan are ITT lifts, so the read is comparable with the plan. Effects "among openers" are not reported as campaign effects: openers choose themselves.
- **Segment of record:** the audience at the launch-day re-score. A customer is analysed in it even if a later refresh moves them to another segment.
- **Window:** orders dated 2020-09-28 to 2020-12-26, the same 90 days for every audience, read on 2020-12-27. Arms that start later (Loyal in week 2, Lost in week 4) have less time to work; that is accepted to keep one window and one pooled read.
- **Effects estimated:** per audience, campaign (any arm) vs holdout; campaign-wide, the audiences' effects weighted by their reachable populations, with the standard error combined across audiences the same way; for the two test cells, offer cell vs content cell of the same audience.

## 5. KPIs

| Level | KPI | Definition | Used for |
|---|---|---|---|
| **Primary** (every arm, fixed now) | 90-day repurchase rate | share of assigned customers with at least one order, store or online, in the window. For New Customers it is reported as the second-order rate: the same measure, as most of them have one order so far | lift per arm, the campaign-wide read, both offer decisions |
| Secondary | Revenue per assigned customer | 90-day revenue in CU (gross demand), winsorised: each customer's revenue capped at the 99th percentile of their audience (campaign and holdout together); the difference adjusted for 12-month spend before launch | incremental revenue |
| Secondary | Net profit | incremental revenue × 40% contribution margin − coupon value actually redeemed − contact cost actually incurred (email platform and paid-social invoices) | whether the wave paid; budget for the next wave |
| Guardrail | Unsubscribes, spam complaints, bounces | per send, against the business-as-usual newsletter in the same weeks | pause rule (section 8) |
| Guardrail | Coupon leakage | redemptions by anyone outside the two test cells | deactivate and reissue codes |
| Guardrail | Holdout contamination | holdout customers with any campaign touch | reported with the result |
| Guardrail | Returns on window orders, both groups | from the order system; this data extract has none | revenue net of returns, if Finance can supply it |
| Diagnostic | Delivery, opens, clicks, paid-social match rate, reach and frequency, coupon redemptions, AOV of buyers | never reported as effects | explaining the results |

- The revenue adjustment only reduces noise: assignment is random, so 12-month spend is balanced by design. The unadjusted difference is reported next to it.
- AOV among buyers (the Loyal arm's secondary KPI) is a diagnostic. Buyers are a group selected after treatment, so a difference in their AOV is not a clean effect; revenue per assigned customer is.
- The margin is the one agreed with Finance before launch and is not revisited after the results are in.

## 6. Sample size and detectable lifts

<!-- BEGIN:measurement -->
<!-- generated by `python run.py --steps docs` from the pipeline outputs; edit src/rfm/docgen.py, not this block -->

| Audience                        | Arm                                   | Role      | Reachable population   | Holdout   | Arm size   | Assumed lift (pp)   | Break-even (pp)   | Detectable lift (pp)   | Detectable revenue lift (CU/customer)   | Readable alone                   | Sized for its decision   |
|:--------------------------------|:--------------------------------------|:----------|:-----------------------|:----------|:-----------|:--------------------|:------------------|:-----------------------|:----------------------------------------|:---------------------------------|:-------------------------|
| Champions                       | Autumn early access                   | Rollout   | 89,749                 | 8,975     | 80,774     | 0.5                 | 0.04              | 1.17                   | 7.0                                     | no - pooled read                 | -                        |
| Loyal                           | Basket-building picks                 | Rollout   | 16,237                 | 1,624     | 14,613     | 0.5                 | 0.10              | 3.41                   | 5.0                                     | no - pooled read                 | -                        |
| Slipping Regulars               | Purchase-cycle reminder: autumn picks | Rollout   | 27,335                 | 2,734     | 24,602     | 1.5                 | 0.05              | 2.63                   | 8.4                                     | no - pooled read                 | -                        |
| Potential Loyalists             | Complete-the-look recommendations     | Rollout   | 47,922                 | 4,792     | 43,130     | 1.0                 | 0.04              | 2.13                   | 3.9                                     | no - pooled read                 | -                        |
| New Customers                   | Welcome journey                       | Rollout   | 71,117                 | 7,112     | 32,003     | 1.5                 | 0.99              | 1.66                   | 2.6                                     | no - pooled read                 | -                        |
| New Customers                   | Welcome journey + 10% off 2nd order   | Test cell | 71,117                 | 7,112     | 32,003     | 3.0                 | 6.07              | 1.66                   | 2.6                                     | yes                              | yes                      |
| Needs Attention                 | Summer-to-autumn new-arrivals edit    | Rollout   | 50,823                 | 5,082     | 45,741     | 1.0                 | 0.04              | 1.97                   | 3.3                                     | no - pooled read                 | -                        |
| At Risk, 121-180 days           | Win-back content (email only)         | Rollout   | 14,547                 | 1,455     | 13,092     | 1.0                 | 0.04              | 3.84                   | 8.3                                     | no - pooled read                 | -                        |
| At Risk, 181-364 days, 200+ CU  | Win-back content + paid social        | Rollout   | 23,960                 | 2,396     | 14,376     | 1.0                 | 0.50              | 2.73                   | 6.7                                     | no - pooled read                 | -                        |
| At Risk, 181-364 days, 200+ CU  | Win-back + 10% off                    | Test cell | 23,960                 | 2,396     | 7,188      | 2.5                 | 5.08              | 2.92                   | 7.1                                     | no - decided vs its content cell | yes                      |
| At Risk, 181-364 days, < 200 CU | Win-back content (email only)         | Rollout   | 9,236                  | 924       | 8,312      | 0.5                 | 0.08              | 4.37                   | 5.1                                     | no - pooled read                 | -                        |
| Hibernating                     | One 'new season' email                | Rollout   | 81,466                 | 8,147     | 73,319     | 0.3                 | 0.05              | 1.12                   | 1.4                                     | no - pooled read                 | -                        |
| Lost                            | One reactivation email                | Rollout   | 106,123                | 10,612    | 95,511     | 0.2                 | 0.05              | 0.74                   | 0.9                                     | no - pooled read                 | -                        |

<!-- END:measurement -->

"Detectable lift" is the smallest true lift the test finds 80% of the time at 95% confidence (two-sided). It uses the business-as-usual repurchase rate from the 2019 backtest (2020 for Lost) and the arm and holdout sizes (`src/rfm/power.py`). If the true lift is smaller, the test will most likely report "no clear difference".

- **Campaign-wide, the main read.** 538,515 reachable customers, 53,852 of them held out, business-as-usual repurchase rate 37.1%. The pooled read detects a lift from **0.51 points**; if every arm delivers its planning assumption the expected lift is **0.84 points**, so the main read is adequately sized. It includes the test cells: it is the effect of the autumn wave as sent.
- **Content arms are directional only.** Their detectable lifts (0.74 to 4.37 points) are above the lifts they are expected to deliver (0.2 to 1.5). A bigger holdout would not fix that at a sensible price: even with 30% held out, the detectable lift would still be 0.76 points for Champions (assumed 0.5) and 1.72 for Slipping Regulars (assumed 1.5), while the profit given up by holding out (6.1K CU at 10%) would roughly triple. Content arms are therefore judged through the pooled read.
- **The two test cells are sized for their decision:** their detectable lift is at most two thirds of break-even (New Customers 1.66 vs 6.07 points; At Risk 2.92 vs 5.08). If an offer adds nothing, the top of its 95% interval lands at no more than about half of break-even, so "it does not pay" is a clear answer rather than "we could not tell". The table compares with the holdout; the decision compares with the content cell, which is larger than the holdout, so the decision comparison is more precise than the table shows.
- **"Readable alone" for the test cells.** The column compares the detectable lift with the assumed lift. The At Risk offer cell shows "no" because its assumed 2.5 points is below its 2.92-point detectable lift against the holdout. That does not affect its decision, which is about break-even (5.08 points) and is made against the content cell; the "pooled read" label applies to the content arms only.
- **Revenue:** the revenue column uses the raw spread of 90-day revenue; capping at the 99th percentile and the 12-month-spend adjustment will make the real read tighter.
- **Paid social is not sized for its own question.** For the arms that use it (New Customers journey: detectable 1.66 vs break-even 0.99 points; At Risk 181-364 days 200+ CU content: 2.73 vs 0.50) the answer to "does paid social pay?" will most likely be inconclusive; section 7 says what happens then.

## 7. Decision rules (fixed before launch)

| Question | Comparison | Scale or keep only if | Otherwise |
|---|---|---|---|
| Does 10% off the second order pay for New Customers? | coupon cell vs journey-only cell | the 95% lower bound of the lift clears break-even: 6.07 points at planning values, re-checked with the measured coupon use and coupon-order value; the higher of the two applies | journey without coupon. The 12-month follow-up (2021-09-28) can reopen the question, not close it early |
| Does 10% off pay for At Risk 181-364 days, 200+ CU? | offer cell vs content + paid social cell | the lower bound clears break-even: 5.08 points at planning values, re-checked the same way, Holm-adjusted within At Risk | content-only win-back in the next wave |
| Did the autumn wave work? | everyone assigned vs holdout, stratified by audience | the 95% interval of the pooled lift lies above zero | content is reviewed before any arm becomes always-on |
| Keep a content arm as an always-on journey? | arm vs holdout (directional) | the pooled read passes and the arm's own estimate is above zero | not made always-on; reworked and read again with the next wave |
| Keep paid social (New Customers; At Risk 181-364 days, 200+ CU)? | arm vs holdout; the split by subscriber status shows how much comes from the non-subscribers that paid social reaches | the lower bound clears the arm's break-even (0.99 and 0.50 points) | not kept by default; a test sized for the paid-social question goes into the next wave |

**Holm within At Risk.** The three At Risk audiences carry five pre-registered comparisons: the offer vs the content cell, the offer vs the holdout, content + paid social vs the holdout, and the two email-only win-back arms vs their holdouts. They are tested together with Holm's step-down method at the 5% level: the strongest result is judged at 5% / 5 = 1%, the next at 5% / 4, and so on, and once one comparison fails, all weaker ones fail too. Each comparison is tested against its own threshold: break-even for the two decision comparisons, zero for the others. Even at the strictest step the offer comparison's detectable lift stays below two thirds of break-even, because it is made against the content cell, twice the offer cell's size.

**General rules.** No decision before day 90 and no early stop for success. Decisions use the lower end of a two-sided 95% interval; within At Risk, the interval at the Holm-adjusted level. Breakdowns by value tier, `channel_12m` and subscriber status are reported as directional; anything not listed in this plan is labelled exploratory.

## 8. Interim read (day 30, 2020-10-28)

A health check, not a result. It covers:

- delivery per arm: sends, bounces, paid-social match rates, reach and frequency;
- guardrails per arm: unsubscribe and complaint rates against the business-as-usual newsletter in the same weeks;
- coupon redemptions against plan, and any leakage outside the test cells;
- the sample-ratio re-check and the holdout contamination count.

No lift is computed or circulated at day 30, and no arm is stopped or scaled because of early sales. An arm is paused only for a guardrail breach (unsubscribe or complaint rate more than twice the business-as-usual newsletter's in the same weeks) or an operational error (wrong audience, holdout contacted, coupon leaking). A pause is logged in section 11, and paused customers stay in their arm for the final read.

## 9. Read-out template (2020-12-27)

The read is one script run once against the frozen assignment table, checked by a second analyst before it goes to the CRM Manager. All lifts are ITT, in percentage points of the 90-day repurchase rate; revenue is gross demand in CU. Planned sizes come from the table in section 6.

**A. Health checks** (all must pass before any lift is read)

| Check | Pass rule | Result |
|---|---|---|
| Sample ratio, per audience and arm | chi-square p-value ≥ 0.001 | |
| Balance at launch | every standardised difference < 0.1 | |
| Placebo: 90 days before launch | pooled difference within chance | |
| Holdout contamination | share of holdout customers with any campaign touch (reported) | |
| Delivery | share of the campaign group sent or matched (reported) | |

**B. Campaign-wide, the main read**

| Group | Customers (planned) | Repurchase rate | Lift vs holdout [95% CI] | Incremental buyers [95% CI] | Revenue per customer, adjusted (CU) [95% CI] | Incremental revenue (CU) | Net profit (CU) |
|---|---|---|---|---|---|---|---|
| Campaign, all arms | 411,344 | | | | | | |
| Holdout | 53,852 | | – | – | | – | – |

**C. Offer decisions**

| Test | Offer / content cell (planned) | Repurchase rate, offer / content | Lift over content [95% CI] | Break-even, planning / re-checked | Lower bound above break-even? | Decision |
|---|---|---|---|---|---|---|
| New Customers, 10% off the second order | 32,003 / 32,003 | | | 6.07 / | | |
| At Risk 181-364 days 200+ CU, 10% off (Holm level) | 7,188 / 14,376 | | | 5.08 / | | |

Under the table: coupon redemption rate per cell, and the estimated share of would-be buyers who redeemed (planning assumption 50%).

**D. Every arm vs its holdout** (directional unless marked as a decision)

| Audience | Arm | Assigned / holdout (planned) | Lift [95% CI] | Assumed lift | Break-even | Revenue per customer lift (CU) [95% CI] | Read as |
|---|---|---|---|---|---|---|---|
| one row per arm in section 6 | | | | | | | directional / decision |

**E. Guardrails**

| Arm | Unsubscribes vs business-as-usual newsletter | Complaints vs business-as-usual newsletter | Bounces | Paid-social match rate / frequency | Coupon leakage |
|---|---|---|---|---|---|
| one row per arm | | | | | |

**F. Decisions and next wave:** one line per row of the section 7 table (rule, result, decision), followed by what changes in the next wave.

## 10. What we will and will not be able to say

On 2020-12-27 we **will** be able to say:

- whether the autumn wave as a whole raised the 90-day repurchase rate above business as usual, with a 95% interval (detectable from 0.51 points);
- how many extra buyers, how much extra revenue (gross demand) and what net profit at the agreed margin it produced, each with an interval;
- whether each of the two offers pays for itself against content alone, as a scale / do-not-scale decision; a "no" will be informative, because the cells are sized for it;
- how often coupons were used, and roughly how much of that use came from customers who would have bought anyway, replacing the 50% assumption;
- whether contact pressure hurt in any arm (unsubscribes, complaints).

We will **not** be able to say:

- which single content email works, or how large each audience's own effect is: those reads are directional;
- whether paid social pays in its own right: the test is not sized for it;
- what a second order or a won-back customer is worth beyond 90 days (that is the 12-month follow-up), or how much of the lift is orders pulled forward from January (days 91-180 are checked, but not used for decisions);
- what the business-as-usual newsletter, Black Friday or Christmas are worth: the holdout gets them too;
- whether online-only customers would be worth more if they shopped in store: not tested;
- revenue net of returns, unless Finance can supply returns for both groups;
- anything about customers outside the experiment: non-subscribers in the email-only audiences and the Review List;
- how much of the "gap vs usual pace" the campaign recovered. Much of that gap is natural slowdown and it was never the target; the measured lift is;
- why something worked. Opens and clicks describe exposure, not effect, and breakdowns beyond the pre-registered ones (audience, value tier, channel, subscriber status) are exploratory.

## 11. Change log

| Date | Change | Reason | Approved by |
|---|---|---|---|
| before launch | Version 1.0 of this plan | | CRM Manager |
