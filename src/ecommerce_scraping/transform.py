"""Transform step: a raw run -> validated, deduplicated Parquet files, rejects and a run summary."""

import gzip
import hashlib
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

import duckdb
from pydantic import ValidationError

from ecommerce_scraping.config import Settings
from ecommerce_scraping.jsonld import ParseError, parse_product
from ecommerce_scraping.models import (
    CrawlSummary,
    ManifestEntry,
    ProductSnapshot,
    Reject,
    RunSummary,
    StoreCrawl,
    StoreRun,
)
from ecommerce_scraping.runs import (
    RunPaths,
    StepError,
    latest_crawled_run,
    naive_utc,
    step_logger,
    utc_now,
)
from ecommerce_scraping.schema import (
    PRODUCT_COLUMNS,
    PRODUCTS_DDL,
    REJECT_COLUMNS,
    REJECTS_DDL,
)

_REASON_CAP = 300


def product_key(url: str) -> str:
    """Lowercased path of the URL without query, fragment and trailing slash; "/" when empty."""
    return urlsplit(url).path.lower().rstrip("/") or "/"


def _reason(error: ValidationError) -> str:
    parts = [f"{'.'.join(map(str, e['loc'])) or 'row'}: {e['msg']}" for e in error.errors()]
    return "; ".join(parts)[:_REASON_CAP]


def _read_manifest(path: Path) -> list[ManifestEntry]:
    if not path.is_file():
        return []
    entries: list[ManifestEntry] = []
    with path.open(encoding="utf-8") as f:
        for number, line in enumerate(f, start=1):
            if not line.strip():
                continue
            try:
                entries.append(ManifestEntry.model_validate_json(line))
            except ValueError as exc:
                raise StepError(f"corrupt manifest line {number} in {path}: {exc}") from exc
    return sorted(entries, key=lambda e: (e.fetched_at, e.url))


def _write_parquet(
    path: Path, ddl: str, columns: tuple[str, ...], rows: list[tuple[Any, ...]], order: str
) -> None:
    """COPY the rows to a temp file next to the target, then replace it (atomic on one volume)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")  # does not end in .parquet: globs never see it
    con = duckdb.connect()
    try:
        con.execute(ddl.format(table="t"))
        if rows:
            marks = ",".join("?" * len(columns))
            con.executemany(f"INSERT INTO t ({','.join(columns)}) VALUES ({marks})", rows)
        con.execute(
            f"COPY (SELECT * FROM t ORDER BY {order}) TO '{tmp.as_posix()}' "
            "(FORMAT parquet, COMPRESSION zstd)"
        )
    finally:
        con.close()
    os.replace(tmp, path)


def _product_row(p: ProductSnapshot) -> tuple[Any, ...]:
    values = p.model_dump()
    values["scraped_at"] = naive_utc(p.scraped_at)
    return tuple(values[c] for c in PRODUCT_COLUMNS)


def _reject_row(r: Reject) -> tuple[Any, ...]:
    values = r.model_dump()
    values["scraped_at"] = naive_utc(r.scraped_at)
    return tuple(values[c] for c in REJECT_COLUMNS)


def _load_summary(paths: RunPaths, run_id: str) -> CrawlSummary:
    try:
        return CrawlSummary.model_validate_json(
            paths.raw_summary(run_id).read_text(encoding="utf-8")
        )
    except (OSError, ValueError) as exc:
        raise StepError(f"crawl not finished: no valid run.json for {run_id}") from exc


def _transform_store(
    paths: RunPaths, run_id: str, crawl: StoreCrawl
) -> tuple[list[ProductSnapshot], list[Reject], int]:
    store = crawl.store
    entries = _read_manifest(paths.raw_store_dir(run_id, store) / "manifest.jsonl")
    if len(entries) != crawl.pages_archived:
        raise StepError(
            f"{store}: manifest has {len(entries)} lines but the crawl archived "
            f"{crawl.pages_archived} pages"
        )
    kept: dict[str, ProductSnapshot] = {}
    rejects: list[Reject] = []
    duplicates = 0

    for entry in entries:

        def reject(
            stage: Literal["parse", "validate", "duplicate"],
            reason: str,
            entry: ManifestEntry = entry,
        ) -> None:
            rejects.append(
                Reject(
                    run_id=run_id,
                    store=store,
                    url=entry.url,
                    raw_path=entry.path,
                    stage=stage,
                    reason=reason,
                    scraped_at=entry.fetched_at,
                )
            )

        try:
            stored = (paths.raw_run_dir(run_id) / entry.path).read_bytes()
        except OSError as exc:
            reject("parse", f"raw file unreadable: {exc.__class__.__name__}")
            continue
        if hashlib.sha256(stored).hexdigest() != entry.sha256:
            reject("parse", "raw checksum mismatch")
            continue
        try:
            html = gzip.decompress(stored).decode("utf-8")
            parsed = parse_product(html, entry.final_url)
        except (OSError, EOFError, UnicodeDecodeError, ParseError) as exc:
            # gzip.BadGzipFile is an OSError
            reject("parse", str(exc) or exc.__class__.__name__)
            continue
        key = product_key(entry.final_url)
        try:
            snapshot = ProductSnapshot(
                **asdict(parsed),
                run_id=run_id,
                store=store,
                product_key=key,
                scraped_at=entry.fetched_at,
                raw_path=entry.path,
            )
        except ValidationError as exc:
            reject("validate", _reason(exc))
            continue
        if key in kept:
            duplicates += 1
            reject("duplicate", f"duplicate of {kept[key].url}")
            continue
        kept[key] = snapshot

    return list(kept.values()), rejects, duplicates


def transform_run(run_id: str | None, cfg: Settings) -> RunSummary:
    paths = RunPaths(cfg.data_dir)
    if run_id is None:
        run_id = latest_crawled_run(paths)
        if run_id is None:
            raise StepError("no crawled run found: run the crawl step first")
    crawl_summary = _load_summary(paths, run_id)
    log = step_logger(run_id, "transform")
    # The summary is the completion marker: drop a stale one before writing anything.
    paths.run_summary(run_id).unlink(missing_ok=True)

    stores: list[StoreRun] = []
    for crawl in crawl_summary.stores:
        products, rejects, duplicates = _transform_store(paths, run_id, crawl)
        _write_parquet(
            paths.products_file(crawl.store, run_id),
            PRODUCTS_DDL,
            PRODUCT_COLUMNS,
            [_product_row(p) for p in products],
            "product_key",
        )
        _write_parquet(
            paths.rejects_file(crawl.store, run_id),
            REJECTS_DDL,
            REJECT_COLUMNS,
            [_reject_row(r) for r in rejects],
            "url, stage",
        )
        store_run = StoreRun(
            **crawl.model_dump(),
            rows_out=len(products),
            rejected=len(rejects) - duplicates,
            duplicates=duplicates,
        )
        log.info(
            "store=%s rows_out=%d rejected=%d duplicates=%d",
            crawl.store,
            store_run.rows_out,
            store_run.rejected,
            store_run.duplicates,
        )
        stores.append(store_run)

    if not any(s.rows_out > 0 for s in stores):
        status: Literal["ok", "partial", "failed"] = "failed"
    elif any(s.rows_out == 0 or s.finish_reason != "finished" for s in stores):
        status = "partial"
    else:
        status = "ok"
    summary = RunSummary(run_id=run_id, status=status, transformed_at=utc_now(), stores=stores)

    target = paths.run_summary(run_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(summary.model_dump_json(indent=2), encoding="utf-8")
    os.replace(tmp, target)
    log.info("status=%s", status)
    return summary
