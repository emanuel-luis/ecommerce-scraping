"""JSON-LD extraction and the redaction applied before a page reaches the raw layer."""

import json
import math
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from html import escape, unescape
from typing import Any, get_args
from urllib.parse import urlsplit

from parsel import Selector

from ecommerce_scraping.models import Availability

_REVIEW_KEYS = frozenset({"review", "reviews"})
_DROPPED_NOTE = re.compile(r"<!-- redacted: (\d+) unparsable")


def _parse(sel: Selector) -> tuple[list[Any], int]:
    blocks: list[Any] = []
    dropped = 0
    for script in sel.xpath("//script[@type]"):
        if "ld+json" not in script.attrib["type"].lower():
            continue
        try:
            blocks.append(json.loads(script.xpath("string()").get() or "", strict=False))
        except ValueError:
            dropped += 1
    return blocks, dropped


def extract_blocks(html: str) -> list[Any]:
    """Every parseable ld+json block, in document order; unparsable ones are skipped."""
    return _parse(Selector(text=html))[0]


def _strip_reviews(node: Any) -> Any:
    if isinstance(node, dict):
        return {k: _strip_reviews(v) for k, v in node.items() if k not in _REVIEW_KEYS}
    if isinstance(node, list):
        return [_strip_reviews(v) for v in node]
    return node


def _canonical(sel: Selector) -> str | None:
    for link in sel.xpath("//link[@rel][@href]"):
        if "canonical" in link.attrib["rel"].lower().split():
            return link.attrib["href"]
    return None


def redact_page(html: str) -> str:
    """A minimal deterministic page: canonical link and ld+json without reviews, no body."""
    sel = Selector(text=html)
    blocks, dropped = _parse(sel)
    # Keep the count from an earlier pass so that redacting twice changes nothing.
    dropped += sum(int(n) for n in _DROPPED_NOTE.findall(html))
    canonical = _canonical(sel)
    parts = ["<!doctype html>", '<html><head><meta charset="utf-8">']
    if canonical is not None:
        parts.append(f'<link rel="canonical" href="{escape(canonical, quote=True)}">')
    for block in blocks:
        body = json.dumps(_strip_reviews(block), ensure_ascii=False, indent=2)
        parts.append(f'<script type="application/ld+json">{body.replace("</", "<\\/")}</script>')
    if dropped:
        parts.append(f"<!-- redacted: {dropped} unparsable ld+json block(s) dropped -->")
    parts.append("</head><body></body></html>")
    return "\n".join(parts) + "\n"


# --- Product parsing -------------------------------------------------------------------------


class ParseError(ValueError):
    """A page that cannot yield a product; the message is a short machine-friendly reason."""


@dataclass(frozen=True)
class ParsedProduct:
    """Fields read from one Product node; the names match ProductSnapshot on purpose."""

    url: str
    name: str | None
    sku: str | None
    mpn: str | None
    gtin: str | None
    brand: str | None
    category: str | None
    color: str | None
    material: str | None
    price: Decimal
    high_price: Decimal | None
    currency: str | None
    availability: Availability | None
    in_stock: bool | None
    offer_count: int | None
    image_url: str | None


_AVAILABILITY: dict[str, Availability] = {t.casefold(): t for t in get_args(Availability)}
_GTIN_KEYS = ("gtin", "gtin13", "gtin14", "gtin12", "gtin8")
_NUMBER = re.compile(r"[0-9.,]+")
_SEPARATOR = re.compile(r"[.,]")
_CENTS = Decimal("0.01")


def norm_text(value: Any) -> str | None:
    """Unescaped, whitespace-collapsed text; None when empty or not text-like."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        if isinstance(value, float) and not math.isfinite(value):
            return None
        value = str(value)
    if not isinstance(value, str):
        return None
    return " ".join(unescape(value).split()) or None


def norm_availability(value: Any) -> Availability | None:
    """The schema.org ItemAvailability token for `https://schema.org/X`, `X`, ... or None."""
    if not isinstance(value, str):
        return None
    return _AVAILABILITY.get(value.strip().rsplit("/", 1)[-1].casefold())


def _decimal_from_text(text: str) -> Decimal | None:
    found = _NUMBER.findall(text)
    if "-" in text or len(found) != 1:
        return None
    digits = found[0]
    last = max(digits.rfind("."), digits.rfind(","))
    if last == -1:
        return Decimal(digits)
    if len(set(_SEPARATOR.findall(digits))) == 1 and digits.count(digits[last]) > 1:
        return None  # "1.299.000": thousands separators only
    whole = _SEPARATOR.sub("", digits[:last]) or "0"
    return Decimal(f"{whole}.{_SEPARATOR.sub('', digits[last + 1 :]) or '0'}")


def norm_price(value: Any) -> Decimal | None:
    """A non-negative price at 2 dp (half up) from a number or text like 'R$ 1.299,90'."""
    if isinstance(value, bool):
        return None
    try:
        if isinstance(value, int):
            number: Decimal | None = Decimal(value)
        elif isinstance(value, float):
            number = Decimal(str(value))
        elif isinstance(value, str):
            number = _decimal_from_text(value)
        else:
            return None
        if number is None or not number.is_finite() or number < 0:
            return None
        return number.quantize(_CENTS, rounding=ROUND_HALF_UP)
    except InvalidOperation:  # more digits than the decimal context holds
        return None


def _types(node: dict[str, Any]) -> set[str]:
    found: set[str] = set()
    for key in ("@type", "type"):
        value = node.get(key)
        if isinstance(value, str):
            found.add(value)
        elif isinstance(value, list):
            found.update(v for v in value if isinstance(v, str))
    return found


def iter_products(blocks: Any) -> Iterator[dict[str, Any]]:
    """Every Product node in the blocks, walking dicts, lists and `@graph`."""
    if isinstance(blocks, list):
        for item in blocks:
            yield from iter_products(item)
    elif isinstance(blocks, dict):
        if "Product" in _types(blocks):
            yield blocks
        else:
            for value in blocks.values():
                yield from iter_products(value)


def _host(url: Any) -> str | None:
    if not isinstance(url, str):
        return None
    try:
        return urlsplit(url).hostname
    except ValueError:
        return None


def pick_product(
    products: Iterable[dict[str, Any]], preferred_host: str | None
) -> dict[str, Any] | None:
    """The first node whose `@id` or `url` is on preferred_host, else the first node."""
    nodes = list(products)
    wanted = preferred_host.lower() if preferred_host else None
    for node in nodes:
        if wanted and wanted in (_host(node.get("@id")), _host(node.get("url"))):
            return node
    return nodes[0] if nodes else None


def _brand_of(value: Any) -> str | None:
    return norm_text(value.get("name") if isinstance(value, dict) else value)


def _image_of(value: Any) -> str | None:
    if isinstance(value, dict):
        return next((u for k in ("url", "contentUrl") if (u := norm_text(value.get(k)))), None)
    if isinstance(value, list):
        return next((u for item in value if (u := _image_of(item))), None)
    return norm_text(value)


def _collect_offers(node: Any, leaves: list[dict[str, Any]], aggs: list[dict[str, Any]]) -> None:
    if isinstance(node, list):
        for item in node:
            _collect_offers(item, leaves, aggs)
    elif isinstance(node, dict):
        if "AggregateOffer" in _types(node):
            aggs.append(node)
        elif norm_price(node.get("price")) is not None:
            leaves.append(node)
        _collect_offers(node.get("offers"), leaves, aggs)


def _count_of(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isascii() and value.isdigit():
        return int(value)
    return None


def _offer_fields(offers: Any) -> dict[str, Any]:
    leaves: list[dict[str, Any]] = []
    aggs: list[dict[str, Any]] = []
    _collect_offers(offers, leaves, aggs)
    leaf_prices = [p for n in leaves if (p := norm_price(n.get("price"))) is not None]
    lows = [p for n in aggs if (p := norm_price(n.get("lowPrice"))) is not None]
    highs = [p for n in aggs if (p := norm_price(n.get("highPrice"))) is not None]
    if not lows and not leaf_prices:
        raise ParseError("no offer price")
    nodes = [*aggs, *leaves]
    tokens = [t for n in nodes if (t := norm_availability(n.get("availability")))]
    in_stock = ("InStock" in tokens) if tokens else None
    return {
        "price": min(lows + leaf_prices),
        "high_price": max(highs) if highs else max(leaf_prices) if len(leaf_prices) > 1 else None,
        "currency": next((c for n in nodes if (c := norm_text(n.get("priceCurrency")))), None),
        "availability": "InStock" if in_stock else (tokens[0] if tokens else None),
        "in_stock": in_stock,
        "offer_count": next(
            (k for n in aggs if (k := _count_of(n.get("offerCount"))) is not None),
            len(leaves) or None,
        ),
    }


def parse_node(node: dict[str, Any], page_url: str) -> ParsedProduct:
    """Read one Product node; raises ParseError when it has no usable offer price."""
    return ParsedProduct(
        url=page_url,
        name=norm_text(node.get("name")),
        sku=norm_text(node.get("sku")),
        mpn=norm_text(node.get("mpn")),
        gtin=next((g for k in _GTIN_KEYS if (g := norm_text(node.get(k)))), None),
        brand=_brand_of(node.get("brand")),
        category=norm_text(node.get("category")),
        color=norm_text(node.get("color")),
        material=norm_text(node.get("material")),
        image_url=_image_of(node.get("image")),
        **_offer_fields(node.get("offers")),
    )


def parse_product(html: str, page_url: str) -> ParsedProduct:
    """The page's product: the JSON-LD Product on the canonical host, else the first one."""
    sel = Selector(text=html)
    host = _host(_canonical(sel)) or _host(page_url)
    node = pick_product(iter_products(_parse(sel)[0]), host)
    if node is None:
        raise ParseError("no ld+json Product")
    return parse_node(node, page_url)
