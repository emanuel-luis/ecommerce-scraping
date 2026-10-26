from pathlib import Path

import pytest
from scrapy.http import HtmlResponse, Request, Response, XmlResponse
from scrapy.utils.test import get_crawler

from ecommerce_scraping.jsonld import extract_blocks
from ecommerce_scraping.models import RawPage
from ecommerce_scraping.spider import ProductsSpider
from ecommerce_scraping.stores import Store

SITE = Path(__file__).parent / "fixtures" / "site"
BASE = "https://shop.example"
STORE = Store("levi", BASE)


def spider(limit: int | None = None) -> ProductsSpider:
    crawler = get_crawler(ProductsSpider)
    return ProductsSpider.from_crawler(crawler, store=STORE, limit=limit)


def sitemap_response(name: str) -> XmlResponse:
    xml = (SITE / name).read_text(encoding="utf-8").replace("{{BASE}}", BASE)
    url = f"{BASE}/{name}"
    return XmlResponse(url, body=xml.encode(), request=Request(url))


def parse(sp: ProductsSpider, name: str) -> list[str]:
    return [r.url.removeprefix(BASE) for r in sp._parse_sitemap(sitemap_response(name))]


def test_start_requests_the_store_sitemap() -> None:
    sp = spider()
    assert sp.sitemap_urls == [f"{BASE}/sitemap.xml"]
    assert sp.allowed_domains == ["shop.example"]


def test_index_follows_only_product_sitemaps() -> None:
    assert parse(spider(), "sitemap.xml") == ["/sitemap/product-0.xml", "/sitemap/product-1.xml"]


def test_index_with_limit_follows_only_the_first_product_sitemap() -> None:
    assert parse(spider(limit=3), "sitemap.xml") == ["/sitemap/product-0.xml"]


def test_urlset_keeps_only_product_urls() -> None:
    assert parse(spider(), "sitemap/product-0.xml") == [
        "/fixture-product/p",
        "/blocked-product/p",
        "/missing-product/p",
        "/no-jsonld-product/p",
        "/FIXTURE-PRODUCT/p",
        "/old-fixture-product/p",
    ]


@pytest.mark.parametrize("limit", [1, 2, 4])
def test_urlset_is_capped_by_limit_in_sitemap_order(limit: int) -> None:
    expected = [
        "/fixture-product/p",
        "/blocked-product/p",
        "/missing-product/p",
        "/no-jsonld-product/p",
    ][:limit]
    assert parse(spider(limit=limit), "sitemap/product-0.xml") == expected


def test_urlset_callbacks_are_parse_product() -> None:
    sp = spider()
    requests = list(sp._parse_sitemap(sitemap_response("sitemap/product-1.xml")))
    assert [r.callback for r in requests] == [sp.parse_product]


PAGE = """<html><head><link rel="canonical" href="https://shop.example/x/p">
<script type="application/ld+json">{"@type": "Product", "name": "Shirt",
"review": [{"author": {"name": "Fake Reviewer"}}]}</script></head>
<body>Fake Reviewer was here</body></html>"""


def html_response(url: str, redirect_urls: list[str] | None = None) -> HtmlResponse:
    meta = {"redirect_urls": redirect_urls} if redirect_urls else {}
    return HtmlResponse(url, body=PAGE.encode(), encoding="utf-8", request=Request(url, meta=meta))


def test_parse_product_yields_a_redacted_raw_page() -> None:
    url = f"{BASE}/shirt/p"
    (page,) = spider().parse_product(html_response(url))
    assert isinstance(page, RawPage)
    assert (page.store, page.url, page.final_url, page.status) == ("levi", url, url, 200)
    assert page.fetched_at.tzinfo is not None
    assert "Fake Reviewer" not in page.html
    assert extract_blocks(page.html) == [{"@type": "Product", "name": "Shirt"}]


def test_parse_product_uses_the_first_url_of_the_redirect_chain() -> None:
    old, mid, final = (f"{BASE}/{n}/p" for n in ("old", "mid", "shirt"))
    (page,) = spider().parse_product(html_response(final, [old, mid]))
    assert (page.url, page.final_url) == (old, final)


def test_parse_product_skips_a_non_text_response(caplog: pytest.LogCaptureFixture) -> None:
    url = f"{BASE}/img/p"
    binary = Response(url, body=b"\x89PNG", request=Request(url))
    assert list(spider().parse_product(binary)) == []
    assert "non-text" in caplog.text
