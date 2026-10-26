# Refactor plan

Design for turning the 2022 multi-retailer Scrapy project into a layered ingestion pipeline.
Decisions behind it are in [DECISIONS.md](DECISIONS.md).

## Data flow

```
store sitemaps ──Scrapy (polite)──> raw ──transform──> processed ──views──> serving
robots.txt -> /sitemap.xml        redacted pages    validated Parquet      DuckDB views
-> product-N.xml -> /<slug>/p     + manifest.jsonl  + rejects, partitioned  over Parquet
                                  + run.json        by store / run_date
```

- **Crawl** only fetches and lands raw pages. Scrapy yields one `RawPage` per product page and a
  single item pipeline writes it to the raw layer.
- **Transform** (`transform --run-id`) is the only parse path: JSON-LD extraction, validation,
  dedupe, Parquet. Re-running it on the same raw run rewrites the same files, so reprocessing is
  the normal path, not a special command.
- **Serving** is a set of DuckDB views over the Parquet files; creating them is idempotent.

## Choices

- **Raw is redacted at write time.** `redact_page(html)` keeps the canonical link and the
  `application/ld+json` blocks with every `review` / `reviews` key removed, and drops the body.
  Committed fixtures are produced by the same function, so they hold no personal data by
  construction.
- **Raw goes through an item pipeline**, not HTTPCACHE (a fingerprint-keyed cache, not
  run-scoped) or a downloader middleware (it would also see robots.txt and sitemaps).
- **Blocked means stop.** `BlockedStopMiddleware` closes a store's spider on a 403 or 429 (the
  robots.txt request included: Scrapy otherwise treats a 403 robots.txt as allow-all) and refuses
  every later request of that spider.
- **product_key** = lowercased path of the final response URL without query or trailing slash
  (`/slug/p`). Always present and unique per store, and independent of which Product block wins
  (TNG ships two blocks whose SKUs differ: `475289` and `00475289`). `sku`, `mpn`, `gtin` stay as
  attributes.
- **Product choice**: the Product node whose `@id` / `url` host equals the page host, else the
  first one.
- **Price**: one row per product per run. `price` = `Offer.price`; for an AggregateOffer
  `lowPrice`, else the minimum nested offer price. `high_price` = `highPrice` (null for a single
  Offer). `in_stock` is true when any top-level or nested offer is `InStock`. Per-variant rows
  are a possible follow-up.
- **Idempotency**: `run_date` derives from the run_id, so a run never spans two partitions and a
  rerun hits the same paths. Every store in a run writes both files (possibly 0 rows) through a
  temp file and `os.replace`. `_runs/<run_id>.json` is written last; views only expose runs that
  have it.
- **Parquet writer**: DuckDB `COPY ... (FORMAT parquet, COMPRESSION zstd)` from a typed table, as
  in books-scraping. One dependency covers writing and serving; the DDL is the Parquet contract.
- **Partition columns** live only in the path (`store=`, `run_date=`), so hive reads never see
  them twice.
- **Description** is not extracted (large, unused, third-party copy); fixtures replace it with a
  placeholder.

## Layout

```
pyproject.toml, uv.lock, .python-version, Makefile, Dockerfile, compose.yaml, .dockerignore,
.env.example, .gitattributes, .gitignore
.github/workflows/ci.yml, security.yml; .github/dependabot.yml
README.md, CHANGELOG.md, CLAUDE.md, LICENSE, docs/DECISIONS.md, docs/REFACTOR_PLAN.md
src/ecommerce_scraping/
  __init__.py         __version__
  __main__.py         python -m entry point (the e2e subprocess uses it)
  py.typed
  config.py           pydantic-settings, prefix ECOMMERCE_
  runs.py             run_id, naive_utc, RunPaths, latest complete run, StepError, step_logger
  models.py           contracts (below)
  stores.py           frozen Store registry: hering, levi, tng
  jsonld.py           pure: extract_blocks, redact_page, iter_products, pick_product,
                      normalizers, parse_product
  scrapy_settings.py  Scrapy settings (constants)
  spider.py           ProductsSpider(SitemapSpider)
  middlewares.py      BlockedStopMiddleware
  pipelines.py        RawArchivePipeline
  crawl.py            builds settings, one CrawlerProcess, writes raw run.json
  transform.py        raw run -> processed Parquet + _runs/<run_id>.json
  warehouse.py        CREATE OR REPLACE views, stats
  cli.py              Typer app
tests/
  conftest.py         fixture-site HTTP server ({{BASE}} substitution), tmp data dir
  fixtures/README.md  provenance and redaction steps
  fixtures/pages/     hering, levi, tng, damyller (redacted real pages) + synthetic_*.html
  fixtures/site/      robots.txt, sitemap.xml, sitemap/product-0.xml (with {{BASE}})
  test_*.py
```

The legacy `main.py`, `ecommerce/` and `requirements.txt` are deleted. No `scrapy.cfg`: the CLI
is the only entry point.

## Contracts (`models.py`)

Frozen pydantic models with `extra="forbid"`; datetimes are aware UTC.

- `RawPage` (Scrapy item, dataclass): store, url, final_url, status, fetched_at, html.
- `ManifestEntry`: url, final_url, status, fetched_at, path (relative to the run dir), sha256 (of
  the stored bytes), bytes.
- `ProductSnapshot`: run_id (`^\d{8}T\d{6}Z$`), store (`^[a-z0-9-]+$`), product_key (min 1), url,
  sku / mpn / gtin `str | None`, name `str` (min 1), brand / category / color / material
  `str | None`, price `Decimal` (>= 0, 2 dp), high_price `Decimal | None` (>= price), currency
  (`^[A-Z]{3}$`), availability (schema.org ItemAvailability token `| None`), in_stock
  `bool | None`, offer_count `int | None` (>= 1), image_url `str | None`, scraped_at, raw_path.
- `Reject`: run_id, store, url, raw_path, stage (`parse` | `validate` | `duplicate`), reason,
  scraped_at. Invariant: pages = rows_out + rejects.
- `StoreCrawl`: store, finish_reason, pages_archived, robots_forbidden, http_errors, retries,
  started_at, finished_at. `CrawlSummary`: run_id, stores.
- `StoreRun(StoreCrawl)`: + rows_out, rejected, duplicates. `RunSummary`: run_id, status
  (`ok` | `partial` | `failed`), transformed_at, stores.

On-disk layout:

```
data/raw/<run_id>/<store>/<sha256(url)[:16]>.html.gz
data/raw/<run_id>/<store>/manifest.jsonl
data/raw/<run_id>/run.json                                       CrawlSummary, written last
data/processed/products/store=<s>/run_date=<YYYY-MM-DD>/<run_id>.parquet
data/processed/rejects/store=<s>/run_date=<YYYY-MM-DD>/<run_id>.parquet
data/processed/_runs/<run_id>.json                               RunSummary, written last
data/warehouse.duckdb
```

Parquet columns: run_id, product_key, url, sku, mpn, gtin, name, brand, category, color,
material, currency, availability, image_url, raw_path `VARCHAR`; price, high_price
`DECIMAL(12,2)`; in_stock `BOOLEAN`; offer_count `INTEGER`; scraped_at `TIMESTAMP` (naive UTC).
Rows sorted by product_key.

Views (absolute paths resolved when `views` runs; `hive_types={'run_date': DATE}`):

```sql
CREATE OR REPLACE VIEW runs AS
  SELECT r.run_id, r.status, s.* FROM read_json('<p>/_runs/*.json') r, unnest(r.stores) t(s);
CREATE OR REPLACE VIEW product_snapshots AS
  SELECT p.* FROM read_parquet('<p>/products/*/*/*.parquet', hive_partitioning = true, ...) p
  SEMI JOIN (SELECT DISTINCT run_id FROM runs) c USING (run_id);
CREATE OR REPLACE VIEW products_latest AS
  SELECT * FROM product_snapshots
  QUALIFY row_number() OVER (PARTITION BY store, product_key ORDER BY scraped_at DESC) = 1;
CREATE OR REPLACE VIEW price_history AS
  SELECT store, product_key, name, run_date, run_id, scraped_at, price, high_price, currency,
         in_stock,
         price - lag(price) OVER (PARTITION BY store, product_key ORDER BY scraped_at)
           AS price_change
  FROM product_snapshots;
CREATE OR REPLACE VIEW rejects AS
  SELECT * FROM read_parquet('<p>/rejects/*/*/*.parquet', hive_partitioning = true, ...);
```

`views` exits 1 with a clear message when no complete run exists (DuckDB binds globs at CREATE).

## Crawl wiring

- `Store(name, base_url)`; product sitemap pattern `/sitemap/product-\d+\.xml$`, product URL
  pattern `/p$`; `allowed_domains` derived from base_url. `ECOMMERCE_STORE_BASE_URLS` (JSON)
  overrides base URLs, for the offline e2e only.
- `ProductsSpider(store, limit)`: `sitemap_urls = [f"{base}/sitemap.xml"]`. `sitemap_filter`
  (called for index and urlset entries) applies the patterns itself and, with a limit, follows
  only the first product sitemap and yields the first `limit` product URLs in sitemap order.
  `parse_product` yields `RawPage(html=redact_page(response.text), ...)`.
- `RawArchivePipeline` refuses an existing store run dir, writes gzip through temp + replace and
  appends to the manifest.
- `crawl.run_crawl(stores, limit, run_id, cfg)`: one `CrawlerProcess(install_root_handler=False)`
  with one crawler per store (concurrent; politeness is per domain), then `run.json` from each
  crawler's stats.
- Scrapy settings: `ROBOTSTXT_OBEY=True`; `USER_AGENT="ecommerce-scraping/<version>
  (+https://github.com/emanuel-luis/ecommerce-scraping)"`; `CONCURRENT_REQUESTS=8`,
  `CONCURRENT_REQUESTS_PER_DOMAIN=1`, `DOWNLOAD_DELAY=3`, `RANDOMIZE_DOWNLOAD_DELAY=False`;
  AutoThrottle on (start 3 s, max 60 s, target concurrency 1.0); `RETRY_TIMES=2`,
  `RETRY_HTTP_CODES=[500, 502, 503, 504, 522, 524, 408]` (no 429: stop instead);
  `DOWNLOAD_TIMEOUT=30`, `DOWNLOAD_MAXSIZE=10 MB`, cookies, HTTP cache and telnet off;
  `CLOSESPIDER_TIMEOUT=3600`, `CLOSESPIDER_ERRORCOUNT=10`; `RawArchivePipeline` at 300,
  `BlockedStopMiddleware` at 560 (above RetryMiddleware, so it sees responses first).
- `ECOMMERCE_DOWNLOAD_DELAY_S` (default 3) overrides the delay; at 0 AutoThrottle is off. A
  validator rejects a delay under 2 s unless every base URL is loopback.

## CLI

`crawl [--store X]... [--limit 20] [--run-id]`, `transform [--run-id latest]`, `views`,
`run` (crawl -> transform -> views, the demo), `stats`, `--version`. `--store` is an enum over the
registry. The default limit of 20 per store prevents an accidental full-catalog crawl. The
reactor starts once per process; tests never start it in-process (spider, pipeline and
middleware are tested with `get_crawler` and `HtmlResponse` / `XmlResponse`), and the real crawl
runs only in the e2e subprocess. Exit 1 when the run `failed` (no store archived a page);
`partial` warns and exits 0.

## Tests (coverage gate 85 %)

- jsonld: expected fields per fixture (Levi's `&apos;` unescaped; TNG picks the www block, SKU
  `00475289`; Hering's list of AggregateOffer with `type`; Damyller's `http://` availability and
  integer price); synthetic pages for no JSON-LD, invalid JSON, `@graph` only, and reviews with a
  fake name that must never reach redacted output or a row.
- Hypothesis: availability normalizer is total; price parsing round-trips to 2 dp; nested offers
  always give price <= high_price; text normalizer returns None or stripped non-empty text.
- Spider (sitemap filtering and limit), middleware (403 / 429 stop, robots.txt included), pipeline
  (gzip + manifest, existing dir refused), transform (dedupe, rejects invariant, rerun gives
  identical rows, partitions from run_id), warehouse (views, latest across two runs, incomplete
  runs hidden).
- e2e: two fixture servers on 127.0.0.1 (robots.txt is per host:port), stores levi and tng, delay
  0; the sitemap holds a robots-disallowed URL, a 404 and a page without JSON-LD. Asserts exit 0,
  manifests, `robots_forbidden`, Parquet rows and rejects, run files, view counts, and that the
  fake reviewer name appears nowhere under `data/`. Coverage measures the subprocess
  (`[tool.coverage.run] patch = ["subprocess"]`).

## Delivery steps (each ends green on `make lint test`)

1. Scaffold: pyproject + lock, package skeleton, config, runs, models, stores,
   `jsonld.extract_blocks` + `redact_page` with tests, Makefile; delete the legacy code.
2. In parallel: (a) `jsonld.parse_product` + normalizers, fixture pages, jsonld tests;
   (b) Scrapy settings, spider, middleware, pipeline, crawl + tests.
3. In parallel: (a) transform; (b) warehouse.
4. CLI, `__main__`, conftest fixture server, e2e and CLI tests.
5. In parallel: (a) Dockerfile, compose, workflows, Dependabot; (b) README, CHANGELOG, CLAUDE.md.
6. A small live `make demo` (5 products per store) and `docker compose up`, with evidence.
