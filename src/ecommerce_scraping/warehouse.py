"""Serving layer: DuckDB views over the processed Parquet and the run summaries.

Views are recreated on every call with absolute paths baked in, so creating them is idempotent
and follows a moved data dir. Only runs with a summary of status ok or partial are exposed:
files of a crashed or unfinished transform stay hidden.
"""

from typing import Any

import duckdb

from ecommerce_scraping.runs import RunPaths, StepError, latest_transformed_run

VIEWS = ("runs", "product_snapshots", "products_latest", "price_history", "rejects")

_HIVE = "hive_partitioning = true, hive_types = {{'store': VARCHAR, 'run_date': DATE}}"

# JSON timestamps are declared TIMESTAMP so the session time zone never shifts them.
_RUNS = """
CREATE OR REPLACE VIEW runs AS
SELECT r.run_id, r.status, r.transformed_at,
       s.store, s.finish_reason, s.pages_archived, s.robots_forbidden, s.http_errors, s.retries,
       s.rows_out, s.rejected, s.duplicates,
       s.started_at, s.finished_at
FROM read_json('{runs}', columns = {{
    run_id: 'VARCHAR', status: 'VARCHAR', transformed_at: 'TIMESTAMP',
    stores: 'STRUCT(store VARCHAR, finish_reason VARCHAR, pages_archived BIGINT,
        robots_forbidden BIGINT, http_errors BIGINT, retries BIGINT, started_at TIMESTAMP,
        finished_at TIMESTAMP, rows_out BIGINT, rejected BIGINT, duplicates BIGINT)[]'
}}) r, unnest(r.stores) t(s);
"""

_REST = f"""
CREATE OR REPLACE VIEW product_snapshots AS
SELECT p.* FROM read_parquet('{{products}}', {_HIVE}) p
SEMI JOIN (SELECT DISTINCT run_id FROM runs WHERE status IN ('ok', 'partial')) c USING (run_id);

CREATE OR REPLACE VIEW products_latest AS
SELECT * FROM product_snapshots
QUALIFY row_number() OVER (
    PARTITION BY store, product_key ORDER BY scraped_at DESC, run_id DESC
) = 1;

CREATE OR REPLACE VIEW price_history AS
SELECT store, product_key, name, run_date, run_id, scraped_at, price, high_price, currency,
       in_stock,
       price - lag(price) OVER (
           PARTITION BY store, product_key ORDER BY scraped_at, run_id
       ) AS price_change
FROM product_snapshots;

CREATE OR REPLACE VIEW rejects AS
SELECT p.* FROM read_parquet('{{rejects}}', {_HIVE}) p
SEMI JOIN (SELECT DISTINCT run_id FROM runs WHERE status IN ('ok', 'partial')) c USING (run_id);
"""

_STATS = """
SELECT r.store, r.runs, coalesce(s.snapshots, 0) AS snapshots, coalesce(l.products, 0) AS products,
       coalesce(j.rejects, 0) AS rejects, l.last_run_id, l.last_scraped_at
FROM (SELECT store, count(*) AS runs FROM runs GROUP BY store) r
LEFT JOIN (SELECT store, count(*) AS snapshots FROM product_snapshots GROUP BY store) s USING (store)
LEFT JOIN (
    SELECT store, count(*) AS products, max(run_id) AS last_run_id,
           max(scraped_at) AS last_scraped_at
    FROM products_latest GROUP BY store
) l USING (store)
LEFT JOIN (SELECT store, count(*) AS rejects FROM rejects GROUP BY store) j USING (store)
ORDER BY r.store
"""


def create_views(paths: RunPaths) -> list[str]:
    """(Re)create the serving views over the latest data; returns their names."""
    if latest_transformed_run(paths) is None:
        raise StepError("no transformed run yet: run `transform` first")
    root = paths.processed_root.resolve().as_posix()
    sql = (_RUNS + _REST).format(
        runs=f"{root}/_runs/*.json",
        products=f"{root}/products/*/*/*.parquet",
        rejects=f"{root}/rejects/*/*/*.parquet",
    )
    con = duckdb.connect(str(paths.warehouse))
    try:
        con.execute(sql)
    finally:
        con.close()
    return list(VIEWS)


def stats(paths: RunPaths) -> list[dict[str, Any]]:
    """One row per store from the views: counts, last run and last scrape time."""
    create_views(paths)
    con = duckdb.connect(str(paths.warehouse), read_only=True)
    try:
        cur = con.execute(_STATS)
        names = [d[0] for d in cur.description]
        return [dict(zip(names, row, strict=True)) for row in cur.fetchall()]
    finally:
        con.close()
