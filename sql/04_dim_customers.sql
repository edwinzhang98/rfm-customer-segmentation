/* =============================================================================
   04_dim_customers.sql  -  customer dimension with order history and flags
   -----------------------------------------------------------------------------
   Inputs  : data/staged/stg_customers.parquet
             data/marts/fct_orders.parquet
             data/marts/fct_sales_lines.parquet
   Output  : data/marts/dim_customers.parquet   grain: one row per customer (1,371,980)
   Columns : attributes (age band, club status, newsletter subscription),
             two-year order history (first / last order, orders, revenue, channel use),
             channel_profile  = Online only / Store only / Omnichannel over the full window,
             is_excluded      = suspected staff / reseller account (not a normal consumer):
                                >= 20 units of one article in one order, OR
                                >= 100 units in one order, OR
                                purchases on >= 150 different days in two years.
   Notes   : Newsletter subscribers (fashion_news_frequency = Regularly / Monthly) are
             treated as email-reachable; everyone else is not.
   Params  : excl_units_same_article (20), excl_units_per_order (100), excl_purchase_days (150)
   Run     : python scripts/run_sql.py sql/04_dim_customers.sql
   ============================================================================= */

SET VARIABLE excl_units_same_article = COALESCE(getvariable('excl_units_same_article'), 20);
SET VARIABLE excl_units_per_order    = COALESCE(getvariable('excl_units_per_order'), 100);
SET VARIABLE excl_purchase_days      = COALESCE(getvariable('excl_purchase_days'), 150);

COPY (
    WITH
    c AS (SELECT * FROM 'data/staged/stg_customers.parquet'),
    o AS (SELECT * FROM 'data/marts/fct_orders.parquet'),
    max_line AS (   -- most units of one article in one order (a line can split by price)
        SELECT customer_id, MAX(units) AS max_units_same_article
        FROM (
            SELECT customer_id, order_date, sales_channel_id, article_id, SUM(units) AS units
            FROM 'data/marts/fct_sales_lines.parquet'
            GROUP BY ALL
        )
        GROUP BY 1
    ),
    history AS (
        SELECT
            customer_id,
            MIN(order_date)                                   AS first_order_date,
            MAX(order_date)                                   AS last_order_date,
            COUNT(*)                                          AS lifetime_orders,
            COUNT(DISTINCT order_date)                        AS lifetime_purchase_days,
            SUM(n_units)                                      AS lifetime_units,
            SUM(revenue_cents)                                AS lifetime_revenue_cents,
            COUNT(*) FILTER (WHERE sales_channel_id = 1)      AS lifetime_store_orders,
            COUNT(*) FILTER (WHERE sales_channel_id = 2)      AS lifetime_online_orders,
            COALESCE(SUM(revenue_cents) FILTER (WHERE sales_channel_id = 2), 0) AS lifetime_online_revenue_cents,
            MAX(n_units)                                      AS max_units_per_order
        FROM o
        GROUP BY 1
    ),
    first_channel AS (
        SELECT
            o.customer_id,
            CASE WHEN COUNT(DISTINCT o.sales_channel_id) = 2 THEN 'Both'
                 WHEN MIN(o.sales_channel_id) = 1           THEN 'Store'
                 ELSE 'Online' END                            AS first_order_channel
        FROM o
        JOIN history h ON h.customer_id = o.customer_id AND o.order_date = h.first_order_date
        GROUP BY 1
    )
    SELECT
        c.customer_id,
        c.age,
        CASE WHEN c.age IS NULL THEN 'Unknown'
             WHEN c.age < 25 THEN '16-24'
             WHEN c.age < 35 THEN '25-34'
             WHEN c.age < 45 THEN '35-44'
             WHEN c.age < 55 THEN '45-54'
             WHEN c.age < 65 THEN '55-64'
             ELSE '65+' END                                               AS age_band,
        COALESCE(c.club_member_status, 'UNKNOWN')                         AS club_member_status,
        CASE WHEN c.fashion_news_frequency IN ('Regularly', 'Monthly')
             THEN c.fashion_news_frequency ELSE 'None' END                AS newsletter_frequency,
        COALESCE(c.fashion_news_frequency IN ('Regularly', 'Monthly'), FALSE) AS is_newsletter_subscriber,
        h.customer_id IS NOT NULL                                         AS has_orders,
        h.first_order_date,
        h.last_order_date,
        f.first_order_channel,
        COALESCE(h.lifetime_orders, 0)                                    AS lifetime_orders,
        COALESCE(h.lifetime_purchase_days, 0)                             AS lifetime_purchase_days,
        COALESCE(h.lifetime_units, 0)                                     AS lifetime_units,
        COALESCE(h.lifetime_revenue_cents, 0)                             AS lifetime_revenue_cents,
        COALESCE(h.lifetime_store_orders, 0)                              AS lifetime_store_orders,
        COALESCE(h.lifetime_online_orders, 0)                             AS lifetime_online_orders,
        COALESCE(h.lifetime_online_revenue_cents, 0)                      AS lifetime_online_revenue_cents,
        CASE WHEN h.customer_id IS NULL           THEN 'No orders'
             WHEN h.lifetime_store_orders = 0     THEN 'Online only'
             WHEN h.lifetime_online_orders = 0    THEN 'Store only'
             ELSE 'Omnichannel' END                                       AS channel_profile,
        COALESCE(m.max_units_same_article, 0)                             AS max_units_same_article,
        COALESCE(h.max_units_per_order, 0)                                AS max_units_per_order,
        COALESCE(m.max_units_same_article >= getvariable('excl_units_same_article'), FALSE) AS flag_bulk_same_article,
        COALESCE(h.max_units_per_order    >= getvariable('excl_units_per_order'), FALSE)    AS flag_bulk_order,
        COALESCE(h.lifetime_purchase_days >= getvariable('excl_purchase_days'), FALSE)      AS flag_very_frequent,
        COALESCE(m.max_units_same_article >= getvariable('excl_units_same_article')
              OR h.max_units_per_order    >= getvariable('excl_units_per_order')
              OR h.lifetime_purchase_days >= getvariable('excl_purchase_days'), FALSE)      AS is_excluded
    FROM c
    LEFT JOIN history       h USING (customer_id)
    LEFT JOIN first_channel f USING (customer_id)
    LEFT JOIN max_line      m USING (customer_id)
    ORDER BY c.customer_id
) TO 'data/marts/dim_customers.parquet' (FORMAT parquet, COMPRESSION zstd);

SELECT
    COUNT(*)                                     AS customers,
    SUM(has_orders::INT)                         AS customers_with_orders,
    SUM(is_excluded::INT)                        AS excluded_customers,
    SUM(is_newsletter_subscriber::INT)           AS newsletter_subscribers
FROM 'data/marts/dim_customers.parquet';
