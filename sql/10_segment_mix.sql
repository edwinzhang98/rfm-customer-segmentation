/* =============================================================================
   10_segment_mix.sql  -  what each segment buys and who they are (current snapshot)
   -----------------------------------------------------------------------------
   Inputs  : data/marts/customer_rfm.parquet   (snapshot_name = 'current')
             data/marts/fct_sales_lines.parquet
             data/staged/stg_articles.parquet
             data/marts/dim_customers.parquet
   Output  : data/marts/segment_mix.parquet
             long format: segment x dimension x value
   Dimensions
     revenue-based  : index_group (Ladieswear, Divided, Menswear, Baby/Children, Sport),
                      product_group (upper body, lower body, shoes, ...),
                      garment_group (knitwear, outdoor, denim, ...)
                      -> share of the segment's revenue in each category
     customer-based : channel_profile, age_band, club_member_status, newsletter_frequency,
                      first_order_channel  -> share of the segment's customers
   affinity_index = segment share / share across all segments x 100
                    (120 = this segment over-indexes by 20% on that category / trait)
   Window  : revenue mix uses the last 12 months for active segments; Lost customers have
             no 12-month revenue, so their mix uses their full two-year history.
             Excluded accounts are left out of the "all customers" baseline.
   Run     : python scripts/run_sql.py sql/10_segment_mix.sql
   ============================================================================= */

SET VARIABLE lookback_days = COALESCE(getvariable('lookback_days'), 365);

COPY (
    WITH
    cur AS (
        SELECT r.customer_id, r.segment, r.snapshot_date, d.channel_profile, d.age_band,
               d.club_member_status, d.newsletter_frequency, d.first_order_channel
        FROM 'data/marts/customer_rfm.parquet' r
        JOIN 'data/marts/dim_customers.parquet' d USING (customer_id)
        WHERE r.snapshot_name = 'current'
    ),
    lines AS (
        SELECT c.segment, a.index_group_name, a.product_group_name, a.garment_group_name,
               l.line_revenue_cents
        FROM 'data/marts/fct_sales_lines.parquet' l
        JOIN cur c USING (customer_id)
        JOIN 'data/staged/stg_articles.parquet' a USING (article_id)
        WHERE c.segment = 'Lost'
           OR (c.snapshot_date - l.order_date) < getvariable('lookback_days')
    ),
    revenue_long AS (
        SELECT segment, 'index_group'   AS dimension, index_group_name   AS value, SUM(line_revenue_cents) AS amount FROM lines GROUP BY ALL
        UNION ALL
        SELECT segment, 'product_group',               product_group_name,          SUM(line_revenue_cents)           FROM lines GROUP BY ALL
        UNION ALL
        SELECT segment, 'garment_group',               garment_group_name,          SUM(line_revenue_cents)           FROM lines GROUP BY ALL
    ),
    customer_long AS (
        SELECT segment, 'channel_profile' AS dimension, channel_profile AS value, COUNT(*) AS amount FROM cur GROUP BY ALL
        UNION ALL
        SELECT segment, 'age_band',             age_band,             COUNT(*) FROM cur GROUP BY ALL
        UNION ALL
        SELECT segment, 'club_member_status',   club_member_status,   COUNT(*) FROM cur GROUP BY ALL
        UNION ALL
        SELECT segment, 'newsletter_frequency', newsletter_frequency, COUNT(*) FROM cur GROUP BY ALL
        UNION ALL
        SELECT segment, 'first_order_channel',  first_order_channel,  COUNT(*) FROM cur GROUP BY ALL
    ),
    combined AS (
        SELECT 'revenue' AS basis, * FROM revenue_long
        UNION ALL
        SELECT 'customers', * FROM customer_long
    ),
    with_shares AS (
        SELECT
            basis,
            segment,
            dimension,
            value,
            amount,
            amount / SUM(amount) OVER (PARTITION BY segment, dimension) AS segment_share
        FROM combined
    ),
    baseline AS (
        SELECT dimension, value,
               SUM(amount) / SUM(SUM(amount)) OVER (PARTITION BY dimension) AS overall_share
        FROM combined
        WHERE segment <> 'Excluded'
        GROUP BY dimension, value
    )
    SELECT
        w.basis,
        w.segment,
        w.dimension,
        w.value,
        CASE WHEN w.basis = 'revenue' THEN w.amount / 100.0 ELSE w.amount END AS amount,
        w.segment_share,
        b.overall_share,
        100.0 * w.segment_share / NULLIF(b.overall_share, 0)                   AS affinity_index
    FROM with_shares w
    LEFT JOIN baseline b USING (dimension, value)
    ORDER BY w.segment, w.dimension, w.segment_share DESC
) TO 'data/marts/segment_mix.parquet' (FORMAT parquet);

SELECT dimension, COUNT(DISTINCT value) AS n_values, COUNT(*) AS n_rows
FROM 'data/marts/segment_mix.parquet' GROUP BY 1 ORDER BY 1;
