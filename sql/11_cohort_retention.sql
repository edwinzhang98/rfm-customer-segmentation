/* =============================================================================
   11_cohort_retention.sql  -  retention and cumulative revenue by first-purchase month
   -----------------------------------------------------------------------------
   Inputs  : data/marts/dim_customers.parquet
             data/marts/fct_orders.parquet
   Output  : data/marts/cohort_retention.parquet
             grain: cohort_month x first_order_channel x month_number
   Definitions
     cohort_month   month of the customer's first order seen in the data
     month_number   0 = the cohort month itself, 1 = the next calendar month, ...
     active         customer placed >= 1 order in that calendar month
     retention      active customers / cohort size
     observed LTV   cumulative revenue per cohort customer up to month_number
   Caveats (shown next to every cohort chart)
     * Left-censoring: the data starts 2018-09-20, so a "first order" in late 2018 is
       often an existing customer's first order *in the window*, not a new customer.
       The later the cohort, the cleaner it is (a 2019-09 cohort had 12 months with no
       order before joining).
     * The 2018-09 cohort (11 days) and the incomplete month 2020-09 (22 days) are
       dropped; activity is counted up to 2020-08.
     * Suspected staff / reseller accounts are excluded.
   Run     : python scripts/run_sql.py sql/11_cohort_retention.sql
   ============================================================================= */

COPY (
    WITH
    customers AS (
        SELECT
            customer_id,
            DATE_TRUNC('month', first_order_date)::DATE AS cohort_month,
            first_order_channel
        FROM 'data/marts/dim_customers.parquet'
        WHERE has_orders
          AND NOT is_excluded
          AND first_order_date >= DATE '2018-10-01'
          AND first_order_date <  DATE '2020-09-01'
    ),
    monthly AS (
        SELECT
            customer_id,
            DATE_TRUNC('month', order_date)::DATE AS activity_month,
            SUM(revenue_cents)                    AS revenue_cents
        FROM 'data/marts/fct_orders.parquet'
        WHERE order_date < DATE '2020-09-01'
        GROUP BY ALL
    ),
    cohort_size AS (
        SELECT cohort_month, first_order_channel, COUNT(*) AS cohort_customers
        FROM customers
        GROUP BY ALL
    ),
    activity AS (
        SELECT
            c.cohort_month,
            c.first_order_channel,
            DATE_DIFF('month', c.cohort_month, m.activity_month) AS month_number,
            COUNT(DISTINCT m.customer_id)                        AS active_customers,
            SUM(m.revenue_cents)                                 AS revenue_cents
        FROM customers c
        JOIN monthly m USING (customer_id)
        GROUP BY ALL
    )
    SELECT
        a.cohort_month,
        a.first_order_channel,
        a.month_number,
        s.cohort_customers,
        a.active_customers,
        a.revenue_cents / 100.0 AS revenue_cu
    FROM activity a
    JOIN cohort_size s USING (cohort_month, first_order_channel)
    ORDER BY a.cohort_month, a.first_order_channel, a.month_number
) TO 'data/marts/cohort_retention.parquet' (FORMAT parquet);

SELECT COUNT(DISTINCT cohort_month) AS cohorts, MAX(month_number) AS max_month_number,
       SUM(CASE WHEN month_number = 0 THEN active_customers END) AS customers_in_cohorts
FROM 'data/marts/cohort_retention.parquet';
