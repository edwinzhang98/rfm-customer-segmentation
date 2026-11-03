/* =============================================================================
   05_customer_rfm.sql  -  RFM features, scores and segment for every customer
   -----------------------------------------------------------------------------
   Inputs  : data/marts/fct_orders.parquet
             data/marts/dim_customers.parquet
   Output  : data/marts/customer_rfm.parquet
             grain: one row per snapshot x customer with >= 1 order on or before the
             snapshot date. Three snapshots are built with identical rules:
               current           2020-09-22  (used for targeting)
               backtest_seasonal 2019-09-22  (same season one year earlier)
               backtest_recent   2020-06-24  (last full 90 days)
   Definitions (full text in docs/02_metric_definitions.md):
     recency_days   = snapshot_date - last order date        (0 = bought on the snapshot day)
     frequency_12m  = orders in the 365 days ending on the snapshot date
     monetary_12m   = revenue (CU) in the same 365 days
     tenure_days    = snapshot_date - first order date seen in the data
   Scores (fixed business thresholds, not quantiles):
     R: 5 = 0-30 days, 4 = 31-60, 3 = 61-120, 2 = 121-180, 1 = 181-364, 0 = 365+ (Lost)
     F: 5 = 10+ orders, 4 = 5-9, 3 = 3-4, 2 = 2, 1 = 1, 0 = none in 12 months
     M: 5 = 400+ CU, 4 = 200-399, 3 = 100-199, 2 = 50-99, 1 = < 50, 0 = none in 12 months
   Segments (first matching rule wins):
     Excluded            suspected staff / reseller account (dim_customers.is_excluded)
     Lost                no order in the last 365 days
     New Customers       first order within the last 90 days
     Champions           R >= 4 and F >= 4 and M >= 4
     Loyal               R >= 3 and F >= 4
     Potential Loyalists R >= 4                 (bought in the last 60 days, < 5 orders)
     Needs Attention     R = 3                   (61-120 days, < 5 orders)
     At Risk             R <= 2 and (F >= 3 or M >= 4)   (121-364 days, used to buy often / a lot)
     Hibernating         everything else         (121-364 days, 1-2 orders, < 200 CU)
   Params  : snapshot_current / snapshot_seasonal / snapshot_recent, lookback_days,
             r*/f*/m* thresholds, new_customer_days (defaults = config.yaml)
   Run     : python scripts/run_sql.py sql/05_customer_rfm.sql
   ============================================================================= */

SET VARIABLE snapshot_current  = COALESCE(getvariable('snapshot_current'),  DATE '2020-09-22');
SET VARIABLE snapshot_seasonal = COALESCE(getvariable('snapshot_seasonal'), DATE '2019-09-22');
SET VARIABLE snapshot_recent   = COALESCE(getvariable('snapshot_recent'),   DATE '2020-06-24');
SET VARIABLE lookback_days     = COALESCE(getvariable('lookback_days'), 365);
SET VARIABLE r5_max_days       = COALESCE(getvariable('r5_max_days'), 30);
SET VARIABLE r4_max_days       = COALESCE(getvariable('r4_max_days'), 60);
SET VARIABLE r3_max_days       = COALESCE(getvariable('r3_max_days'), 120);
SET VARIABLE r2_max_days       = COALESCE(getvariable('r2_max_days'), 180);
SET VARIABLE f5_min_orders     = COALESCE(getvariable('f5_min_orders'), 10);
SET VARIABLE f4_min_orders     = COALESCE(getvariable('f4_min_orders'), 5);
SET VARIABLE f3_min_orders     = COALESCE(getvariable('f3_min_orders'), 3);
SET VARIABLE f2_min_orders     = COALESCE(getvariable('f2_min_orders'), 2);
SET VARIABLE m5_min_cu         = COALESCE(getvariable('m5_min_cu'), 400);
SET VARIABLE m4_min_cu         = COALESCE(getvariable('m4_min_cu'), 200);
SET VARIABLE m3_min_cu         = COALESCE(getvariable('m3_min_cu'), 100);
SET VARIABLE m2_min_cu         = COALESCE(getvariable('m2_min_cu'), 50);
SET VARIABLE new_customer_days = COALESCE(getvariable('new_customer_days'), 90);

COPY (
    WITH
    snapshots (snapshot_name, snapshot_date) AS (
        VALUES ('current',           getvariable('snapshot_current')),
               ('backtest_seasonal', getvariable('snapshot_seasonal')),
               ('backtest_recent',   getvariable('snapshot_recent'))
    ),

    -- 1. Order history up to each snapshot, with the trailing-12-month window flagged
    orders_to_snapshot AS (
        SELECT
            s.snapshot_name,
            s.snapshot_date,
            o.customer_id,
            o.order_date,
            o.sales_channel_id,
            o.n_units,
            o.revenue_cents,
            (s.snapshot_date - o.order_date) < getvariable('lookback_days') AS in_12m
        FROM snapshots s
        JOIN 'data/marts/fct_orders.parquet' o
          ON o.order_date <= s.snapshot_date
    ),

    -- 2. One row per snapshot x customer: raw R, F, M inputs
    features AS (
        SELECT
            snapshot_name,
            snapshot_date,
            customer_id,
            MIN(order_date)                                                  AS first_order_date,
            MAX(order_date)                                                  AS last_order_date,
            MIN(order_date) FILTER (WHERE in_12m)                            AS first_order_date_12m,
            COUNT(*)                                                         AS orders_to_date,
            SUM(revenue_cents)                                               AS revenue_to_date_cents,
            COUNT(*) FILTER (WHERE in_12m)                                   AS frequency_12m,
            COALESCE(SUM(revenue_cents) FILTER (WHERE in_12m), 0)            AS monetary_12m_cents,
            COALESCE(SUM(n_units) FILTER (WHERE in_12m), 0)                  AS units_12m,
            COUNT(*) FILTER (WHERE in_12m AND sales_channel_id = 1)          AS store_orders_12m,
            COUNT(*) FILTER (WHERE in_12m AND sales_channel_id = 2)          AS online_orders_12m,
            COALESCE(SUM(revenue_cents) FILTER (WHERE in_12m AND sales_channel_id = 2), 0)
                                                                             AS online_revenue_12m_cents
        FROM orders_to_snapshot
        GROUP BY snapshot_name, snapshot_date, customer_id
    ),

    -- 3. Derived measures
    measures AS (
        SELECT
            *,
            snapshot_date - last_order_date                                  AS recency_days,
            snapshot_date - first_order_date                                 AS tenure_days,
            monetary_12m_cents / 100.0                                       AS monetary_12m_cu,
            CASE WHEN frequency_12m >= 2
                 THEN (last_order_date - first_order_date_12m) / (frequency_12m - 1.0)
            END                                                              AS avg_days_between_orders_12m
        FROM features
    ),

    -- 4. R, F, M scores with fixed business thresholds
    scored AS (
        SELECT
            *,
            CASE WHEN recency_days <= getvariable('r5_max_days')  THEN 5
                 WHEN recency_days <= getvariable('r4_max_days')  THEN 4
                 WHEN recency_days <= getvariable('r3_max_days')  THEN 3
                 WHEN recency_days <= getvariable('r2_max_days')  THEN 2
                 WHEN recency_days <  getvariable('lookback_days') THEN 1
                 ELSE 0 END                                                  AS r_score,
            CASE WHEN frequency_12m >= getvariable('f5_min_orders') THEN 5
                 WHEN frequency_12m >= getvariable('f4_min_orders') THEN 4
                 WHEN frequency_12m >= getvariable('f3_min_orders') THEN 3
                 WHEN frequency_12m >= getvariable('f2_min_orders') THEN 2
                 WHEN frequency_12m >= 1                            THEN 1
                 ELSE 0 END                                                  AS f_score,
            CASE WHEN frequency_12m = 0                             THEN 0
                 WHEN monetary_12m_cu >= getvariable('m5_min_cu')   THEN 5
                 WHEN monetary_12m_cu >= getvariable('m4_min_cu')   THEN 4
                 WHEN monetary_12m_cu >= getvariable('m3_min_cu')   THEN 3
                 WHEN monetary_12m_cu >= getvariable('m2_min_cu')   THEN 2
                 ELSE 1 END                                                  AS m_score
        FROM measures
    )

    -- 5. Segment rules (first match wins) + attributes used for targeting
    SELECT
        s.snapshot_name,
        s.snapshot_date,
        s.customer_id,
        s.first_order_date,
        s.last_order_date,
        s.recency_days,
        s.tenure_days,
        s.frequency_12m,
        s.monetary_12m_cents,
        s.monetary_12m_cu,
        s.units_12m,
        s.store_orders_12m,
        s.online_orders_12m,
        s.online_revenue_12m_cents,
        s.avg_days_between_orders_12m,
        s.orders_to_date,
        s.revenue_to_date_cents,
        s.r_score,
        s.f_score,
        s.m_score,
        CAST(s.r_score AS VARCHAR) || CAST(s.f_score AS VARCHAR) || CAST(s.m_score AS VARCHAR) AS rfm_code,
        CASE
            WHEN d.is_excluded                                         THEN 'Excluded'
            WHEN s.recency_days >= getvariable('lookback_days')        THEN 'Lost'
            WHEN s.tenure_days  <  getvariable('new_customer_days')    THEN 'New Customers'
            WHEN s.r_score >= 4 AND s.f_score >= 4 AND s.m_score >= 4  THEN 'Champions'
            WHEN s.r_score >= 3 AND s.f_score >= 4                     THEN 'Loyal'
            WHEN s.r_score >= 4                                        THEN 'Potential Loyalists'
            WHEN s.r_score  = 3                                        THEN 'Needs Attention'
            WHEN s.f_score >= 3 OR s.m_score >= 4                      THEN 'At Risk'
            ELSE 'Hibernating'
        END                                                            AS segment,
        d.is_excluded,
        d.channel_profile,
        d.is_newsletter_subscriber,
        d.club_member_status,
        d.age_band
    FROM scored s
    JOIN 'data/marts/dim_customers.parquet' d USING (customer_id)
    ORDER BY s.snapshot_name, s.customer_id
) TO 'data/marts/customer_rfm.parquet' (FORMAT parquet, COMPRESSION zstd);

SELECT snapshot_name, segment, COUNT(*) AS customers
FROM 'data/marts/customer_rfm.parquet'
GROUP BY ALL
ORDER BY snapshot_name, customers DESC;
