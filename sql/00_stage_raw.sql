/* =============================================================================
   00_stage_raw.sql  -  stage the three raw H&M CSV files as typed Parquet
   -----------------------------------------------------------------------------
   Inputs  : data/raw/transactions_train.csv   31,788,324 rows, one row = one item bought
             data/raw/customers.csv            1,371,980 rows
             data/raw/articles.csv               105,542 rows
             (data/raw is a symlink to data.raw_dir in config.yaml, created by
              `python run.py --steps link`; raw files are never copied into the repo)
   Outputs : data/staged/stg_transactions.parquet
             data/staged/stg_customers.parquet
             data/staged/stg_articles.parquet
   Notes   : Staging keeps source column names and only fixes types.
             article_id stays VARCHAR so the leading zero survives joins.
             FN / Active / age arrive as text like "1.0", hence the double cast.
   Run     : python scripts/run_sql.py sql/00_stage_raw.sql    (from the repo root)
   ============================================================================= */

COPY (
    SELECT
        CAST(t_dat AS DATE)               AS t_dat,
        customer_id,
        article_id,
        price,
        CAST(sales_channel_id AS TINYINT) AS sales_channel_id
    FROM read_csv(
        'data/raw/transactions_train.csv',
        header  = true,
        columns = {'t_dat': 'DATE', 'customer_id': 'VARCHAR', 'article_id': 'VARCHAR',
                   'price': 'DOUBLE', 'sales_channel_id': 'INTEGER'}
    )
) TO 'data/staged/stg_transactions.parquet' (FORMAT parquet, COMPRESSION zstd);

COPY (
    SELECT
        customer_id,
        TRY_CAST(TRY_CAST(FN     AS DOUBLE) AS INTEGER) AS fn,
        TRY_CAST(TRY_CAST(Active AS DOUBLE) AS INTEGER) AS active,
        club_member_status,
        fashion_news_frequency,
        TRY_CAST(TRY_CAST(age    AS DOUBLE) AS INTEGER) AS age,
        postal_code
    FROM read_csv('data/raw/customers.csv', header = true, all_varchar = true)
) TO 'data/staged/stg_customers.parquet' (FORMAT parquet, COMPRESSION zstd);

COPY (
    SELECT *
    FROM read_csv('data/raw/articles.csv', header = true, all_varchar = true)
) TO 'data/staged/stg_articles.parquet' (FORMAT parquet, COMPRESSION zstd);

-- Row counts written, for the run log
SELECT 'stg_transactions' AS table_name, COUNT(*) AS row_count FROM 'data/staged/stg_transactions.parquet'
UNION ALL SELECT 'stg_customers', COUNT(*) FROM 'data/staged/stg_customers.parquet'
UNION ALL SELECT 'stg_articles',  COUNT(*) FROM 'data/staged/stg_articles.parquet';
