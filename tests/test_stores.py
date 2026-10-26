import re

import pytest

from ecommerce_scraping.stores import PRODUCT_SITEMAP_RE, PRODUCT_URL_RE, STORES, resolve_store


def test_registry() -> None:
    assert sorted(STORES) == ["hering", "levi", "tng"]
    levi = STORES["levi"]
    assert levi.sitemap_url == "https://www.levi.com.br/sitemap.xml"
    assert levi.allowed_domains == ["www.levi.com.br"]


def test_resolve_store_override_strips_slash_and_port_is_not_a_domain() -> None:
    store = resolve_store("tng", {"tng": "http://127.0.0.1:8001/"})
    assert store.base_url == "http://127.0.0.1:8001"
    assert store.sitemap_url == "http://127.0.0.1:8001/sitemap.xml"
    assert store.allowed_domains == ["127.0.0.1"]
    assert resolve_store("tng", {"levi": "http://x"}) == STORES["tng"]


def test_resolve_unknown_store() -> None:
    with pytest.raises(ValueError, match="unknown store 'nope'"):
        resolve_store("nope", {})


def test_url_patterns() -> None:
    assert re.search(PRODUCT_SITEMAP_RE, "https://h/sitemap/product-12.xml")
    assert not re.search(PRODUCT_SITEMAP_RE, "https://h/sitemap/category-1.xml")
    assert re.search(PRODUCT_URL_RE, "https://h/blue-jeans/p")
    assert not re.search(PRODUCT_URL_RE, "https://h/blue-jeans/p?x=1")
