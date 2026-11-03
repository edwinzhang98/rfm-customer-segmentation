/* =============================================================================
   09_segment_profile.sql  -  one row per segment at the current snapshot
   -----------------------------------------------------------------------------
   Input   : data/marts/customer_rfm.parquet   (snapshot_name = 'current')
             data/marts/dim_customers.parquet
   Output  : data/marts/segment_profile.parquet
   Columns : size and value       customers, % of customers, 12-month revenue and %,
                                  two-year revenue and % (only measure that is non-zero for Lost)
             behaviour            avg recency, avg orders, AOV (= revenue / orders),
                                  units per order, median days between orders
             channel              % online only / store only / omnichannel, on the last
                                  12 months (operational) and on two years (context)
             reach                % newsletter subscribers (email-reachable), % active club members
             demographics         median age, % age unknown
   Notes   : Revenue shares sum to 100% across the 10 groups (incl. Review List), so the
             table reconciles to the company total.
   Run     : python scripts/run_sql.py sql/09_segment_profile.sql
   ============================================================================= */

COPY (
    WITH cur AS (
        SELECT r.*, d.lifetime_revenue_cents, d.age, d.first_order_channel
        FROM 'data/marts/customer_rfm.parquet' r
        JOIN 'data/marts/dim_customers.parquet' d USING (customer_id)
        WHERE r.snapshot_name = 'current'
    ),
    agg AS (
        SELECT
            segment,
            COUNT(*)                                                     AS customers,
            SUM(monetary_12m_cents) / 100.0                              AS revenue_12m_cu,
            SUM(lifetime_revenue_cents) / 100.0                          AS revenue_2y_cu,
            SUM(frequency_12m)                                           AS orders_12m,
            SUM(units_12m)                                               AS units_12m,
            SUM(orders_to_date)                                          AS orders_2y,
            AVG(recency_days)                                            AS avg_recency_days,
            MEDIAN(recency_days)                                         AS median_recency_days,
            AVG(frequency_12m)                                           AS avg_orders_12m,
            SUM(monetary_12m_cents) / COUNT(*) / 100.0                   AS avg_revenue_12m_cu,
            MEDIAN(avg_days_between_orders_12m)                          AS median_days_between_orders,
            AVG(tenure_days)                                             AS avg_tenure_days,
            AVG((channel_12m = 'Online only')::INT) FILTER (WHERE frequency_12m > 0)  AS pct_online_only_12m,
            AVG((channel_12m = 'Store only')::INT)  FILTER (WHERE frequency_12m > 0)  AS pct_store_only_12m,
            AVG((channel_12m = 'Omnichannel')::INT) FILTER (WHERE frequency_12m > 0)  AS pct_omnichannel_12m,
            AVG((channel_profile_2y = 'Online only')::INT)               AS pct_online_only_2y,
            AVG((channel_profile_2y = 'Store only')::INT)                AS pct_store_only_2y,
            AVG((channel_profile_2y = 'Omnichannel')::INT)               AS pct_omnichannel_2y,
            AVG((value_tier = 'VIP')::INT)                               AS pct_vip,
            SUM(online_revenue_12m_cents) / NULLIF(SUM(monetary_12m_cents), 0) AS online_revenue_share_12m,
            AVG(is_newsletter_subscriber::INT)                           AS pct_newsletter,
            AVG((club_member_status = 'ACTIVE')::INT)                    AS pct_club_active,
            MEDIAN(age)                                                  AS median_age,
            AVG((age IS NULL)::INT)                                      AS pct_age_unknown
        FROM cur
        GROUP BY segment
    )
    SELECT
        segment,
        CASE segment
            WHEN 'Champions'           THEN 1
            WHEN 'Loyal'               THEN 2
            WHEN 'Slipping Regulars'   THEN 3
            WHEN 'Potential Loyalists' THEN 4
            WHEN 'New Customers'       THEN 5
            WHEN 'Needs Attention'     THEN 6
            WHEN 'At Risk'             THEN 7
            WHEN 'Hibernating'         THEN 8
            WHEN 'Lost'                THEN 9
            WHEN 'Review List'         THEN 10
        END                                                              AS segment_order,
        customers,
        customers / SUM(customers) OVER ()                               AS pct_customers,
        revenue_12m_cu,
        revenue_12m_cu / SUM(revenue_12m_cu) OVER ()                     AS pct_revenue_12m,
        revenue_2y_cu,
        revenue_2y_cu / SUM(revenue_2y_cu) OVER ()                       AS pct_revenue_2y,
        orders_12m,
        revenue_12m_cu / NULLIF(orders_12m, 0)                           AS aov_12m_cu,
        revenue_2y_cu / NULLIF(orders_2y, 0)                             AS aov_2y_cu,
        units_12m / NULLIF(orders_12m, 0)                                AS units_per_order_12m,
        avg_recency_days,
        median_recency_days,
        avg_orders_12m,
        avg_revenue_12m_cu,
        median_days_between_orders,
        avg_tenure_days,
        pct_online_only_12m,
        pct_store_only_12m,
        pct_omnichannel_12m,
        pct_online_only_2y,
        pct_store_only_2y,
        pct_omnichannel_2y,
        pct_vip,
        online_revenue_share_12m,
        pct_newsletter,
        pct_club_active,
        median_age,
        pct_age_unknown
    FROM agg
    ORDER BY segment_order
) TO 'data/marts/segment_profile.parquet' (FORMAT parquet);

SELECT segment, customers, ROUND(pct_customers * 100, 1) AS pct_customers,
       ROUND(pct_revenue_12m * 100, 1) AS pct_revenue_12m, ROUND(aov_12m_cu, 1) AS aov_12m_cu
FROM 'data/marts/segment_profile.parquet' ORDER BY segment_order;
