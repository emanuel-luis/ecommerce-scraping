import asyncio
from collections.abc import Coroutine
from types import SimpleNamespace
from typing import Any

import pytest
from scrapy.exceptions import IgnoreRequest
from scrapy.http import Request, Response
from scrapy.utils.test import get_crawler
from twisted.internet import defer

from ecommerce_scraping import middlewares
from ecommerce_scraping.middlewares import BlockedStopMiddleware

URL = "https://shop.example/a/p"


class Harness:
    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.reasons: list[str] = []

        async def close_spider_async(*, reason: str) -> None:
            self.reasons.append(reason)

        def run(coro: Coroutine[Any, Any, None]) -> defer.Deferred[None]:
            asyncio.run(coro)
            return defer.succeed(None)

        self.crawler = get_crawler()
        self.crawler.engine = SimpleNamespace(close_spider_async=close_spider_async)  # type: ignore[assignment]
        monkeypatch.setattr(middlewares, "deferred_from_coro", run)
        self.mw = BlockedStopMiddleware.from_crawler(self.crawler)

    def respond(self, url: str, status: int) -> Response:
        request = Request(url)
        return self.mw.process_response(request, Response(url, status=status, request=request))


@pytest.fixture
def harness(monkeypatch: pytest.MonkeyPatch) -> Harness:
    return Harness(monkeypatch)


@pytest.mark.parametrize("status", [200, 301, 404, 500])
def test_other_statuses_pass_through(harness: Harness, status: int) -> None:
    assert harness.respond(URL, status).status == status
    assert harness.reasons == []
    harness.mw.process_request(Request(URL))  # still allowed


@pytest.mark.parametrize("url", [URL, "https://shop.example/robots.txt"])
@pytest.mark.parametrize("status", [403, 429])
def test_block_closes_the_spider_and_refuses_later_requests(
    harness: Harness, status: int, url: str
) -> None:
    with pytest.raises(IgnoreRequest):
        harness.respond(url, status)
    assert harness.reasons == [f"blocked_{status}"]
    assert harness.crawler.stats.get_value(f"blocked/{status}") == 1
    with pytest.raises(IgnoreRequest):
        harness.mw.process_request(Request("https://shop.example/b/p"))


def test_a_second_block_is_counted_but_closes_only_once(harness: Harness) -> None:
    for status in (403, 429):
        with pytest.raises(IgnoreRequest):
            harness.respond(URL, status)
    assert harness.reasons == ["blocked_403"]
    assert harness.crawler.stats.get_value("blocked/429") == 1
