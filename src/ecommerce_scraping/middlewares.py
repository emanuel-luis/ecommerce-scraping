"""Downloader middleware that stops a store's crawl when the site signals a block."""

from __future__ import annotations

from typing import TYPE_CHECKING

from scrapy.exceptions import IgnoreRequest
from scrapy.utils.defer import _schedule_coro  # what Scrapy's own CloseSpider extension uses

if TYPE_CHECKING:
    from typing import Self

    from scrapy import Spider
    from scrapy.crawler import Crawler
    from scrapy.http import Request, Response

BLOCK_STATUSES = frozenset({403, 429})


class BlockedStopMiddleware:
    """On a 403 or 429 (robots.txt included) close the spider and refuse every later request."""

    def __init__(self, crawler: Crawler) -> None:
        self.crawler = crawler
        self.blocked: int | None = None

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        return cls(crawler)

    def process_request(self, request: Request, spider: Spider | None = None) -> None:
        if self.blocked is not None:
            raise IgnoreRequest(f"spider blocked ({self.blocked})")

    def process_response(
        self, request: Request, response: Response, spider: Spider | None = None
    ) -> Response:
        if response.status not in BLOCK_STATUSES:
            return response
        self.crawler.stats.inc_value(f"blocked/{response.status}")
        if self.blocked is None:
            self.blocked = response.status
            engine = self.crawler.engine
            assert engine is not None
            _schedule_coro(engine.close_spider_async(reason=f"blocked_{response.status}"))
        raise IgnoreRequest(f"blocked: HTTP {response.status} from {response.url}")
