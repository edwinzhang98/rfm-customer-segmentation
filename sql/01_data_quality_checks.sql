/* =============================================================================
   01_data_quality_checks.sql  -  sanity checks on the staged raw data
   -----------------------------------------------------------------------------
   Inputs  : data/staged/stg_transactions.parquet
             data/staged/stg_customers.parquet
             data/staged/stg_articles.parquet
   Output  : data/marts/dq_checks.parquet
             one row per check: check_id, area, check_name, observed, expectation,
             status (PASS / FLAG = known issue, handled / FAIL = blocks the pipeline),
             handling (what we do about it)
   Notes   : "Known" row counts come from the Kaggle competition data page
             (H&M Personalized Fashion Recommendations, 2022).
             Pipeline-level reconciliation (rows -> lines -> orders -> customers ->
             segments) is in 13_reconciliation_checks.sql.
   Params  : price_scale (default 590), exclusion thresholds (defaults = config.yaml)
   Run     : python scripts/run_sql.py sql/01_data_quality_checks.sql
   ============================================================================= */

SET VARIABLE price_scale                  = COALESCE(getvariable('price_scale'), 590);
SET VARIABLE excl_units_same_article      = COALESCE(getvariable('excl_units_same_article'), 20);
SET VARIABLE excl_units_per_order         = COALESCE(getvariable('excl_units_per_order'), 100);
SET VARIABLE excl_purchase_days           = COALESCE(getvariable('excl_purchase_days'), 150);

COPY (
WITH
t AS (SELECT * FROM 'data/staged/stg_transactions.parquet'),
c AS (SELECT * FROM 'data/staged/stg_customers.parquet'),
a AS (SELECT * FROM 'data/staged/stg_articles.parquet'),

t_stats AS MATERIALIZED (
    SELECT
        COUNT(*)                                                    AS n_rows,
        COUNT(DISTINCT customer_id)                                 AS n_customers,
        COUNT(DISTINCT article_id)                                  AS n_articles,
        MIN(t_dat)                                                  AS min_date,
        MAX(t_dat)                                                  AS max_date,
        SUM(CASE WHEN t_dat IS NULL OR customer_id IS NULL OR article_id IS NULL
                   OR price IS NULL OR sales_channel_id IS NULL THEN 1 ELSE 0 END) AS n_null_rows,
        SUM(CASE WHEN sales_channel_id NOT IN (1, 2) THEN 1 ELSE 0 END) AS n_bad_channel,
        MIN(price)                                                  AS min_price,
        MAX(price * getvariable('price_scale'))                     AS max_price_cu,
        MAX(ABS(price * getvariable('price_scale') * 100
                - ROUND(price * getvariable('price_scale') * 100))) AS max_cent_deviation,
        SUM(CASE WHEN price * getvariable('price_scale') < 0.5 THEN 1 ELSE 0 END) AS n_low_price_rows,
        SUM(price)                                                  AS total_price
    FROM t
),
dup AS MATERIALIZED (
    SELECT SUM(n) - COUNT(*) AS extra_identical_rows, MAX(n) AS max_identical_rows
    FROM (SELECT t_dat, customer_id, article_id, price, sales_channel_id, COUNT(*) AS n
          FROM t GROUP BY ALL)
),
art_median AS (
    SELECT article_id, MEDIAN(price) AS med_price FROM t GROUP BY 1
),
rel_price AS MATERIALIZED (
    SELECT
        SUM(CASE WHEN t.price < 0.2 * m.med_price THEN 1 ELSE 0 END)         AS n_below_20pct,
        SUM(CASE WHEN t.price < 0.2 * m.med_price THEN t.price ELSE 0 END)   AS rev_below_20pct,
        SUM(CASE WHEN t.price > 3 * m.med_price THEN 1 ELSE 0 END)           AS n_above_3x,
        SUM(CASE WHEN t.price > 3 * m.med_price THEN t.price ELSE 0 END)     AS rev_above_3x
    FROM t JOIN art_median m USING (article_id)
),
days AS (
    SELECT
        d::DATE AS dt
    FROM (SELECT UNNEST(generate_series(MIN(t_dat), MAX(t_dat), INTERVAL 1 DAY)) AS d FROM t)
),
daily AS (
    SELECT t_dat, COUNT(*) AS n_rows, SUM(CASE WHEN sales_channel_id = 1 THEN 1 ELSE 0 END) AS n_store
    FROM t GROUP BY 1
),
calendar AS MATERIALIZED (
    SELECT
        SUM(CASE WHEN daily.t_dat IS NULL THEN 1 ELSE 0 END)              AS n_days_without_sales,
        SUM(CASE WHEN COALESCE(daily.n_store, 0) = 0 THEN 1 ELSE 0 END)   AS n_days_without_store_sales,
        MIN(CASE WHEN COALESCE(daily.n_store, 0) = 0 THEN days.dt END)    AS first_day_without_store,
        MAX(CASE WHEN COALESCE(daily.n_store, 0) = 0 THEN days.dt END)    AS last_day_without_store,
        SUM(CASE WHEN days.dt BETWEEN DATE '2020-03-20' AND DATE '2020-05-05'
                 THEN COALESCE(daily.n_store, 0) ELSE 0 END)              AS store_rows_in_closure
    FROM days LEFT JOIN daily ON daily.t_dat = days.dt
),
c_stats AS MATERIALIZED (
    SELECT
        COUNT(*)                                                    AS n_rows,
        COUNT(DISTINCT customer_id)                                 AS n_distinct,
        SUM(CASE WHEN age IS NULL THEN 1 ELSE 0 END)                AS n_age_null,
        MIN(age)                                                    AS min_age,
        MAX(age)                                                    AS max_age,
        SUM(CASE WHEN club_member_status IS NULL THEN 1 ELSE 0 END) AS n_club_null,
        SUM(CASE WHEN fashion_news_frequency IS NULL THEN 1 ELSE 0 END) AS n_news_null
    FROM c
),
postal AS MATERIALIZED (
    SELECT MAX(n) AS top_postal_code_customers
    FROM (SELECT postal_code, COUNT(*) AS n FROM c GROUP BY 1)
),
a_stats AS MATERIALIZED (
    SELECT COUNT(*) AS n_rows, COUNT(DISTINCT article_id) AS n_distinct FROM a
),
txn_customers AS MATERIALIZED (SELECT DISTINCT customer_id FROM t),
txn_articles  AS MATERIALIZED (SELECT DISTINCT article_id  FROM t),
ref AS MATERIALIZED (
    SELECT
        (SELECT COUNT(*) FROM txn_customers ANTI JOIN c USING (customer_id))  AS txn_customers_missing,
        (SELECT COUNT(*) FROM txn_articles  ANTI JOIN a USING (article_id))   AS txn_articles_missing,
        (SELECT COUNT(*) FROM c ANTI JOIN txn_customers USING (customer_id))  AS customers_without_txn
),
extreme AS MATERIALIZED (
    WITH lines AS (
        SELECT customer_id, t_dat, sales_channel_id, article_id, COUNT(*) AS units
        FROM t GROUP BY ALL
    ),
    orders AS (
        SELECT customer_id, t_dat, sales_channel_id, SUM(units) AS units, MAX(units) AS max_same_article
        FROM lines GROUP BY ALL
    ),
    per_customer AS (
        SELECT customer_id,
               MAX(max_same_article)     AS max_same_article,
               MAX(units)                AS max_units_order,
               COUNT(DISTINCT t_dat)     AS purchase_days
        FROM orders GROUP BY 1
    ),
    flagged AS (
        SELECT customer_id FROM per_customer
        WHERE max_same_article >= getvariable('excl_units_same_article')
           OR max_units_order  >= getvariable('excl_units_per_order')
           OR purchase_days    >= getvariable('excl_purchase_days')
    )
    SELECT
        (SELECT COUNT(*) FROM flagged)                                              AS n_flagged,
        (SELECT SUM(t.price) FROM t SEMI JOIN flagged USING (customer_id))      AS flagged_price
)

-- status: PASS = as expected | FLAG = known issue, handled as described | FAIL = blocks the pipeline
SELECT * FROM (
    SELECT 1 AS check_id, 'Row counts' AS area, 'transactions rows match the published count' AS check_name,
           format('{:,}', n_rows) AS observed, '31,788,324' AS expectation,
           CASE WHEN n_rows = 31788324 THEN 'PASS' ELSE 'FAIL' END AS status,
           '-' AS handling
    FROM t_stats
    UNION ALL
    SELECT 2, 'Row counts', 'customers rows match the published count',
           format('{:,}', n_rows), '1,371,980', CASE WHEN n_rows = 1371980 THEN 'PASS' ELSE 'FAIL' END, '-' FROM c_stats
    UNION ALL
    SELECT 3, 'Row counts', 'articles rows match the published count',
           format('{:,}', n_rows), '105,542', CASE WHEN n_rows = 105542 THEN 'PASS' ELSE 'FAIL' END, '-' FROM a_stats
    UNION ALL
    SELECT 4, 'Keys', 'customer_id is unique in customers',
           format('{:,} distinct / {:,} rows', n_distinct, n_rows), 'distinct = rows',
           CASE WHEN n_distinct = n_rows THEN 'PASS' ELSE 'FAIL' END, '-' FROM c_stats
    UNION ALL
    SELECT 5, 'Keys', 'article_id is unique in articles',
           format('{:,} distinct / {:,} rows', n_distinct, n_rows), 'distinct = rows',
           CASE WHEN n_distinct = n_rows THEN 'PASS' ELSE 'FAIL' END, '-' FROM a_stats
    UNION ALL
    SELECT 6, 'Keys', 'identical repeated transaction rows (no row key, no quantity column)',
           format('{:,} extra rows ({:.2f}%), max {} identical rows', extra_identical_rows,
                  100.0 * extra_identical_rows / n_rows, max_identical_rows),
           'repeats are extra units, not errors',
           CASE WHEN extra_identical_rows = 0 THEN 'PASS' ELSE 'FLAG' END,
           'kept: each repeat = one more unit of the same item; collapsed into a units column in fct_sales_lines'
    FROM dup CROSS JOIN t_stats
    UNION ALL
    SELECT 7, 'Referential integrity', 'every transaction customer exists in customers',
           format('{:,} missing', txn_customers_missing), '0',
           CASE WHEN txn_customers_missing = 0 THEN 'PASS' ELSE 'FAIL' END, '-' FROM ref
    UNION ALL
    SELECT 8, 'Referential integrity', 'every transaction article exists in articles',
           format('{:,} missing', txn_articles_missing), '0',
           CASE WHEN txn_articles_missing = 0 THEN 'PASS' ELSE 'FAIL' END, '-' FROM ref
    UNION ALL
    SELECT 9, 'Referential integrity', 'customers with no transaction in the two-year window',
           format('{:,}', customers_without_txn), 'informational',
           CASE WHEN customers_without_txn = 0 THEN 'PASS' ELSE 'FLAG' END,
           'outside the RFM universe (nothing to score); listed in the segmentation spec so totals reconcile'
    FROM ref
    UNION ALL
    SELECT 10, 'Nulls', 'transactions: rows with any null field',
           format('{:,}', n_null_rows), '0', CASE WHEN n_null_rows = 0 THEN 'PASS' ELSE 'FAIL' END, '-' FROM t_stats
    UNION ALL
    SELECT 11, 'Nulls', 'customers: missing age / club status / newsletter field',
           format('age {:,}; club status {:,}; newsletter {:,}', n_age_null, n_club_null, n_news_null),
           'small share (< 2% each)',
           CASE WHEN n_age_null + n_club_null + n_news_null = 0 THEN 'PASS'
                WHEN GREATEST(n_age_null, n_club_null, n_news_null) < 0.02 * n_rows THEN 'FLAG' ELSE 'FAIL' END,
           'age -> "Unknown" band; club status -> UNKNOWN; newsletter missing -> not subscribed'
    FROM c_stats
    UNION ALL
    SELECT 12, 'Time range', 'first and last transaction date',
           format('{} to {}', min_date, max_date), '2018-09-20 to 2020-09-22',
           CASE WHEN min_date = DATE '2018-09-20' AND max_date = DATE '2020-09-22' THEN 'PASS' ELSE 'FAIL' END,
           'snapshot (Recency base date) = last date 2020-09-22'
    FROM t_stats
    UNION ALL
    SELECT 13, 'Time range', 'calendar days with no transactions at all',
           format('{:,}', n_days_without_sales), '0',
           CASE WHEN n_days_without_sales = 0 THEN 'PASS' ELSE 'FAIL' END, '-' FROM calendar
    UNION ALL
    SELECT 14, 'Channel', 'sales_channel_id only takes values 1 and 2',
           format('{:,} other values', n_bad_channel), '0',
           CASE WHEN n_bad_channel = 0 THEN 'PASS' ELSE 'FAIL' END, '-' FROM t_stats
    UNION ALL
    SELECT 15, 'Channel', 'channel 1 disappears during the spring-2020 COVID store closures',
           format('{} days without channel-1 sales, {} to {}; {} channel-1 rows in that period',
                  n_days_without_store_sales, first_day_without_store, last_day_without_store, store_rows_in_closure),
           'if 1 = store, channel 1 drops to ~0 in spring 2020',
           CASE WHEN store_rows_in_closure < 100 THEN 'PASS' ELSE 'FAIL' END,
           'confirms the encoding 1 = store, 2 = online'
    FROM calendar
    UNION ALL
    SELECT 16, 'Price', 'all prices are positive',
           format('min price {:.8f}', min_price), '> 0', CASE WHEN min_price > 0 THEN 'PASS' ELSE 'FAIL' END, '-' FROM t_stats
    UNION ALL
    SELECT 17, 'Price', 'price x 590 lands on whole cents (scaled retail price)',
           format('max deviation from a whole cent: {:.2e}', max_cent_deviation), '< 1e-6',
           CASE WHEN max_cent_deviation < 1e-6 THEN 'PASS' ELSE 'FAIL' END,
           'money reported in CU = price x 590, stored as integer cents (exact, reproducible totals)'
    FROM t_stats
    UNION ALL
    SELECT 18, 'Price', 'highest item price is plausible',
           format('{:.2f} CU', max_price_cu), '< 500 CU (outerwear range)',
           CASE WHEN max_price_cu < 500 THEN 'PASS' ELSE 'FLAG' END, '-' FROM t_stats
    UNION ALL
    SELECT 19, 'Price', 'rows priced below 0.50 CU',
           format('{:,} rows ({:.3f}%)', n_low_price_rows, 100.0 * n_low_price_rows / n_rows), '< 0.1% of rows',
           CASE WHEN n_low_price_rows = 0 THEN 'PASS' WHEN n_low_price_rows < 0.001 * n_rows THEN 'FLAG' ELSE 'FAIL' END,
           'kept and flagged (is_low_price); ~0% of revenue; scores use thresholds, so a few cents cannot move a segment'
    FROM t_stats
    UNION ALL
    SELECT 20, 'Price', 'rows priced < 20% or > 3x the article median price',
           format('< 20% of median: {:,} rows ({:.3f}% of revenue); > 3x median: {:,} rows ({:.3f}% of revenue)',
                  n_below_20pct, 100 * rev_below_20pct / total_price,
                  n_above_3x, 100 * rev_above_3x / total_price),
           '< 1% of revenue',
           CASE WHEN n_below_20pct + n_above_3x = 0 THEN 'PASS'
                WHEN (rev_below_20pct + rev_above_3x) < 0.01 * total_price THEN 'FLAG' ELSE 'FAIL' END,
           'kept (markdowns and price changes are real revenue); ratio stored per line for audit'
    FROM rel_price CROSS JOIN t_stats
    UNION ALL
    SELECT 21, 'Customers', 'age within a plausible range',
           format('{} to {}', min_age, max_age), '16 to 100',
           CASE WHEN min_age >= 16 AND max_age <= 100 THEN 'PASS' ELSE 'FLAG' END, '-' FROM c_stats
    UNION ALL
    SELECT 22, 'Customers', 'most common postal code',
           format('{:,} customers share one postal code ({:.1f}%)', top_postal_code_customers,
                  100.0 * top_postal_code_customers / n_rows),
           'no single code > 1% of customers',
           CASE WHEN top_postal_code_customers < 0.01 * n_rows THEN 'PASS' ELSE 'FLAG' END,
           'looks like a default / placeholder value; postal code is not used in this analysis'
    FROM postal CROSS JOIN c_stats
    UNION ALL
    SELECT 23, 'Extreme customers', 'bulk or near-daily buyers (Review List rule in 02_metric_definitions.md)',
           format('{:,} customers ({:.3f}%), {:.2f}% of revenue', n_flagged,
                  100.0 * n_flagged / n_customers,
                  100.0 * flagged_price / total_price),
           '< 0.1% of customers',
           CASE WHEN n_flagged = 0 THEN 'PASS' WHEN n_flagged < 0.001 * n_customers THEN 'FLAG' ELSE 'FAIL' END,
           'kept in totals; segment = Review List: no offers or paid media until reviewed by CRM / retail ops'
    FROM extreme CROSS JOIN t_stats
)
ORDER BY check_id
) TO 'data/marts/dq_checks.parquet' (FORMAT parquet);

SELECT check_id, check_name, status, observed FROM 'data/marts/dq_checks.parquet' ORDER BY check_id;
