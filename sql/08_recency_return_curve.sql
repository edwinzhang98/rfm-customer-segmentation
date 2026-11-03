/* =============================================================================
   08_recency_return_curve.sql  -  chance of buying again within 90 days, by recency
   -----------------------------------------------------------------------------
   Input   : data/marts/customer_outcomes_90d.parquet
   Output  : data/marts/recency_return_curve.parquet
             grain: backtest snapshot x 15-day recency bucket x frequency group
   Purpose : Evidence for the recency thresholds. If the share of customers who come
             back within 90 days falls steadily with days since last order, the R-score
             cut-offs (30 / 60 / 120 / 180 / 365 days) should sit where the curve is
             still meaningfully above the "lapsed" level.
   Groups  : frequency_group = '1 order' / '2+ orders' (in the 12 months before the
             snapshot) / 'No order in 12 months' (lapsed)
   Run     : python scripts/run_sql.py sql/08_recency_return_curve.sql
   ============================================================================= */

COPY (
    WITH bucketed AS (
        SELECT
            snapshot_name,
            snapshot_date,
            LEAST(FLOOR(recency_days / 15) * 15, 720)::INTEGER                  AS recency_bucket_start,
            CASE WHEN frequency_12m = 0 THEN 'No order in 12 months'
                 WHEN frequency_12m = 1 THEN '1 order'
                 ELSE '2+ orders' END                                          AS frequency_group,
            purchased_next_90d,
            revenue_next_90d_cents
        FROM 'data/marts/customer_outcomes_90d.parquet'
        WHERE segment <> 'Review List'
    )
    SELECT
        snapshot_name,
        snapshot_date,
        recency_bucket_start,
        recency_bucket_start + 14                         AS recency_bucket_end,
        frequency_group,
        COUNT(*)                                          AS customers,
        SUM(purchased_next_90d::INT)                      AS buyers,
        AVG(purchased_next_90d::INT)                      AS return_rate_90d,
        AVG(revenue_next_90d_cents) / 100.0               AS revenue_per_customer_cu
    FROM bucketed
    GROUP BY ALL
    ORDER BY snapshot_name, frequency_group, recency_bucket_start
) TO 'data/marts/recency_return_curve.parquet' (FORMAT parquet);

SELECT snapshot_name, frequency_group, COUNT(*) AS buckets, SUM(customers) AS customers
FROM 'data/marts/recency_return_curve.parquet'
GROUP BY ALL ORDER BY ALL;
