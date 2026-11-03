/* =============================================================================
   13_reconciliation_checks.sql  -  do the numbers add up across every table?
   -----------------------------------------------------------------------------
   Inputs  : data/staged/stg_transactions.parquet, data/staged/stg_customers.parquet,
             data/marts/fct_sales_lines.parquet, data/marts/fct_orders.parquet,
             data/marts/dim_customers.parquet, data/marts/customer_rfm.parquet,
             data/marts/segment_profile.parquet, data/marts/customer_outcomes_90d.parquet
   Output  : data/marts/reconciliation_checks.parquet
             one row per check: check_name, left_value, right_value, difference, passed
   Logic   : units, revenue (integer cents, so equality is exact), customers and
             orders must be identical at every step from raw rows to segments; segment
             shares must add up to 100%.
   Params  : price_scale (590), lookback_days (365), snapshot_current (2020-09-22)
   Run     : python scripts/run_sql.py sql/13_reconciliation_checks.sql
   ============================================================================= */

SET VARIABLE price_scale      = COALESCE(getvariable('price_scale'), 590);
SET VARIABLE lookback_days    = COALESCE(getvariable('lookback_days'), 365);
SET VARIABLE snapshot_current = COALESCE(getvariable('snapshot_current'), DATE '2020-09-22');

COPY (
    WITH
    stg AS (
        SELECT COUNT(*)                    AS units,
               SUM(CAST(ROUND(price * getvariable('price_scale') * 100) AS BIGINT)) AS revenue_cents,
               COUNT(DISTINCT customer_id) AS customers
        FROM 'data/staged/stg_transactions.parquet'
    ),
    lines AS (SELECT SUM(units) AS units, SUM(line_revenue_cents) AS revenue_cents
              FROM 'data/marts/fct_sales_lines.parquet'),
    ord AS (SELECT SUM(n_units) AS units, SUM(revenue_cents) AS revenue_cents, COUNT(*) AS orders,
                   COUNT(*) FILTER (WHERE getvariable('snapshot_current') - order_date < getvariable('lookback_days')) AS orders_12m,
                   SUM(revenue_cents) FILTER (WHERE getvariable('snapshot_current') - order_date < getvariable('lookback_days')) AS revenue_12m_cents
            FROM 'data/marts/fct_orders.parquet'),
    dim AS (SELECT COUNT(*) AS rows_, SUM(has_orders::INT) AS customers_with_orders,
                   SUM(lifetime_units) AS units, SUM(lifetime_revenue_cents) AS revenue_cents,
                   SUM(lifetime_orders) AS orders
            FROM 'data/marts/dim_customers.parquet'),
    stg_c AS (SELECT COUNT(*) AS rows_ FROM 'data/staged/stg_customers.parquet'),
    rfm AS (SELECT COUNT(*) AS customers, SUM(frequency_12m) AS orders_12m,
                   SUM(monetary_12m_cents) AS revenue_12m_cents,
                   SUM(revenue_to_date_cents) AS revenue_to_date_cents
            FROM 'data/marts/customer_rfm.parquet' WHERE snapshot_name = 'current'),
    prof AS (SELECT SUM(customers) AS customers, SUM(revenue_12m_cu) AS revenue_12m_cu,
                    SUM(revenue_2y_cu) AS revenue_2y_cu,
                    SUM(pct_customers) AS pct_customers, SUM(pct_revenue_12m) AS pct_revenue_12m
             FROM 'data/marts/segment_profile.parquet'),
    bt AS (SELECT
               (SELECT COUNT(*) FROM 'data/marts/customer_rfm.parquet' WHERE snapshot_name LIKE 'backtest%') AS rfm_rows,
               (SELECT COUNT(*) FROM 'data/marts/customer_outcomes_90d.parquet') AS outcome_rows),
    checks AS (
        SELECT 'units: raw rows = sum(units) in fct_sales_lines'            AS check_name, stg.units::DOUBLE AS left_value, lines.units::DOUBLE AS right_value FROM stg, lines
        UNION ALL SELECT 'units: fct_sales_lines = fct_orders',               lines.units, ord.units FROM lines, ord
        UNION ALL SELECT 'units: fct_orders = dim_customers lifetime units',   ord.units, dim.units FROM ord, dim
        UNION ALL SELECT 'revenue (cents): raw = fct_sales_lines',            stg.revenue_cents, lines.revenue_cents FROM stg, lines
        UNION ALL SELECT 'revenue (cents): fct_sales_lines = fct_orders',     lines.revenue_cents, ord.revenue_cents FROM lines, ord
        UNION ALL SELECT 'revenue (cents): fct_orders = dim_customers',       ord.revenue_cents, dim.revenue_cents FROM ord, dim
        UNION ALL SELECT 'revenue (cents): fct_orders = customer_rfm (to date)', ord.revenue_cents, rfm.revenue_to_date_cents FROM ord, rfm
        UNION ALL SELECT 'orders: fct_orders = dim_customers lifetime orders', ord.orders, dim.orders FROM ord, dim
        UNION ALL SELECT 'customers: dim_customers rows = stg_customers rows', dim.rows_, stg_c.rows_ FROM dim, stg_c
        UNION ALL SELECT 'customers: buyers in raw data = dim has_orders',     stg.customers, dim.customers_with_orders FROM stg, dim
        UNION ALL SELECT 'customers: dim has_orders = current RFM rows',       dim.customers_with_orders, rfm.customers FROM dim, rfm
        UNION ALL SELECT 'customers: current RFM rows = sum over segments',    rfm.customers, prof.customers FROM rfm, prof
        UNION ALL SELECT 'orders 12m: fct_orders window = sum(frequency_12m)', ord.orders_12m, rfm.orders_12m FROM ord, rfm
        UNION ALL SELECT 'revenue 12m (cents): fct_orders window = sum(monetary_12m)', ord.revenue_12m_cents, rfm.revenue_12m_cents FROM ord, rfm
        UNION ALL SELECT 'revenue 12m (CU): fct_orders window = sum over segments', ord.revenue_12m_cents / 100.0, prof.revenue_12m_cu FROM ord, prof
        UNION ALL SELECT 'revenue 2y (CU): fct_orders = sum over segments',   ord.revenue_cents / 100.0, prof.revenue_2y_cu FROM ord, prof
        UNION ALL SELECT 'segment shares of customers add to 100%',            1.0, prof.pct_customers FROM prof
        UNION ALL SELECT 'segment shares of 12m revenue add to 100%',          1.0, prof.pct_revenue_12m FROM prof
        UNION ALL SELECT 'backtest: RFM rows = outcome rows',                  bt.rfm_rows, bt.outcome_rows FROM bt
    )
    SELECT
        check_name,
        left_value,
        right_value,
        right_value - left_value                     AS difference,
        ABS(right_value - left_value) < 1e-6 * GREATEST(1, ABS(left_value)) AS passed
    FROM checks
) TO 'data/marts/reconciliation_checks.parquet' (FORMAT parquet);

SELECT check_name, passed FROM 'data/marts/reconciliation_checks.parquet';
