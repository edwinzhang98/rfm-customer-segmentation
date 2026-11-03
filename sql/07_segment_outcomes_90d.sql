/* =============================================================================
   07_segment_outcomes_90d.sql  -  next-90-day behaviour by segment (backtests)
   -----------------------------------------------------------------------------
   Input   : data/marts/customer_outcomes_90d.parquet
   Output  : data/marts/segment_outcomes_90d.parquet
             grain: one row per backtest snapshot x segment
   Columns : repurchase_rate          share of customers with >= 1 order in the 90 days
             revenue_per_customer_cu  average 90-day revenue over all customers
             revenue_per_buyer_cu     average 90-day revenue over customers who bought
             run_rate_per_customer_cu trailing-12-month spend x 90/365
             realisation_ratio        actual 90-day revenue / run-rate revenue
                                      (1.0 = kept their usual pace; 0.3 = spent 30% of it)
             sd_revenue_per_customer_cu   used for holdout power on revenue
   Run     : python scripts/run_sql.py sql/07_segment_outcomes_90d.sql
   ============================================================================= */

COPY (
    SELECT
        snapshot_name,
        snapshot_date,
        segment,
        COUNT(*)                                                    AS customers,
        SUM(purchased_next_90d::INT)                                AS buyers,
        AVG(purchased_next_90d::INT)                                AS repurchase_rate,
        SUM(revenue_next_90d_cents) / 100.0                         AS revenue_next_90d_cu,
        SUM(run_rate_90d_cents) / 100.0                             AS run_rate_90d_cu,
        AVG(revenue_next_90d_cents) / 100.0                         AS revenue_per_customer_cu,
        SUM(revenue_next_90d_cents) / NULLIF(SUM(purchased_next_90d::INT), 0) / 100.0
                                                                    AS revenue_per_buyer_cu,
        AVG(run_rate_90d_cents) / 100.0                             AS run_rate_per_customer_cu,
        SUM(revenue_next_90d_cents) / NULLIF(SUM(run_rate_90d_cents), 0)
                                                                    AS realisation_ratio,
        STDDEV_SAMP(revenue_next_90d_cents) / 100.0                 AS sd_revenue_per_customer_cu,
        SUM(orders_next_90d) / NULLIF(SUM(purchased_next_90d::INT), 0)
                                                                    AS orders_per_buyer,
        AVG(is_newsletter_subscriber::INT)                          AS newsletter_share,
        AVG(CASE WHEN is_newsletter_subscriber THEN purchased_next_90d::INT END)
                                                                    AS repurchase_rate_subscribers
    FROM 'data/marts/customer_outcomes_90d.parquet'
    GROUP BY snapshot_name, snapshot_date, segment
    ORDER BY snapshot_name, segment
) TO 'data/marts/segment_outcomes_90d.parquet' (FORMAT parquet);

SELECT snapshot_name, segment, customers, ROUND(repurchase_rate, 3) AS repurchase_rate,
       ROUND(realisation_ratio, 3) AS realisation_ratio
FROM 'data/marts/segment_outcomes_90d.parquet'
ORDER BY snapshot_name, repurchase_rate DESC;
