"""Builds the Scrapy settings, runs one crawler per store and writes the raw run summary."""

from __future__ import annotations

import ipaddress
import os
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from scrapy.crawler import CrawlerProcess
from scrapy.settings import Settings as ScrapySettings

from ecommerce_scraping.config import Settings
from ecommerce_scraping.models import CrawlSummary, StoreCrawl
from ecommerce_scraping.runs import RunPaths, StepError, step_logger, utc_now
from ecommerce_scraping.spider import ProductsSpider
from ecommerce_scraping.stores import Store

MIN_DELAY_S = 2.0


def build_settings(cfg: Settings, run_id: str) -> ScrapySettings:
    settings = ScrapySettings()
    settings.setmodule("ecommerce_scraping.scrapy_settings", priority="project")
    settings.set("USER_AGENT", cfg.user_agent, priority="project")
    settings.set("DOWNLOAD_DELAY", cfg.download_delay_s, priority="project")
    settings.set("AUTOTHROTTLE_ENABLED", cfg.download_delay_s > 0, priority="project")
    settings.set("LOG_LEVEL", cfg.log_level, priority="project")
    settings.set("ECOMMERCE_DATA_DIR", str(cfg.data_dir), priority="project")
    settings.set("ECOMMERCE_RUN_ID", run_id, priority="project")
    return settings


def _is_loopback(base_url: str) -> bool:
    host = urlparse(base_url).hostname or ""
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def check_polite(delay_s: float, stores: Sequence[Store]) -> None:
    """A delay under 2 s is only allowed against loopback hosts (the offline e2e)."""
    if delay_s < MIN_DELAY_S and not all(_is_loopback(s.base_url) for s in stores):
        raise StepError(
            f"download delay {delay_s}s is under {MIN_DELAY_S}s; "
            "lower values are only allowed for loopback stores"
        )


def _aware(value: Any) -> datetime:
    if not isinstance(value, datetime):
        return utc_now()
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def store_crawl_from_stats(store: str, stats: Mapping[str, Any]) -> StoreCrawl:
    return StoreCrawl(
        store=store,
        finish_reason=str(stats.get("finish_reason", "unknown")),
        pages_archived=stats.get("archive/pages", 0),
        robots_forbidden=stats.get("robotstxt/forbidden", 0),
        http_errors=stats.get("httperror/response_ignored_count", 0),
        retries=stats.get("retry/count", 0),
        started_at=_aware(stats.get("start_time")),
        finished_at=_aware(stats.get("finish_time")),
    )


def run_crawl(
    stores: Sequence[Store], limit: int | None, run_id: str, cfg: Settings
) -> CrawlSummary:
    log = step_logger(run_id, "crawl")
    check_polite(cfg.download_delay_s, stores)
    paths = RunPaths(cfg.data_dir)
    run_dir = paths.raw_run_dir(run_id)
    if run_dir.exists():
        raise StepError(f"raw run directory already exists: {run_dir}")

    process = CrawlerProcess(build_settings(cfg, run_id), install_root_handler=False)
    crawlers = []
    for store in stores:
        crawler = process.create_crawler(ProductsSpider)
        process.crawl(crawler, store=store, limit=limit)
        crawlers.append((store, crawler))
    log.info("crawling %s (limit=%s)", ", ".join(s.name for s in stores), limit)
    process.start()

    summary = CrawlSummary(
        run_id=run_id,
        stores=[store_crawl_from_stats(s.name, c.stats.get_stats()) for s, c in crawlers],
    )
    for crawl in summary.stores:
        log.info("%s: %s, %d pages", crawl.store, crawl.finish_reason, crawl.pages_archived)
    run_dir.mkdir(parents=True, exist_ok=True)
    target = paths.raw_summary(run_id)
    tmp = target.with_name("run.json.tmp")
    tmp.write_text(summary.model_dump_json(indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, target)  # last write: its presence marks the run complete
    return summary
