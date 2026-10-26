import json
from typing import Any

from hypothesis import given
from hypothesis import strategies as st

from ecommerce_scraping.jsonld import extract_blocks, redact_page


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


def test_redact_keeps_graph() -> None:
    graph = {"@graph": [{"@type": "Product", "name": "A", "review": []}, {"@type": "WebSite"}]}
    blocks = extract_blocks(redact_page(page(ld(graph))))
    assert blocks == [{"@graph": [{"@type": "Product", "name": "A"}, {"@type": "WebSite"}]}]


def test_redact_counts_unparsable_blocks() -> None:
    html = page(
        ld({"ok": 1}),
        '<script type="application/ld+json">{bad</script>',
        '<script type="application/ld+json">[1,</script>',
    )
    out = redact_page(html)
    assert "<!-- redacted: 2 unparsable ld+json block(s) dropped -->" in out
    assert extract_blocks(out) == [{"ok": 1}]
    assert "redacted:" not in redact_page(page(ld({"ok": 1})))


def test_redact_escapes_script_end_inside_strings() -> None:
    out = redact_page(page(ld({"name": "</script><b>x</b>"})))
    assert out.count("</script>") == 1
    assert "<\\/script>" in out
    assert extract_blocks(out) == [{"name": "</script><b>x</b>"}]


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
            st.sampled_from(["review", "reviews", "name", "offers"]), kids, max_size=3
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
    out = redact_page(page(ld(tree)))
    assert not {"review", "reviews"} & keys(extract_blocks(out))
    assert redact_page(out) == out
