"""Column contracts of the processed Parquet files.

`store` and `run_date` are partition columns: they live in the directory names
(`store=<s>/run_date=<d>/`), never inside the files, so hive-partitioned reads see them once.
"""

PRODUCT_COLUMNS: tuple[str, ...] = (
    "run_id",
    "product_key",
    "url",
    "sku",
    "mpn",
    "gtin",
    "name",
    "brand",
    "category",
    "color",
    "material",
    "price",
    "high_price",
    "currency",
    "availability",
    "in_stock",
    "offer_count",
    "image_url",
    "scraped_at",
    "raw_path",
)

REJECT_COLUMNS: tuple[str, ...] = (
    "run_id",
    "url",
    "raw_path",
    "stage",
    "reason",
    "scraped_at",
)

# Timestamps are TIMESTAMP holding UTC wall-clock time (see runs.naive_utc).
PRODUCTS_DDL = """
CREATE TABLE {table} (
    run_id VARCHAR NOT NULL,
    product_key VARCHAR NOT NULL,
    url VARCHAR NOT NULL,
    sku VARCHAR,
    mpn VARCHAR,
    gtin VARCHAR,
    name VARCHAR NOT NULL,
    brand VARCHAR,
    category VARCHAR,
    color VARCHAR,
    material VARCHAR,
    price DECIMAL(12, 2) NOT NULL,
    high_price DECIMAL(12, 2),
    currency VARCHAR NOT NULL,
    availability VARCHAR,
    in_stock BOOLEAN,
    offer_count INTEGER,
    image_url VARCHAR,
    scraped_at TIMESTAMP NOT NULL,
    raw_path VARCHAR NOT NULL
)
"""

REJECTS_DDL = """
CREATE TABLE {table} (
    run_id VARCHAR NOT NULL,
    url VARCHAR NOT NULL,
    raw_path VARCHAR,
    stage VARCHAR NOT NULL,
    reason VARCHAR NOT NULL,
    scraped_at TIMESTAMP NOT NULL
)
"""
