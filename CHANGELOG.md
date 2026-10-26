# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

The 2022 multi-store Scrapy project is replaced by a layered ingestion pipeline (version 0.1.0
in `pyproject.toml`).

### Added

- `ecommerce_scraping` package (src layout, typed) with a Typer CLI: `crawl`, `transform`,
  `views`, `run`, `stats`.
- One sitemap spider for every store: robots.txt-listed sitemaps, product sitemaps only, product
  pages only, with a per-run limit (20 per store by default).
- Raw layer: one redacted page per product URL (canonical link and JSON-LD `Product` nodes,
  without reviews or person data), gzip, `manifest.jsonl` with URL, status, UTC fetch time and
  SHA-256, and `run.json` with per-store crawl stats.
- JSON-LD parser for schema.org `Product` / `Offer` / `AggregateOffer`, with normalizers for
  prices, availability and text.
- Processed layer: pydantic contract, checksum verification, deduplication by product key,
  rejects with stage and reason, Parquet partitioned by `store` and `run_date`, and a run summary
  written last.
- Serving layer: DuckDB views `runs`, `product_snapshots`, `products_latest`, `price_history`,
  `rejects`.
- Offline tests on redacted product pages and an end-to-end crawl against local fixture servers;
  85 % coverage gate, ruff, mypy strict.
- Multi-stage Docker image (non-root, healthcheck), `compose.yaml`, Makefile, GitHub Actions
  (lint, test, docker, pip-audit, zizmor) and Dependabot.
- `docs/DECISIONS.md`, `docs/REFACTOR_PLAN.md`, `CLAUDE.md`, MIT `LICENSE`.

### Changed

- Targets: Hering, Levi's and TNG stay; Afabula, Alphabeto, Daksul, Damyller, Lupo, Marisa,
  Mormaii and Tricae are dropped (reasons in `docs/DECISIONS.md`). One saved Damyller page
  remains as a parser fixture.
- Extraction reads schema.org JSON-LD instead of XPath on CSS classes.
- Output is Parquet and DuckDB instead of CSV and JSON feeds.
- Dependencies are managed with uv (`pyproject.toml` and `uv.lock`) instead of a pip freeze.

### Removed

- Splash, Selenium, the vendored geckodriver and js2py: every kept store renders its product
  data server-side.
- The 2022 output under `products/` and the old `readme.md` from the working tree (both remain
  in git history).

### Fixed

- The crawler obeys robots.txt, sends an identifying User-Agent, uses AutoThrottle with one
  request at a time per store, and stops a store on 403 or 429. The 2022 settings ignored
  robots.txt and allowed 16 concurrent requests per domain.
- Scraped timestamps are UTC datetimes (`scraped_at`) instead of a local date string in a
  `scrapped-at` column.
