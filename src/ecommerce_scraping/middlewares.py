"""Downloader middleware that stops a store's crawl when the site signals a block."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from scrapy.exceptions import IgnoreRequest
from scrapy.utils.defer import deferred_from_coro

if TYPE_CHECKING:
    from typing import Self

    from scrapy import Spider
    from scrapy.crawler import Crawler
    from scrapy.http import Request, Response
    from twisted.internet.defer import Deferred
    from twisted.python.failure import Failure

logger = logging.getLogger(__name__)

BLOCK_STATUSES = frozenset({403, 429})


class BlockedStopMiddleware:
    """On a 403 or 429 (robots.txt included) close the spider and refuse every later request."""

    def __init__(self, crawler: Crawler) -> None:
        self.crawler = crawler
        self.blocked: int | None = None
        self._closing: Deferred[Any] | None = None  # kept so the close is not garbage-collected

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
            self._closing = deferred_from_coro(
                engine.close_spider_async(reason=f"blocked_{response.status}")
            )
            self._closing.addErrback(self._log_close_failure)
        raise IgnoreRequest(f"blocked: HTTP {response.status} from {response.url}")

    @staticmethod
    def _log_close_failure(failure: Failure) -> None:
        logger.error("could not close the blocked spider: %s", failure.getErrorMessage())
