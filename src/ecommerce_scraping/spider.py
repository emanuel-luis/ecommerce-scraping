"""Sitemap spider: robots.txt -> /sitemap.xml -> product-N.xml -> product pages."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from scrapy.http import TextResponse
from scrapy.spiders import SitemapSpider

from ecommerce_scraping.jsonld import redact_page
from ecommerce_scraping.models import RawPage
from ecommerce_scraping.runs import utc_now
from ecommerce_scraping.stores import PRODUCT_SITEMAP_RE, PRODUCT_URL_RE, Store

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

    from scrapy.http import Response


class ProductsSpider(SitemapSpider):
    name = "products"
    sitemap_follow = (PRODUCT_SITEMAP_RE,)
    sitemap_rules = ((PRODUCT_URL_RE, "parse_product"),)

    def __init__(self, store: Store, limit: int | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.store = store
        self.limit = limit
        self.allowed_domains = store.allowed_domains
        self.sitemap_urls = [store.sitemap_url]

    def sitemap_filter(self, entries: Iterable[dict[str, Any]]) -> Iterator[dict[str, Any]]:
        """Keep product sitemaps (index entries) and product URLs (urlset entries).

        With a limit: only the first product sitemap and its first `limit` URLs, in sitemap order.
        The two patterns never match the same loc, so no need to look at the Sitemap type.
        """
        sitemaps = urls = 0
        for entry in entries:
            loc = entry.get("loc") or ""
            if re.search(PRODUCT_SITEMAP_RE, loc):
                if self.limit is None or sitemaps < 1:
                    sitemaps += 1
                    yield entry
            elif re.search(PRODUCT_URL_RE, loc) and (self.limit is None or urls < self.limit):
                urls += 1
                yield entry

    def parse_product(self, response: Response) -> Iterator[RawPage]:
        if not isinstance(response, TextResponse):
            self.logger.warning("skipping non-text response: %s", response.url)
            return
        chain = response.meta.get("redirect_urls")
        yield RawPage(
            store=self.store.name,
            url=chain[0] if chain else response.url,
            final_url=response.url,
            status=response.status,
            fetched_at=utc_now(),
            html=redact_page(response.text),
        )
