from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from ecommerce_scraping.models import ManifestEntry, ProductSnapshot, RawPage, Reject

NOW = datetime(2026, 1, 3, 2, 30, tzinfo=UTC)


def snapshot(**over: Any) -> ProductSnapshot:
    data: dict[str, Any] = {
        "run_id": "20260103T023000Z",
        "store": "levi",
        "product_key": "/jeans/p",
        "url": "https://www.levi.com.br/jeans/p",
        "name": "Jeans",
        "price": "99.9",
        "currency": "BRL",
        "scraped_at": NOW,
        "raw_path": "levi/abc.html.gz",
    }
    return ProductSnapshot(**{**data, **over})


def test_price_is_quantized_to_two_places() -> None:
    assert snapshot(price="99.9").price == Decimal("99.90")
    assert snapshot(price=Decimal("10.005")).price == Decimal("10.01")
    assert snapshot(price=10, high_price="12.345").high_price == Decimal("12.35")


def test_negative_price_rejected() -> None:
    with pytest.raises(ValidationError):
        snapshot(price="-1")


def test_high_price_below_price_rejected() -> None:
    with pytest.raises(ValidationError, match="high_price"):
        snapshot(price="10", high_price="9.99")
    assert snapshot(price="10", high_price="10").high_price == Decimal("10.00")


@pytest.mark.parametrize("currency", ["brl", "BR", "BRLX", ""])
def test_bad_currency_rejected(currency: str) -> None:
    with pytest.raises(ValidationError):
        snapshot(currency=currency)


def test_availability_and_offer_count() -> None:
    assert snapshot(availability="InStock", offer_count=1).availability == "InStock"
    with pytest.raises(ValidationError):
        snapshot(availability="http://schema.org/InStock")
    with pytest.raises(ValidationError):
        snapshot(offer_count=0)


def test_field_patterns_and_extra_forbidden() -> None:
    for bad in [{"run_id": "2026"}, {"store": "Levi"}, {"name": ""}, {"product_key": ""}]:
        with pytest.raises(ValidationError):
            snapshot(**bad)
    with pytest.raises(ValidationError):
        snapshot(surprise=1)


def test_naive_datetime_rejected_and_offset_converted_to_utc() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        snapshot(scraped_at=datetime(2026, 1, 3, 2, 30))
    local = datetime(2026, 1, 2, 23, 30, tzinfo=timezone(timedelta(hours=-3)))
    assert snapshot(scraped_at=local).scraped_at == NOW


def test_models_are_frozen() -> None:
    with pytest.raises(ValidationError):
        snapshot().name = "other"  # type: ignore[misc]


def test_reject_stage_and_manifest_sha() -> None:
    base: dict[str, Any] = {
        "run_id": "r",
        "store": "levi",
        "url": "u",
        "raw_path": None,
        "reason": "x",
        "scraped_at": NOW,
    }
    assert Reject(stage="duplicate", **base).stage == "duplicate"
    with pytest.raises(ValidationError):
        Reject(stage="other", **base)  # type: ignore[arg-type]
    entry = {
        "url": "u",
        "final_url": "u",
        "status": 200,
        "fetched_at": NOW,
        "path": "p",
        "bytes": 1,
    }
    assert ManifestEntry(sha256="a" * 64, **entry).bytes == 1  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        ManifestEntry(sha256="xyz", **entry)  # type: ignore[arg-type]


def test_raw_page_is_a_frozen_dataclass() -> None:
    page = RawPage("levi", "u", "u", 200, NOW, "<html/>")
    with pytest.raises(AttributeError):
        page.status = 404  # type: ignore[misc]
