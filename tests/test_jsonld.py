import json
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from ecommerce_scraping.jsonld import (
    ParsedProduct,
    ParseError,
    extract_blocks,
    iter_products,
    norm_availability,
    norm_price,
    norm_text,
    parse_node,
    parse_product,
    pick_product,
    redact_page,
)
from ecommerce_scraping.models import ProductSnapshot


def page(*scripts: str, head: str = "", body: str = "<p>secret body</p>") -> str:
    return f"<html><head>{head}{''.join(scripts)}</head><body>{body}</body></html>"


def ld(data: Any, type_: str = "application/ld+json") -> str:
    text = json.dumps(data).replace("</", "<\\/")
    return f'<script type="{type_}">{text}</script>'


PRODUCT = {
    "@type": "Product",
    "name": "Jeans",
    "offers": {
        "@type": "Offer",
        "price": 99.9,
        "review": [{"author": {"name": "Zelda Synthetic"}}],
    },
    "review": [{"author": {"name": "Zelda Synthetic"}, "reviewBody": "Zelda Synthetic loved it"}],
    "reviews": [{"author": "Zelda Synthetic"}],
}


def test_extract_blocks_is_case_insensitive_and_skips_invalid() -> None:
    html = page(
        ld({"a": 1}, "Application/LD+JSON"),
        '<script type="application/json">{"b": 2}</script>',
        '<script type="application/ld+json">{not json</script>',
        "<script>var x = 1;</script>",
        ld([{"c": 3}]),
    )
    assert extract_blocks(html) == [{"a": 1}, [{"c": 3}]]


def test_extract_blocks_tolerates_control_characters() -> None:
    html = '<script type="application/ld+json">{"name": "a\nb"}</script>'
    assert extract_blocks(html) == [{"name": "a\nb"}]


def test_extract_blocks_without_scripts() -> None:
    assert extract_blocks("") == []
    assert extract_blocks("<p>nothing</p>") == []


def test_redact_removes_reviews_and_body() -> None:
    out = redact_page(page(ld(PRODUCT)))
    assert "Zelda Synthetic" not in out
    assert "secret body" not in out
    blocks = extract_blocks(out)
    assert blocks[0]["name"] == "Jeans"
    assert blocks[0]["offers"] == {"@type": "Offer", "price": 99.9}
    assert "review" not in blocks[0]
    assert "reviews" not in blocks[0]


def test_redact_lifts_products_out_of_graph_and_drops_other_nodes() -> None:
    graph = {"@graph": [{"@type": "Product", "name": "A", "review": []}, {"@type": "WebSite"}]}
    crumbs = {"@type": "BreadcrumbList", "itemListElement": []}
    blocks = extract_blocks(redact_page(page(ld(crumbs), ld(graph))))
    assert blocks == [{"@type": "Product", "name": "A"}]


def test_redact_drops_person_and_review_nodes() -> None:
    review = {"@type": "Review", "author": {"@type": "Person", "name": "Zelda Synthetic"}}
    person = {"@type": "Person", "name": "Zelda Synthetic"}
    product = {
        "@type": "Product",
        "name": "A",
        "author": "Zelda Synthetic",
        "isRelatedTo": [person, {"@type": "Product", "name": "B"}],
        "subjectOf": review,
    }
    out = redact_page(page(ld(review), ld({"@graph": [person, product]})))
    assert "Zelda Synthetic" not in out
    assert extract_blocks(out) == [
        {"@type": "Product", "name": "A", "isRelatedTo": [{"@type": "Product", "name": "B"}]}
    ]


def test_redact_counts_unparsable_blocks() -> None:
    html = page(
        ld({"@type": "Product", "name": "ok"}),
        '<script type="application/ld+json">{bad</script>',
        '<script type="application/ld+json">[1,</script>',
    )
    out = redact_page(html)
    assert "<!-- redacted: 2 unparsable ld+json block(s) dropped -->" in out
    assert extract_blocks(out) == [{"@type": "Product", "name": "ok"}]
    assert "redacted:" not in redact_page(page(ld({"ok": 1})))


def test_redact_escapes_script_end_inside_strings() -> None:
    out = redact_page(page(ld({"@type": "Product", "name": "</script><b>x</b>"})))
    assert out.count("</script>") == 1
    assert "<\\/script>" in out
    assert extract_blocks(out) == [{"@type": "Product", "name": "</script><b>x</b>"}]


def test_redact_canonical() -> None:
    head = '<link rel="stylesheet" href="/a.css"><link REL="Canonical" href="/x?a=1&amp;b=&quot;2&quot;">'
    out = redact_page(page(ld({}), head=head))
    assert '<link rel="canonical" href="/x?a=1&amp;b=&quot;2&quot;">' in out
    assert "a.css" not in out
    assert "canonical" not in redact_page(page(ld({})))


def test_redact_shape_and_determinism() -> None:
    html = page(ld(PRODUCT), head='<link rel="canonical" href="/p">')
    out = redact_page(html)
    assert out.startswith('<!doctype html>\n<html><head><meta charset="utf-8">\n')
    assert out.endswith("</head><body></body></html>\n")
    assert redact_page(html) == out


def test_redact_is_idempotent() -> None:
    html = page(
        ld(PRODUCT),
        '<script type="application/ld+json">{bad</script>',
        ld({"name": "</script>"}),
        head='<link rel="canonical" href="/p?a=1&amp;b=2">',
    )
    once = redact_page(html)
    assert redact_page(once) == once


def test_redact_page_without_json_ld() -> None:
    assert redact_page("") == (
        '<!doctype html>\n<html><head><meta charset="utf-8">\n</head><body></body></html>\n'
    )


json_leaf = st.none() | st.booleans() | st.integers() | st.text(max_size=8)
json_tree = st.recursive(
    json_leaf,
    lambda kids: (
        st.lists(kids, max_size=3)
        | st.dictionaries(
            st.sampled_from(["review", "reviews", "author", "name", "offers"]), kids, max_size=3
        )
    ),
    max_leaves=12,
)


def keys(node: Any) -> set[str]:
    if isinstance(node, dict):
        return set(node) | {k for v in node.values() for k in keys(v)}
    if isinstance(node, list):
        return {k for v in node for k in keys(v)}
    return set()


@given(json_tree)
def test_redacted_output_never_has_review_keys(tree: Any) -> None:
    out = redact_page(page(ld({"@type": "Product", "data": tree}), ld(tree)))
    assert not {"review", "reviews", "author"} & keys(extract_blocks(out))
    assert redact_page(out) == out


PAGES = Path(__file__).parent / "fixtures" / "pages"


def parse_fixture(name: str, url: str = "http://127.0.0.1:8000/x/p") -> ParsedProduct:
    return parse_product((PAGES / f"{name}.html").read_text(encoding="utf-8"), url)


def test_levi() -> None:
    p = parse_fixture("levi")
    assert p.url == "http://127.0.0.1:8000/x/p"
    assert p.name == "Camiseta Levi's® Perfect Graphic Tee"
    assert p.brand == "Levi's"
    assert (p.sku, p.mpn, p.gtin) == ("29869", None, "7891234041197")
    assert p.category == "Feminino"
    assert p.image_url is not None
    assert p.image_url.endswith("LB0010208_1.jpg?v=638901036276700000")
    assert (p.price, p.high_price, p.currency) == (Decimal("169.90"), None, "BRL")
    assert (p.availability, p.in_stock, p.offer_count) == ("InStock", True, 1)


def test_tng_prefers_the_public_host_block() -> None:
    p = parse_fixture("tng")
    assert (p.sku, p.mpn, p.gtin) == ("00475289", "BNMCIS309501", "00475289")
    assert p.price == Decimal("99.99")
    assert p.high_price == Decimal("99.99")
    assert (p.in_stock, p.offer_count) == (True, 1)


def test_tng_first_block_when_no_host_matches() -> None:
    html = (PAGES / "tng.html").read_text(encoding="utf-8").replace('rel="canonical"', 'rel="x"')
    p = parse_product(html, "http://127.0.0.1:8000/p")
    assert (p.sku, p.gtin) == ("475289", "30950")  # the myvtex block, gtin13


def test_hering_aggregate_typed_with_type() -> None:
    p = parse_fixture("hering")
    assert p.name == "Calça Básica Feminina Jogger Em Moletom Peluciado - Preto"
    assert p.category == "Roupas e Acessórios > Vestuário > Calças > Jogger"
    assert (p.color, p.material, p.mpn, p.sku) == ("PRETO", "100% ALGODAO", "05V2N10EN", "83")
    assert (p.price, p.high_price, p.currency) == (Decimal("99.99"), Decimal("99.99"), "BRL")
    assert (p.availability, p.in_stock, p.offer_count) == ("OutOfStock", False, 5)


def test_damyller_http_availability_and_integer_price() -> None:
    p = parse_fixture("damyller")
    assert p.price == Decimal("299.00")
    assert p.price.as_tuple().exponent == -2
    # four nested offers are out of stock but one is in stock: any InStock wins
    assert (p.availability, p.in_stock, p.offer_count) == ("InStock", True, 5)


@pytest.mark.parametrize("name", ["levi", "tng", "hering", "damyller"])
def test_fixtures_build_snapshots(name: str) -> None:
    ProductSnapshot(
        **asdict(parse_fixture(name)),
        run_id="20261026T000000Z",
        store="s",
        product_key="/k",
        scraped_at=datetime(2026, 10, 26, tzinfo=UTC),
        raw_path="r",
    )


@pytest.mark.parametrize("name", ["synthetic_no_jsonld", "synthetic_invalid_json"])
def test_synthetic_pages_without_a_product(name: str) -> None:
    with pytest.raises(ParseError, match="no ld\\+json Product"):
        parse_fixture(name)


def test_synthetic_graph_only() -> None:
    p = parse_fixture("synthetic_graph_only", "https://shop.example.test/graph-jacket/p")
    assert (p.name, p.sku, p.brand) == ("Graph Jacket", "GJ-1", "Synthetic Brand")
    assert (p.price, p.currency, p.in_stock) == (Decimal("1299.90"), "BRL", True)
    assert p.image_url == "https://img.example.test/gj.jpg"


def test_synthetic_reviews_never_leak() -> None:
    html = (PAGES / "synthetic_reviews.html").read_text(encoding="utf-8")
    assert "Zelda Synthetic" in html
    assert "Zelda Synthetic" not in redact_page(html)
    parsed = parse_product(html, "https://shop.example.test/review-hoodie/p")
    assert "Zelda Synthetic" not in repr(asdict(parsed))
    assert parsed.price == Decimal("149.90")


@pytest.mark.parametrize(
    "offers", [None, {}, {"@type": "Offer", "price": "free"}, {"@type": "AggregateOffer"}]
)
def test_no_offer_price(offers: Any) -> None:
    with pytest.raises(ParseError, match="no offer price"):
        parse_node({"@type": "Product", "offers": offers}, "u")


def test_iter_and_pick_product() -> None:
    a = {"@type": ["Thing", "Product"], "@id": "https://A.test/p"}
    b = {"type": "Product", "url": "https://b.test/p"}
    blocks = [{"@graph": [{"x": a}, {"@type": "WebSite"}]}, [b, {"@id": 3}]]
    assert list(iter_products(blocks)) == [a, b]
    assert pick_product([a, b], "B.TEST") is b
    assert pick_product([a, b], "none.test") is a
    assert pick_product([a, b], None) is a
    assert pick_product([], "b.test") is None
    bad = {"@id": "http://[bad"}
    assert pick_product([bad], "b.test") is bad


def _offers(value: Any) -> ParsedProduct:
    return parse_node({"@type": "Product", "name": "n", "offers": value}, "u")


def test_offer_list_without_types() -> None:
    p = _offers([{"price": "10"}, {"@type": "Offer", "price": 5, "priceCurrency": "BRL"}])
    assert (p.price, p.high_price, p.currency) == (Decimal("5.00"), Decimal("10.00"), "BRL")
    assert (p.in_stock, p.availability, p.offer_count) == (None, None, 2)


def test_aggregate_with_nested_offers_only() -> None:
    p = _offers(
        {
            "@type": "AggregateOffer",
            "offerCount": "7",
            "offers": [{"price": 3, "availability": "SoldOut"}, {"price": 4}],
        }
    )
    assert (p.price, p.high_price, p.offer_count) == (Decimal(3), Decimal(4), 7)
    assert (p.in_stock, p.availability) == (False, "SoldOut")


def test_aggregate_with_low_price_only() -> None:
    p = _offers({"@type": "AggregateOffer", "lowPrice": 1, "offerCount": True})
    assert (p.price, p.high_price, p.offer_count) == (Decimal(1), None, None)


def test_text_fields() -> None:
    p = parse_node(
        {
            "@type": "Product",
            "name": " A&amp;B \n c ",
            "brand": "  Acme ",
            "image": [{}, {"contentUrl": "http://i/1"}],
            "gtin8": "123",
            "gtin13": "",
            "mpn": "",
            "offers": {"price": 1},
        },
        "u",
    )
    assert (p.name, p.brand, p.image_url) == ("A&B c", "Acme", "http://i/1")
    assert (p.gtin, p.mpn) == ("123", None)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("R$ 1.299,90", "1299.90"),
        ("169.9", "169.90"),
        ("299", "299.00"),
        ("1,5", "1.50"),
        ("1.299,9", "1299.90"),
        ("1,299.90", "1299.90"),
        ("0.005", "0.01"),
        (1e-05, "0.00"),
        (12.5, "12.50"),
        (".5", "0.50"),
        (True, None),
        ("-5", None),
        (-1, None),
        ("1.299.000", None),
        ("1,2,3", None),
        ("10 20", None),
        ("abc", None),
        ("", None),
        (float("nan"), None),
        (float("inf"), None),
        (10**40, None),
        (None, None),
        ([1], None),
    ],
)
def test_norm_price(raw: Any, expected: str | None) -> None:
    assert norm_price(raw) == (None if expected is None else Decimal(expected))


def test_norm_text_and_availability_examples() -> None:
    assert norm_text(3) == "3"
    assert norm_text(1.5) == "1.5"
    assert norm_text(True) is None
    assert norm_text(float("nan")) is None
    assert norm_text("  ") is None
    assert norm_text({}) is None
    assert norm_availability("HTTP://schema.org/instock") == "InStock"
    assert norm_availability("schema.org/PreOrder") == "PreOrder"
    assert norm_availability(" soldout ") == "SoldOut"
    assert norm_availability("Maybe") is None
    assert norm_availability(None) is None
