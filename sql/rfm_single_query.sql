/* =============================================================================
   rfm_single_query.sql  -  the whole RFM scoring and segmentation in one query
   -----------------------------------------------------------------------------
   Input   : data/staged/stg_transactions.parquet only (raw item rows)
   Output  : one row per segment (customers, share, 12-month revenue share)
   Purpose : a compact, self-contained version of sql/02-05 for ad-hoc use and review:
             raw rows -> orders -> R / F / M -> scores -> segments. It reproduces the
             production segment counts except the Review List (which needs the
             bulk-buying flags from sql/04) - those 864 accounts land in their
             behavioural segment here.
   Run     : python scripts/run_sql.py sql/rfm_single_query.sql
   ============================================================================= */

WITH
params AS (SELECT DATE '2020-09-22' AS snapshot_date, 365 AS lookback_days, 90 AS new_customer_days),

-- 1. one row per order = customer x day x channel; money in CU (price x 590), integer cents
orders AS (
    SELECT customer_id, t_dat AS order_date, sales_channel_id,
           SUM(CAST(ROUND(price * 59000) AS BIGINT)) AS revenue_cents
    FROM 'data/staged/stg_transactions.parquet'
    GROUP BY ALL
),

-- 2. raw R, F, M per customer at the snapshot
rfm AS (
    SELECT o.customer_id,
           p.snapshot_date - MAX(o.order_date)                                        AS recency_days,
           p.snapshot_date - MIN(o.order_date)                                        AS tenure_days,
           COUNT(*) FILTER (WHERE p.snapshot_date - o.order_date < p.lookback_days)    AS frequency_12m,
           COALESCE(SUM(o.revenue_cents) FILTER (WHERE p.snapshot_date - o.order_date < p.lookback_days), 0) / 100.0
                                                                                      AS monetary_12m_cu
    FROM orders o CROSS JOIN params p
    WHERE o.order_date <= p.snapshot_date
    GROUP BY o.customer_id, p.snapshot_date
),

-- 3. scores with fixed business thresholds
scored AS (
    SELECT *,
           CASE WHEN recency_days <= 30 THEN 5 WHEN recency_days <= 60 THEN 4 WHEN recency_days <= 120 THEN 3
                WHEN recency_days <= 180 THEN 2 WHEN recency_days < 365 THEN 1 ELSE 0 END          AS r,
           CASE WHEN frequency_12m >= 10 THEN 5 WHEN frequency_12m >= 5 THEN 4 WHEN frequency_12m >= 3 THEN 3
                WHEN frequency_12m = 2 THEN 2 WHEN frequency_12m = 1 THEN 1 ELSE 0 END             AS f,
           CASE WHEN frequency_12m = 0 THEN 0 WHEN monetary_12m_cu >= 400 THEN 5 WHEN monetary_12m_cu >= 200 THEN 4
                WHEN monetary_12m_cu >= 100 THEN 3 WHEN monetary_12m_cu >= 50 THEN 2 ELSE 1 END    AS m
    FROM rfm
),

-- 4. segments, first matching rule wins
segmented AS (
    SELECT *,
           CASE WHEN recency_days >= 365                 THEN 'Lost'
                WHEN tenure_days < 90                    THEN 'New Customers'
                WHEN r >= 4 AND f >= 4 AND m >= 4        THEN 'Champions'
                WHEN r >= 4 AND f >= 4                   THEN 'Loyal'
                WHEN r = 3  AND f >= 4                   THEN 'Slipping Regulars'
                WHEN r >= 4                              THEN 'Potential Loyalists'
                WHEN r = 3                               THEN 'Needs Attention'
                WHEN f >= 3 OR m >= 4                    THEN 'At Risk'
                ELSE 'Hibernating' END                   AS segment
    FROM scored
)

SELECT segment,
       COUNT(*)                                                           AS customers,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1)                  AS pct_customers,
       ROUND(SUM(monetary_12m_cu), 0)                                      AS revenue_12m_cu,
       ROUND(100.0 * SUM(monetary_12m_cu) / SUM(SUM(monetary_12m_cu)) OVER (), 1) AS pct_revenue_12m
FROM segmented
GROUP BY segment
ORDER BY revenue_12m_cu DESC;
