"""Pydantic contracts passed between the layers."""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, Literal, Self

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from ecommerce_scraping.runs import RUN_ID_RE


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(UTC)


def _two_places(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


UtcDatetime = Annotated[datetime, AfterValidator(_aware_utc)]
Money = Annotated[Decimal, Field(ge=0), AfterValidator(_two_places)]

Availability = Literal[
    "InStock",
    "OutOfStock",
    "PreOrder",
    "BackOrder",
    "Discontinued",
    "InStoreOnly",
    "LimitedAvailability",
    "OnlineOnly",
    "PreSale",
    "SoldOut",
    "Reserved",
    "MadeToOrder",
]


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


@dataclass(frozen=True)
class RawPage:
    """One fetched product page; the Scrapy item handed to the archive pipeline."""

    store: str
    url: str
    final_url: str
    status: int
    fetched_at: datetime
    html: str


class ManifestEntry(_Model):
    url: str
    final_url: str
    status: int
    fetched_at: UtcDatetime
    path: str  # relative to the run dir
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")  # of the stored bytes
    bytes: int = Field(ge=0)


class ProductSnapshot(_Model):
    run_id: str = Field(pattern=RUN_ID_RE.pattern)
    store: str = Field(pattern=r"^[a-z0-9-]+$")
    product_key: str = Field(min_length=1)
    url: str
    sku: str | None = None
    mpn: str | None = None
    gtin: str | None = None
    name: str = Field(min_length=1)
    brand: str | None = None
    category: str | None = None
    color: str | None = None
    material: str | None = None
    price: Money
    high_price: Money | None = None
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    availability: Availability | None = None
    in_stock: bool | None = None
    offer_count: int | None = Field(default=None, ge=1)
    image_url: str | None = None
    scraped_at: UtcDatetime
    raw_path: str

    @model_validator(mode="after")
    def _high_price_not_below_price(self) -> Self:
        if self.high_price is not None and self.high_price < self.price:
            raise ValueError("high_price must be >= price")
        return self


class Reject(_Model):
    run_id: str
    store: str
    url: str
    raw_path: str | None
    stage: Literal["parse", "validate", "duplicate"]
    reason: str
    scraped_at: UtcDatetime


class StoreCrawl(_Model):
    store: str
    finish_reason: str
    pages_archived: int = Field(ge=0)
    robots_forbidden: int = Field(ge=0)
    http_errors: int = Field(ge=0)
    retries: int = Field(ge=0)
    started_at: UtcDatetime
    finished_at: UtcDatetime


class CrawlSummary(_Model):
    run_id: str
    stores: list[StoreCrawl]


class StoreRun(StoreCrawl):
    rows_out: int = Field(ge=0)
    rejected: int = Field(ge=0)
    duplicates: int = Field(ge=0)


class RunSummary(_Model):
    run_id: str
    status: Literal["ok", "partial", "failed"]
    transformed_at: UtcDatetime
    stores: list[StoreRun]
