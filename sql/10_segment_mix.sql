/* =============================================================================
   10_segment_mix.sql  -  what each segment bought and who they are (current snapshot)
   -----------------------------------------------------------------------------
   Inputs  : data/marts/customer_rfm.parquet   (snapshot_name = 'current')
             data/marts/fct_sales_lines.parquet
             data/staged/stg_articles.parquet
             data/marts/dim_customers.parquet
   Output  : data/marts/segment_mix.parquet
             long format: basis x segment x dimension x value
   Dimensions
     revenue-based  : index_group (department: Ladieswear, Divided, Menswear, Baby/Children,
                      Sport), product_group (upper body, lower body, shoes, ...),
                      garment_group (knitwear, outdoor, denim, ...)
                      -> share of the segment's revenue in each category
     customer-based : channel_12m (operational), channel_profile_2y (context), value_tier,
                      age_band, club_member_status, newsletter_frequency, first_order_channel
                      -> share of the segment's customers
   affinity_index = segment share / share across all customers x 100
                    (120 = the segment spends 20% more of its money on that category)
   Windows : "what they bought in their last active period":
             active segments use the last 12 months and are compared with all customers'
             last 12 months; Lost has no 12-month revenue, so Lost uses its full two-year
             history and is compared with all customers' two-year mix (same window on both
             sides of the ratio). Review List accounts are left out of every baseline.
   Caveat  : affinity reflects WHEN a segment last bought as much as WHAT it likes
             (At Risk last bought in autumn/winter -> knitwear; Needs Attention in summer
             -> swimwear). Read it as "what to show them now", not as a fixed taste.
   Run     : python scripts/run_sql.py sql/10_segment_mix.sql
   ============================================================================= */

SET VARIABLE lookback_days = COALESCE(getvariable('lookback_days'), 365);

COPY (
    WITH
    cur AS (
        SELECT r.customer_id, r.segment, r.snapshot_date, r.channel_12m, r.channel_profile_2y, r.value_tier,
               d.age_band, d.club_member_status, d.newsletter_frequency, d.first_order_channel
        FROM 'data/marts/customer_rfm.parquet' r
        JOIN 'data/marts/dim_customers.parquet' d USING (customer_id)
        WHERE r.snapshot_name = 'current'
    ),
    lines AS (
        SELECT c.segment, a.index_group_name, a.product_group_name, a.garment_group_name,
               l.line_revenue_cents,
               (c.snapshot_date - l.order_date) < getvariable('lookback_days') AS in_12m
        FROM 'data/marts/fct_sales_lines.parquet' l
        JOIN cur c USING (customer_id)
        JOIN 'data/staged/stg_articles.parquet' a USING (article_id)
    ),
    -- numerator rows: active segments on 12 months, Lost on two years
    seg_lines AS (
        SELECT * FROM lines WHERE in_12m AND segment <> 'Lost'
        UNION ALL
        SELECT * FROM lines WHERE segment = 'Lost'
    ),
    revenue_long AS (
        SELECT segment, 'index_group' AS dimension, index_group_name AS value, SUM(line_revenue_cents) AS amount FROM seg_lines GROUP BY ALL
        UNION ALL SELECT segment, 'product_group', product_group_name, SUM(line_revenue_cents) FROM seg_lines GROUP BY ALL
        UNION ALL SELECT segment, 'garment_group', garment_group_name, SUM(line_revenue_cents) FROM seg_lines GROUP BY ALL
    ),
    -- baselines: all customers (minus Review List) on 12 months and on two years
    base_lines AS (
        SELECT '12m' AS window_, * FROM lines WHERE in_12m AND segment <> 'Review List'
        UNION ALL
        SELECT '2y', * FROM lines WHERE segment <> 'Review List'
    ),
    revenue_base AS (
        SELECT window_, 'index_group' AS dimension, index_group_name AS value, SUM(line_revenue_cents) AS amount FROM base_lines GROUP BY ALL
        UNION ALL SELECT window_, 'product_group', product_group_name, SUM(line_revenue_cents) FROM base_lines GROUP BY ALL
        UNION ALL SELECT window_, 'garment_group', garment_group_name, SUM(line_revenue_cents) FROM base_lines GROUP BY ALL
    ),
    customer_long AS (
        SELECT segment, 'channel_12m' AS dimension, channel_12m AS value, COUNT(*) AS amount FROM cur GROUP BY ALL
        UNION ALL SELECT segment, 'channel_profile_2y',   channel_profile_2y,   COUNT(*) FROM cur GROUP BY ALL
        UNION ALL SELECT segment, 'value_tier',           value_tier,           COUNT(*) FROM cur GROUP BY ALL
        UNION ALL SELECT segment, 'age_band',             age_band,             COUNT(*) FROM cur GROUP BY ALL
        UNION ALL SELECT segment, 'club_member_status',   club_member_status,   COUNT(*) FROM cur GROUP BY ALL
        UNION ALL SELECT segment, 'newsletter_frequency', newsletter_frequency, COUNT(*) FROM cur GROUP BY ALL
        UNION ALL SELECT segment, 'first_order_channel',  first_order_channel,  COUNT(*) FROM cur GROUP BY ALL
    ),
    customer_base AS (
        SELECT dimension, value, SUM(amount) AS amount
        FROM customer_long WHERE segment <> 'Review List' GROUP BY ALL
    ),
    shares AS (
        SELECT 'revenue' AS basis, segment, dimension, value, amount,
               amount / SUM(amount) OVER (PARTITION BY segment, dimension) AS segment_share,
               CASE WHEN segment = 'Lost' THEN '2y' ELSE '12m' END          AS window_
        FROM revenue_long
        UNION ALL
        SELECT 'customers', segment, dimension, value, amount,
               amount / SUM(amount) OVER (PARTITION BY segment, dimension),
               NULL
        FROM customer_long
    ),
    base_shares AS (
        SELECT window_, dimension, value, amount / SUM(amount) OVER (PARTITION BY window_, dimension) AS overall_share
        FROM revenue_base
        UNION ALL
        SELECT NULL, dimension, value, amount / SUM(amount) OVER (PARTITION BY dimension)
        FROM customer_base
    )
    SELECT
        s.basis,
        s.segment,
        s.dimension,
        s.value,
        CASE WHEN s.basis = 'revenue' THEN s.amount / 100.0 ELSE s.amount END AS amount,
        s.segment_share,
        b.overall_share,
        100.0 * s.segment_share / NULLIF(b.overall_share, 0)                   AS affinity_index,
        COALESCE(s.window_, 'customers')                                       AS window
    FROM shares s
    LEFT JOIN base_shares b
           ON b.dimension = s.dimension AND b.value = s.value
          AND b.window_ IS NOT DISTINCT FROM s.window_
    ORDER BY s.segment, s.dimension, s.segment_share DESC
) TO 'data/marts/segment_mix.parquet' (FORMAT parquet);

SELECT dimension, COUNT(DISTINCT value) AS n_values, COUNT(*) AS n_rows
FROM 'data/marts/segment_mix.parquet' GROUP BY 1 ORDER BY 1;
