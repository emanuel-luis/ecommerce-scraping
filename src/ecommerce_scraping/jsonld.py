"""JSON-LD extraction and the redaction applied before a page reaches the raw layer."""

import json
import re
from html import escape
from typing import Any

from parsel import Selector

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
