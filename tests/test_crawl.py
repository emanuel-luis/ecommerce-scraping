from datetime import UTC, datetime
from pathlib import Path

import pytest

from ecommerce_scraping import scrapy_settings
from ecommerce_scraping.config import Settings
from ecommerce_scraping.crawl import build_settings, check_polite, store_crawl_from_stats
from ecommerce_scraping.middlewares import BlockedStopMiddleware
from ecommerce_scraping.pipelines import RawArchivePipeline
from ecommerce_scraping.runs import StepError
from ecommerce_scraping.stores import STORES, Store

RUN_ID = "20260103T023005Z"


def cfg(**kwargs: object) -> Settings:
    return Settings(_env_file=None, **kwargs)  # type: ignore[call-arg]


def test_module_settings_follow_the_plan() -> None:
    s = build_settings(cfg(), RUN_ID)
    assert s.getbool("ROBOTSTXT_OBEY")
    assert s.getint("CONCURRENT_REQUESTS") == 8
    assert s.getint("CONCURRENT_REQUESTS_PER_DOMAIN") == 1
    assert s.getfloat("DOWNLOAD_DELAY_JITTER") == 0
    assert s.getint("RETRY_TIMES") == 2
    assert 429 not in s.getlist("RETRY_HTTP_CODES")
    assert s.getint("DOWNLOAD_MAXSIZE") == 10 * 1024 * 1024
    assert not s.getbool("COOKIES_ENABLED")
    assert not s.getbool("HTTPCACHE_ENABLED")
    assert not s.getbool("TELNETCONSOLE_ENABLED")
    assert s.getint("CLOSESPIDER_TIMEOUT") == 3600
    assert s.getint("CLOSESPIDER_ERRORCOUNT") == 10
    assert s.getdict("ITEM_PIPELINES") == {RawArchivePipeline: 300}
    assert s.getdict("DOWNLOADER_MIDDLEWARES")[BlockedStopMiddleware] == 560
    assert scrapy_settings.RETRY_HTTP_CODES == [500, 502, 503, 504, 522, 524, 408]


def test_run_values_come_from_config(tmp_path: Path) -> None:
    s = build_settings(
        cfg(data_dir=tmp_path, download_delay_s=5, user_agent="ua/1", log_level="WARNING"), RUN_ID
    )
    assert s["USER_AGENT"] == "ua/1"
    assert s.getfloat("DOWNLOAD_DELAY") == 5
    assert s.getbool("AUTOTHROTTLE_ENABLED")
    assert s["LOG_LEVEL"] == "WARNING"
    assert s["ECOMMERCE_DATA_DIR"] == str(tmp_path)
    assert s["ECOMMERCE_RUN_ID"] == RUN_ID


def test_delay_zero_turns_autothrottle_off() -> None:
    s = build_settings(cfg(download_delay_s=0), RUN_ID)
    assert s.getfloat("DOWNLOAD_DELAY") == 0
    assert not s.getbool("AUTOTHROTTLE_ENABLED")


LOCAL = [Store("a", "http://127.0.0.1:8001"), Store("b", "http://localhost:8002")]
REMOTE = list(STORES.values())


@pytest.mark.parametrize("stores", [LOCAL, REMOTE])
def test_polite_delay_is_always_fine(stores: list[Store]) -> None:
    check_polite(2, stores)
    check_polite(3, stores)


def test_short_delay_is_allowed_for_loopback_only() -> None:
    check_polite(0, LOCAL)
    check_polite(0.5, [Store("a", "http://[::1]:9")])
    for stores in (REMOTE, [*LOCAL, REMOTE[0]]):
        with pytest.raises(StepError, match="under 2"):
            check_polite(1.9, stores)


def test_store_crawl_from_full_stats() -> None:
    start = datetime(2026, 1, 3, 2, 30, tzinfo=UTC)
    finish = datetime(2026, 1, 3, 2, 31, tzinfo=UTC)
    crawl = store_crawl_from_stats(
        "levi",
        {
            "finish_reason": "blocked_403",
            "archive/pages": 7,
            "robotstxt/forbidden": 1,
            "httperror/response_ignored_count": 2,
            "retry/count": 3,
            "start_time": start,
            "finish_time": finish,
        },
    )
    assert crawl.model_dump() == {
        "store": "levi",
        "finish_reason": "blocked_403",
        "pages_archived": 7,
        "robots_forbidden": 1,
        "http_errors": 2,
        "retries": 3,
        "started_at": start,
        "finished_at": finish,
    }


def test_store_crawl_from_empty_stats_defaults_to_zero() -> None:
    crawl = store_crawl_from_stats("tng", {})
    assert crawl.finish_reason == "unknown"
    assert (crawl.pages_archived, crawl.robots_forbidden, crawl.http_errors, crawl.retries) == (
        0,
        0,
        0,
        0,
    )
    assert crawl.started_at.tzinfo is not None
    assert crawl.finished_at.tzinfo is not None


def test_naive_stat_datetimes_are_read_as_utc() -> None:
    naive = datetime(2026, 1, 3, 2, 30)
    crawl = store_crawl_from_stats("tng", {"start_time": naive, "finish_time": naive})
    assert crawl.started_at == naive.replace(tzinfo=UTC)
