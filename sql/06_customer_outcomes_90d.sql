/* =============================================================================
   06_customer_outcomes_90d.sql  -  what each customer actually did in the 90 days
                                    after a backtest snapshot
   -----------------------------------------------------------------------------
   Inputs  : data/marts/customer_rfm.parquet   (backtest snapshots only)
             data/marts/fct_orders.parquet
   Output  : data/marts/customer_outcomes_90d.parquet
             grain: one row per backtest snapshot x customer
   Logic   : Outcome window = the 90 days after the snapshot date:
             (snapshot_date, snapshot_date + 90]. No campaign data exists, so this is
             "business as usual" behaviour: the basis for the "if we do nothing"
             estimate and for the holdout power calculation.
             run_rate_90d_cents = what the customer would spend in 90 days at their
             trailing-12-month pace (monetary_12m x 90 / 365).
   Params  : outcome_days (default 90), lookback_days (default 365)
   Run     : python scripts/run_sql.py sql/06_customer_outcomes_90d.sql
   ============================================================================= */

SET VARIABLE outcome_days  = COALESCE(getvariable('outcome_days'), 90);
SET VARIABLE lookback_days = COALESCE(getvariable('lookback_days'), 365);

COPY (
    WITH
    base AS (
        SELECT *
        FROM 'data/marts/customer_rfm.parquet'
        WHERE snapshot_name LIKE 'backtest%'
    ),
    future_orders AS (
        SELECT
            b.snapshot_name,
            b.customer_id,
            COUNT(*)              AS orders_next_90d,
            SUM(o.revenue_cents)  AS revenue_next_90d_cents
        FROM base b
        JOIN 'data/marts/fct_orders.parquet' o
          ON  o.customer_id = b.customer_id
          AND o.order_date >  b.snapshot_date
          AND o.order_date <= b.snapshot_date + CAST(getvariable('outcome_days') AS INTEGER)
        GROUP BY 1, 2
    )
    SELECT
        b.snapshot_name,
        b.snapshot_date,
        b.customer_id,
        b.segment,
        b.r_score,
        b.f_score,
        b.m_score,
        b.recency_days,
        b.frequency_12m,
        b.monetary_12m_cents,
        b.is_newsletter_subscriber,
        b.monetary_12m_cents * getvariable('outcome_days') / getvariable('lookback_days') AS run_rate_90d_cents,
        COALESCE(f.orders_next_90d, 0)          AS orders_next_90d,
        COALESCE(f.revenue_next_90d_cents, 0)   AS revenue_next_90d_cents,
        COALESCE(f.orders_next_90d, 0) > 0      AS purchased_next_90d
    FROM base b
    LEFT JOIN future_orders f USING (snapshot_name, customer_id)
    ORDER BY b.snapshot_name, b.customer_id
) TO 'data/marts/customer_outcomes_90d.parquet' (FORMAT parquet, COMPRESSION zstd);

SELECT snapshot_name, COUNT(*) AS customers, AVG(purchased_next_90d::INT) AS repurchase_rate
FROM 'data/marts/customer_outcomes_90d.parquet'
GROUP BY 1 ORDER BY 1;
