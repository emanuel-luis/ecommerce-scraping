import re

import duckdb

from ecommerce_scraping.models import ProductSnapshot, Reject
from ecommerce_scraping.schema import PRODUCT_COLUMNS, PRODUCTS_DDL, REJECT_COLUMNS, REJECTS_DDL

PARTITION_COLUMNS = {"store"}


def _ddl_columns(ddl: str) -> tuple[str, ...]:
    con = duckdb.connect()
    con.execute(ddl.format(table="t"))
    return tuple(row[0] for row in con.execute("DESCRIBE t").fetchall())


def test_product_columns_match_the_contract_minus_partition_columns() -> None:
    assert set(PRODUCT_COLUMNS) == set(ProductSnapshot.model_fields) - PARTITION_COLUMNS
    assert len(PRODUCT_COLUMNS) == len(set(PRODUCT_COLUMNS))


def test_reject_columns_match_the_contract_minus_partition_columns() -> None:
    assert set(REJECT_COLUMNS) == set(Reject.model_fields) - PARTITION_COLUMNS


def test_ddl_declares_the_columns_in_order() -> None:
    assert _ddl_columns(PRODUCTS_DDL) == PRODUCT_COLUMNS
    assert _ddl_columns(REJECTS_DDL) == REJECT_COLUMNS


def test_ddl_has_no_partition_columns() -> None:
    for ddl in (PRODUCTS_DDL, REJECTS_DDL):
        assert not re.search(r"\b(store|run_date)\b", ddl)
