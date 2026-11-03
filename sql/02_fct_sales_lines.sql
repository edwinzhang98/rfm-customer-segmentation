/* =============================================================================
   02_fct_sales_lines.sql  -  clean line-level sales fact
   -----------------------------------------------------------------------------
   Input   : data/staged/stg_transactions.parquet
   Output  : data/marts/fct_sales_lines.parquet
             grain: one row per customer x date x channel x article x unit price
   Logic   : 1. The source has no quantity column: identical rows are extra units of
                the same item (e.g. two identical T-shirts), so they are collapsed into
                `units` instead of being deleted. Deleting them would drop 9.4% of
                units and revenue.
             2. Money: price x 590 lands exactly on retail price points (9.99, 19.99,
                ...), so every price is stored as integer cents of CU (currency units).
                Integer cents keep every total exact and every rerun identical.
             3. Price outliers are kept (they are real paid amounts) but flagged:
                is_low_price (< 0.50 CU) and the ratio to the article's median price.
   Params  : price_scale (default 590)
   Run     : python scripts/run_sql.py sql/02_fct_sales_lines.sql
   ============================================================================= */

SET VARIABLE price_scale = COALESCE(getvariable('price_scale'), 590);

COPY (
    WITH rows_in_cents AS (
        SELECT
            t_dat                                                              AS order_date,
            customer_id,
            article_id,
            sales_channel_id,
            CAST(ROUND(price * getvariable('price_scale') * 100) AS BIGINT)    AS unit_price_cents
        FROM 'data/staged/stg_transactions.parquet'
    ),
    article_median AS (
        SELECT article_id, MEDIAN(unit_price_cents) AS article_median_price_cents
        FROM rows_in_cents
        GROUP BY 1
    ),
    lines AS (
        SELECT
            order_date,
            customer_id,
            article_id,
            sales_channel_id,
            unit_price_cents,
            COUNT(*)                    AS units
        FROM rows_in_cents
        GROUP BY ALL
    )
    SELECT
        l.order_date,
        l.customer_id,
        l.article_id,
        l.sales_channel_id,
        l.unit_price_cents,
        l.units,
        l.units * l.unit_price_cents                                       AS line_revenue_cents,
        ROUND(l.unit_price_cents / m.article_median_price_cents, 3)        AS price_ratio_to_article_median,
        l.unit_price_cents < 50                                            AS is_low_price
    FROM lines l
    JOIN article_median m USING (article_id)
    ORDER BY l.customer_id, l.order_date
) TO 'data/marts/fct_sales_lines.parquet' (FORMAT parquet, COMPRESSION zstd);

SELECT COUNT(*) AS line_count, SUM(units) AS unit_count, SUM(line_revenue_cents) AS revenue_cents
FROM 'data/marts/fct_sales_lines.parquet';
