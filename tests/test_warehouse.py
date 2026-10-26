from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import duckdb
import pytest

from ecommerce_scraping.models import RunSummary, StoreRun
from ecommerce_scraping.runs import RunPaths, StepError, naive_utc, run_date
from ecommerce_scraping.schema import PRODUCTS_DDL, REJECTS_DDL
from ecommerce_scraping.warehouse import VIEWS, create_views, stats

R1 = "20261001T100000Z"
R2 = "20261002T100000Z"
R_HIDDEN = "20261003T100000Z"  # Parquet without a summary
R_FAILED = "20261004T100000Z"


def _ts(run_id: str) -> datetime:
    return datetime.strptime(run_id, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)


def _write_parquet(ddl: str, file: Path, rows: list[tuple[object, ...]], placeholders: int) -> None:
    file.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    try:
        con.execute(ddl.format(table="t"))
        marks = ", ".join("?" * placeholders)
        con.executemany(f"INSERT INTO t VALUES ({marks})", rows)
        con.execute(f"COPY t TO '{file.as_posix()}' (FORMAT parquet)")
    finally:
        con.close()


def _product(run_id: str, key: str, price: str) -> tuple[object, ...]:
    return (
        run_id, key, f"https://x.test{key}", None, None, None, f"name {key}", None, None, None,
        None, Decimal(price), None, "BRL", None, True, None, None, naive_utc(_ts(run_id)),
        "raw/x.html.gz",
    )  # fmt: skip


def _reject(run_id: str) -> tuple[object, ...]:
    return (run_id, "https://x.test/bad", None, "parse", "no json-ld", naive_utc(_ts(run_id)))


def _add_run(
    paths: RunPaths, run_id: str, store: str, prices: dict[str, str], rejects: int
) -> None:
    _write_parquet(
        PRODUCTS_DDL,
        paths.products_file(store, run_id),
        [_product(run_id, k, p) for k, p in prices.items()],
        20,
    )
    _write_parquet(REJECTS_DDL, paths.rejects_file(store, run_id), [_reject(run_id)] * rejects, 6)


def _store_run(store: str, rows: int, rejected: int) -> StoreRun:
    when = _ts(R1)
    return StoreRun(
        store=store, finish_reason="finished", pages_archived=rows + rejected,
        robots_forbidden=0, http_errors=1, retries=2, started_at=when, finished_at=when,
        rows_out=rows, rejected=rejected, duplicates=0,
    )  # fmt: skip


def _summary(paths: RunPaths, run_id: str, status: str, stores: list[StoreRun]) -> None:
    summary = RunSummary.model_validate(
        {
            "run_id": run_id,
            "status": status,
            "transformed_at": _ts(run_id),
            "stores": [s.model_dump(mode="json") for s in stores],
        }
    )
    paths.runs_dir.mkdir(parents=True, exist_ok=True)
    paths.run_summary(run_id).write_text(summary.model_dump_json(), encoding="utf-8")


@pytest.fixture
def paths(tmp_path: Path) -> RunPaths:
    p = RunPaths(tmp_path)
    for store in ("alpha", "beta"):
        _add_run(p, R1, store, {"/a/p": "10.00", "/b/p": "20.00"}, rejects=1)
        _add_run(p, R2, store, {"/a/p": "12.50"}, rejects=2)
    _add_run(p, R_HIDDEN, "alpha", {"/a/p": "99.00", "/z/p": "1.00"}, rejects=5)
    _add_run(p, R_FAILED, "alpha", {"/a/p": "77.00"}, rejects=7)
    _summary(p, R1, "ok", [_store_run("alpha", 2, 1), _store_run("beta", 2, 1)])
    _summary(p, R2, "partial", [_store_run("alpha", 1, 2), _store_run("beta", 1, 2)])
    _summary(p, R_FAILED, "failed", [_store_run("alpha", 0, 0)])
    return p


@pytest.fixture
def con(paths: RunPaths) -> Iterator[duckdb.DuckDBPyConnection]:
    create_views(paths)
    c = duckdb.connect(str(paths.warehouse), read_only=True)
    yield c
    c.close()


def test_views_exist_with_types(con: duckdb.DuckDBPyConnection) -> None:
    names = {
        r[0]
        for r in con.execute("SELECT view_name FROM duckdb_views() WHERE NOT internal").fetchall()
    }
    assert names == set(VIEWS)
    types = {r[0]: r[1] for r in con.execute("DESCRIBE product_snapshots").fetchall()}
    assert types["price"] == "DECIMAL(12,2)"
    assert types["run_date"] == "DATE"
    assert types["scraped_at"] == "TIMESTAMP"
    assert types["store"] == "VARCHAR"


def test_incomplete_runs_are_hidden(con: duckdb.DuckDBPyConnection) -> None:
    run_ids = {
        r[0] for r in con.execute("SELECT DISTINCT run_id FROM product_snapshots").fetchall()
    }
    assert run_ids == {R1, R2}
    assert con.execute("SELECT count(*) FROM rejects").fetchone() == (6,)


def test_products_latest_picks_newer_snapshot(con: duckdb.DuckDBPyConnection) -> None:
    rows = con.execute(
        "SELECT store, product_key, run_id, price FROM products_latest ORDER BY 1, 2"
    ).fetchall()
    assert rows == [
        ("alpha", "/a/p", R2, Decimal("12.50")),
        ("alpha", "/b/p", R1, Decimal("20.00")),
        ("beta", "/a/p", R2, Decimal("12.50")),
        ("beta", "/b/p", R1, Decimal("20.00")),
    ]


def test_price_history_change(con: duckdb.DuckDBPyConnection) -> None:
    rows = con.execute(
        "SELECT run_id, run_date, price_change FROM price_history"
        " WHERE store = 'alpha' AND product_key = '/a/p' ORDER BY scraped_at"
    ).fetchall()
    assert rows == [
        (R1, run_date(R1), None),
        (R2, run_date(R2), Decimal("2.50")),
    ]


def test_runs_rows_per_store(con: duckdb.DuckDBPyConnection) -> None:
    rows = con.execute("SELECT run_id, store, status FROM runs ORDER BY 1, 2").fetchall()
    assert rows == [
        (R1, "alpha", "ok"),
        (R1, "beta", "ok"),
        (R2, "alpha", "partial"),
        (R2, "beta", "partial"),
        (R_FAILED, "alpha", "failed"),
    ]
    row = con.execute(
        "SELECT transformed_at, retries, rows_out, finished_at FROM runs"
        " WHERE run_id = ? AND store = 'alpha'",
        [R1],
    ).fetchone()
    assert row == (naive_utc(_ts(R1)), 2, 2, naive_utc(_ts(R1)))


def test_no_complete_run_is_an_error(tmp_path: Path) -> None:
    paths = RunPaths(tmp_path)
    with pytest.raises(StepError, match="no transformed run yet"):
        create_views(paths)
    _summary(paths, R_FAILED, "failed", [_store_run("alpha", 0, 0)])
    with pytest.raises(StepError, match="no transformed run yet"):
        stats(paths)


def test_create_views_is_idempotent(paths: RunPaths) -> None:
    assert create_views(paths) == list(VIEWS)
    assert create_views(paths) == list(VIEWS)


def test_stats(paths: RunPaths) -> None:
    assert not paths.warehouse.exists()
    result = stats(paths)
    expected_ts = naive_utc(_ts(R2))
    assert result == [
        {
            "store": store,
            "runs": runs,
            "snapshots": 3,
            "products": 2,
            "rejects": 3,
            "last_run_id": R2,
            "last_scraped_at": expected_ts,
        }
        for store, runs in (("alpha", 3), ("beta", 2))
    ]
