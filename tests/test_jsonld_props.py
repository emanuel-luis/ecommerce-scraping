from decimal import Decimal
from typing import Any, get_args

from hypothesis import given
from hypothesis import strategies as st

from ecommerce_scraping.jsonld import (
    ParseError,
    norm_availability,
    norm_price,
    norm_text,
    parse_node,
)
from ecommerce_scraping.models import Availability

json_values = st.recursive(
    st.none() | st.booleans() | st.integers() | st.floats() | st.text(max_size=12),
    lambda kids: (
        st.lists(kids, max_size=3) | st.dictionaries(st.text(max_size=4), kids, max_size=3)
    ),
    max_leaves=10,
)


@given(json_values)
def test_norm_availability_is_total(value: Any) -> None:
    assert norm_availability(value) in {None, *get_args(Availability)}


@given(
    st.sampled_from(get_args(Availability)),
    st.sampled_from(["", "http://schema.org/", "https://schema.org/", "schema.org/"]),
    st.booleans(),
)
def test_norm_availability_accepts_every_token(token: str, prefix: str, upper: bool) -> None:
    assert norm_availability(prefix + (token.upper() if upper else token)) == token


@given(json_values)
def test_norm_text_is_none_or_stripped(value: Any) -> None:
    out = norm_text(value)
    assert out is None or (out != "" and out == out.strip())


@given(json_values)
def test_norm_price_is_total(value: Any) -> None:
    out = norm_price(value)
    assert out is None or (out >= 0 and out.as_tuple().exponent == -2)


amounts = st.decimals(min_value=0, max_value=Decimal(10**7) - Decimal("0.01"), places=2)


@given(amounts)
def test_norm_price_round_trips(amount: Decimal) -> None:
    forms: list[Any] = [
        str(amount),
        f"R$ {amount:.2f}",
        float(amount),
        f"{amount:.2f}".replace(".", ","),
    ]
    if amount == amount.to_integral_value():
        forms.append(int(amount))
    assert all(norm_price(form) == amount for form in forms)


prices = amounts.map(float) | st.integers(0, 10**6) | amounts.map(str)


def offer(kids: st.SearchStrategy[Any]) -> st.SearchStrategy[Any]:
    leaf = st.fixed_dictionaries(
        {"price": prices}, optional={"@type": st.just("Offer"), "type": st.just("Offer")}
    )
    agg = st.fixed_dictionaries(
        {"offers": st.lists(kids, max_size=3)},
        optional={"@type": st.just("AggregateOffer"), "type": st.just("AggregateOffer")},
    )
    return leaf | agg


offer_trees = st.recursive(
    st.fixed_dictionaries({"price": prices}),
    lambda kids: st.lists(offer(kids), min_size=1, max_size=3) | offer(kids),
    max_leaves=8,
)


@given(offer_trees)
def test_nested_offers_keep_high_at_or_above_price(offers: Any) -> None:
    try:
        parsed = parse_node({"@type": "Product", "offers": offers}, "u")
    except ParseError:
        return  # an aggregate without any priced leaf has no price to report
    assert parsed.high_price is None or parsed.high_price >= parsed.price
