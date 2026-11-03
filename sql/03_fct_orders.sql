/* =============================================================================
   03_fct_orders.sql  -  order (basket) fact
   -----------------------------------------------------------------------------
   Input   : data/marts/fct_sales_lines.parquet
   Output  : data/marts/fct_orders.parquet
             grain: one row per customer x date x channel  (= one "order")
   Logic   : The data has no order id. We define an order as everything a customer
             bought on one day in one channel. A store visit and an online order on
             the same day are two orders (happens on ~1% of customer-days).
             Several online orders placed on the same day collapse into one order:
             a known limitation, documented in docs/02_metric_definitions.md.
   Run     : python scripts/run_sql.py sql/03_fct_orders.sql
   ============================================================================= */

COPY (
    SELECT
        customer_id,
        order_date,
        sales_channel_id,
        CASE sales_channel_id WHEN 1 THEN 'Store' WHEN 2 THEN 'Online' END AS channel,
        COUNT(*)                    AS n_lines,
        SUM(units)                  AS n_units,
        SUM(line_revenue_cents)     AS revenue_cents
    FROM 'data/marts/fct_sales_lines.parquet'
    GROUP BY customer_id, order_date, sales_channel_id
    ORDER BY customer_id, order_date, sales_channel_id
) TO 'data/marts/fct_orders.parquet' (FORMAT parquet, COMPRESSION zstd);

SELECT COUNT(*) AS order_count, SUM(n_units) AS unit_count, SUM(revenue_cents) AS revenue_cents
FROM 'data/marts/fct_orders.parquet';
