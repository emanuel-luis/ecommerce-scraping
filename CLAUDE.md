# ecommerce-scraping

Layered ingestion pipeline for three VTEX fashion stores (Hering, Levi's, TNG): Scrapy crawl ->
raw (redacted pages) -> transform (JSON-LD parse, validate, dedupe) -> processed (Parquet by
store/run_date) -> DuckDB views. Portfolio repo of a data engineer: changes must keep the
layers, idempotency, contracts and polite crawling visible.

## Commands

- `uv sync --locked`: install (Python 3.12, dev group included).
- `make lint`: `uv run ruff check`, `uv run ruff format --check`, `uv run mypy` (the CI lint job).
- `make test`: offline pytest with `--cov-fail-under=85` (includes the e2e crawl against local
  servers). `make test-fast` skips coverage.
- `make demo`: live crawl of 5 products per store, then `stats`. `make up` / `make down`: compose.
- On Windows without make, run the underlying `uv run ...` commands.

## Repo map

- `src/ecommerce_scraping/cli.py`: Typer app (`crawl`, `transform`, `views`, `run`, `stats`).
- `config.py`: `Settings`, env prefix `ECOMMERCE_`. `runs.py`: run ids, `RunPaths` (layer
  layout), latest-run lookups, `StepError`, step logger. `stores.py`: store registry.
- `spider.py` (sitemap spider), `middlewares.py` (`BlockedStopMiddleware`), `pipelines.py`
  (`RawArchivePipeline`), `scrapy_settings.py`, `crawl.py` (`run_crawl`, `run.json`).
- `jsonld.py`: pure functions: `redact_page`, `extract_blocks`, `parse_product`, normalizers.
- `transform.py`: raw run -> Parquet + rejects + `_runs/<run_id>.json`.
- `warehouse.py`: DuckDB views and `stats`. `models.py`: pydantic contracts. `schema.py`:
  Parquet columns and DDL.
- `tests/fixtures/pages/`: redacted real pages + synthetic edge cases; `tests/fixtures/site/`:
  fixture-site templates served by `tests/conftest.py`. See `tests/fixtures/README.md`.
- `docs/DECISIONS.md`: decisions log. `docs/REFACTOR_PLAN.md`: the design.

## Invariants

- Politeness: `ROBOTSTXT_OBEY`, identifying User-Agent, one request at a time per store, delay
  >= 2 s (lower only for loopback targets), AutoThrottle, stop on 403/429 (no 429 retry), a
  product limit per run. Never add a way around robots.txt or an anti-bot response.
- No listening servers in a crawl: Scrapy's telnet console and remote-control HTTP server stay
  disabled (`scrapy_settings.py`; asserted in `test_crawl.py` and the e2e).
- Tests and CI never contact a store. A live crawl only happens through `crawl`/`run`/`make demo`.
- The raw layer holds only `redact_page` output: canonical link + JSON-LD `Product` nodes without
  reviews, authors or Person/Review nodes. Fixtures are produced by the same function.
- A raw run directory is immutable: the pipeline refuses an existing store dir; `run.json` is
  written last and marks the crawl complete.
- `transform` is the only parse path and is idempotent: same raw run -> same rows at the same
  paths. It deletes `_runs/<run_id>.json` first and writes it last; views only expose runs with
  status ok or partial.
- Per store and run: manifest lines = `pages_archived` in the raw `run.json` (checked by
  transform); every page becomes a row, a reject or a duplicate. `product_key` is the lowercased
  path of the final URL.
- Run ids are `YYYYMMDDTHHMMSSZ` real UTC times; the CLI rejects anything else and the
  latest-run lookups skip other names.
- Partition columns (`store`, `run_date`) live only in the path; `run_date` comes from the run_id.
- Timestamps are aware UTC in Python and UTC `TIMESTAMP` columns in Parquet and DuckDB
  (`naive_utc`).
- The Twisted reactor never starts in the pytest process; real crawls run in a subprocess.

## Conventions

- uv only; `pyproject.toml` + committed `uv.lock`. ruff line-length 100 with `BLE`
  (`# noqa: BLE001 - reason` on a broad except); mypy strict on `src`.
- Code, docs and commit messages in English; Conventional Commits.
- Work on a branch; the default branch is `main`.
- No secrets: settings come from `ECOMMERCE_*` env vars, none of them secret.
- Record design decisions in `docs/DECISIONS.md`; update README and CHANGELOG with behavior
  changes.
