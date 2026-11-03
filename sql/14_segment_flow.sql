/* =============================================================================
   14_segment_flow.sql  -  how customers moved between segments in one quarter
   -----------------------------------------------------------------------------
   Input   : data/marts/customer_rfm.parquet   (snapshots backtest_recent and current)
   Output  : data/marts/segment_flow.parquet
             grain: segment on 2020-06-24 (from_segment) x segment on 2020-09-22 (to_segment)
   Purpose : Segments are a moving picture. This transition matrix is the monitoring view
             the CRM team re-runs every month: e.g. "what share of last quarter's Champions
             are still Champions" and "how many At Risk customers slipped to Lost before
             we contacted them". Customers with no order before 2020-06-24 appear as
             from_segment = 'Not yet a customer'.
   Run     : python scripts/run_sql.py sql/14_segment_flow.sql
   ============================================================================= */

COPY (
    WITH
    prev AS (
        SELECT customer_id, segment AS from_segment
        FROM 'data/marts/customer_rfm.parquet' WHERE snapshot_name = 'backtest_recent'
    ),
    cur AS (
        SELECT customer_id, segment AS to_segment, monetary_12m_cents
        FROM 'data/marts/customer_rfm.parquet' WHERE snapshot_name = 'current'
    ),
    flows AS (
        SELECT COALESCE(p.from_segment, 'Not yet a customer') AS from_segment,
               c.to_segment,
               COUNT(*)                                       AS customers,
               SUM(c.monetary_12m_cents) / 100.0              AS revenue_12m_cu_now
        FROM cur c
        LEFT JOIN prev p USING (customer_id)
        GROUP BY ALL
    )
    SELECT
        from_segment,
        to_segment,
        customers,
        revenue_12m_cu_now,
        customers / SUM(customers) OVER (PARTITION BY from_segment) AS share_of_from_segment
    FROM flows
    ORDER BY from_segment, customers DESC
) TO 'data/marts/segment_flow.parquet' (FORMAT parquet);

SELECT from_segment, SUM(customers) AS customers,
       ROUND(100 * MAX(CASE WHEN from_segment = to_segment THEN share_of_from_segment END), 1) AS pct_stayed
FROM 'data/marts/segment_flow.parquet'
GROUP BY 1 ORDER BY 2 DESC;
