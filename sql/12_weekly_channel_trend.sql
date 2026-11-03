/* =============================================================================
   12_weekly_channel_trend.sql  -  weekly orders, customers and revenue by channel
   -----------------------------------------------------------------------------
   Input   : data/marts/fct_orders.parquet
   Output  : data/marts/weekly_channel_trend.parquet
             grain: week (Monday start) x channel
   Purpose : (1) sanity check: channel 1 should collapse during the spring-2020
             store closures if 1 = store; (2) context for the overview page.
             The first week (data starts Thu 2018-09-20) and the last week (data ends
             Tue 2020-09-22) are partial and flagged so charts can drop them.
   Run     : python scripts/run_sql.py sql/12_weekly_channel_trend.sql
   ============================================================================= */

COPY (
    WITH
    bounds AS (
        SELECT MIN(order_date) AS first_day, MAX(order_date) AS last_day
        FROM 'data/marts/fct_orders.parquet'
    ),
    weekly AS (
        SELECT
            DATE_TRUNC('week', order_date)::DATE  AS week_start,
            channel,
            COUNT(*)                              AS orders,
            COUNT(DISTINCT customer_id)           AS customers,
            SUM(n_units)                          AS units,
            SUM(revenue_cents) / 100.0            AS revenue_cu
        FROM 'data/marts/fct_orders.parquet'
        GROUP BY ALL
    )
    SELECT
        w.*,
        (w.week_start < b.first_day OR w.week_start + 6 > b.last_day) AS is_partial_week
    FROM weekly w
    CROSS JOIN bounds b
    ORDER BY w.week_start, w.channel
) TO 'data/marts/weekly_channel_trend.parquet' (FORMAT parquet);

SELECT channel, COUNT(*) AS weeks, SUM(orders) AS orders, SUM(is_partial_week::INT) AS partial_weeks
FROM 'data/marts/weekly_channel_trend.parquet' GROUP BY 1 ORDER BY 1;
