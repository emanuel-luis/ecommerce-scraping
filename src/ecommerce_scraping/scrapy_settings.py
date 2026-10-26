"""Scrapy settings as module constants; USER_AGENT and the run-specific values come from crawl.py."""

from ecommerce_scraping.middlewares import BlockedStopMiddleware
from ecommerce_scraping.pipelines import RawArchivePipeline

ROBOTSTXT_OBEY = True

CONCURRENT_REQUESTS = 8
CONCURRENT_REQUESTS_PER_DOMAIN = 1
DOWNLOAD_DELAY = 3
DOWNLOAD_DELAY_JITTER = 0  # a fixed delay: no random variation
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 3
AUTOTHROTTLE_MAX_DELAY = 60
AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0

RETRY_TIMES = 2
RETRY_HTTP_CODES = [500, 502, 503, 504, 522, 524, 408]  # no 429: BlockedStopMiddleware stops
DOWNLOAD_TIMEOUT = 30
DOWNLOAD_MAXSIZE = 10 * 1024 * 1024

COOKIES_ENABLED = False
HTTPCACHE_ENABLED = False
TELNETCONSOLE_ENABLED = False

CLOSESPIDER_TIMEOUT = 3600
CLOSESPIDER_ERRORCOUNT = 10

ITEM_PIPELINES = {RawArchivePipeline: 300}
DOWNLOADER_MIDDLEWARES = {BlockedStopMiddleware: 560}  # above RetryMiddleware (550)

LOG_LEVEL = "INFO"
