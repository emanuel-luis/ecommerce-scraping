import json
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from ecommerce_scraping.runs import (
    RunPaths,
    latest_crawled_run,
    latest_transformed_run,
    naive_utc,
    new_run_id,
    run_date,
    step_logger,
)


def test_new_run_id_is_utc_and_sortable() -> None:
    tz = timezone(timedelta(hours=-3))
    assert new_run_id(datetime(2026, 1, 2, 23, 30, 5, tzinfo=tz)) == "20260103T023005Z"
    assert new_run_id() <= new_run_id()


def test_run_date_parses_and_validates() -> None:
    assert run_date("20260103T023005Z") == date(2026, 1, 3)
    for bad in ["", "2026-01-03", "20260103T023005", "20261303T000000Z"]:
        with pytest.raises(ValueError, match="invalid run id"):
            run_date(bad)


def test_naive_utc_converts_to_utc_wall_clock() -> None:
    tz = timezone(timedelta(hours=2))
    assert naive_utc(datetime(2026, 1, 1, 10, tzinfo=tz)) == datetime(2026, 1, 1, 8)
    assert naive_utc(datetime(2026, 1, 1, 10, tzinfo=UTC)).tzinfo is None


def test_layout() -> None:
    p = RunPaths(Path("d"))
    rid = "20260103T023005Z"
    assert p.raw_run_dir(rid) == Path("d/raw") / rid
    assert p.raw_store_dir(rid, "levi") == Path("d/raw") / rid / "levi"
    assert p.raw_summary(rid) == Path("d/raw") / rid / "run.json"
    assert p.run_summary(rid) == Path("d/processed/_runs") / f"{rid}.json"
    assert p.runs_dir == Path("d/processed/_runs")
    assert p.warehouse == Path("d/warehouse.duckdb")
    part = "store=tng/run_date=2026-01-03"
    assert p.products_file("tng", rid) == Path("d/processed/products") / part / f"{rid}.parquet"
    assert p.rejects_file("tng", rid) == Path("d/processed/rejects") / part / f"{rid}.parquet"


def test_latest_crawled_run_needs_a_parsable_run_json(tmp_path: Path) -> None:
    paths = RunPaths(tmp_path)
    assert latest_crawled_run(paths) is None
    for rid, text in [
        ("20260101T000000Z", "{}"),
        ("20260102T000000Z", json.dumps({"run_id": "x"})),
        ("20260103T000000Z", None),  # still running or crashed
        ("20260104T000000Z", "{not json"),
        ("20260105T000000Z", "[]"),
    ]:
        paths.raw_run_dir(rid).mkdir(parents=True)
        if text is not None:
            paths.raw_summary(rid).write_text(text, encoding="utf-8")
    assert latest_crawled_run(paths) == "20260102T000000Z"


def test_latest_transformed_run_accepts_ok_and_partial_only(tmp_path: Path) -> None:
    paths = RunPaths(tmp_path)
    assert latest_transformed_run(paths) is None
    paths.runs_dir.mkdir(parents=True)
    for rid, text in [
        ("20260101T000000Z", json.dumps({"status": "ok"})),
        ("20260102T000000Z", json.dumps({"status": "partial"})),
        ("20260103T000000Z", json.dumps({"status": "failed"})),
        ("20260104T000000Z", "{not json"),
    ]:
        paths.run_summary(rid).write_text(text, encoding="utf-8")
    assert latest_transformed_run(paths) == "20260102T000000Z"


def test_step_logger_prefixes_run_and_step(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level("INFO", logger="ecommerce_scraping"):
        step_logger("20260101T000000Z", "crawl").info("hello")
    assert "run_id=20260101T000000Z step=crawl hello" in caplog.text
