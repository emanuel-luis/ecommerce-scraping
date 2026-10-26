"""Typer CLI: ecommerce-scraping crawl | transform | views | run | stats."""

import logging
import sys
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime
from enum import StrEnum
from typing import Annotated

import typer

from ecommerce_scraping import __version__
from ecommerce_scraping.config import Settings
from ecommerce_scraping.crawl import run_crawl
from ecommerce_scraping.models import CrawlSummary, RunSummary
from ecommerce_scraping.runs import RunPaths, StepError, new_run_id
from ecommerce_scraping.stores import Store, resolve_store
from ecommerce_scraping.transform import transform_run
from ecommerce_scraping.warehouse import create_views
from ecommerce_scraping.warehouse import stats as warehouse_stats

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Polite Scrapy ingestion pipeline for e-commerce product data.",
)
log = logging.getLogger(__name__)


class StoreName(StrEnum):
    """The --store choices; a test asserts they equal the registry keys."""

    hering = "hering"
    levi = "levi"
    tng = "tng"


StoreOpt = Annotated[
    list[StoreName] | None,
    typer.Option("--store", "-s", help="Store to crawl; repeat for several. Default: all."),
]
LimitOpt = Annotated[
    int | None,
    typer.Option(min=1, help="Product pages per store. Default: ECOMMERCE_DEFAULT_LIMIT (20)."),
]
NoLimitOpt = Annotated[
    bool, typer.Option("--no-limit", help="Crawl every product sitemap (thousands of requests).")
]
RunIdOpt = Annotated[str | None, typer.Option(help="Run to use; default: the latest crawled.")]


class _UtcFormatter(logging.Formatter):
    converter: Callable[[float | None], time.struct_time] = time.gmtime


def _version(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit


@app.callback()
def main(
    version: Annotated[bool, typer.Option("--version", callback=_version, is_eager=True)] = False,
) -> None:
    """Polite Scrapy ingestion pipeline for e-commerce product data."""
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(_UtcFormatter("%(asctime)sZ %(levelname)s %(message)s"))
    logging.basicConfig(level=Settings().log_level.upper(), handlers=[handler], force=True)


@contextmanager
def _errors() -> Iterator[None]:
    """A StepError becomes `error: <message>` on stderr and exit code 1."""
    try:
        yield
    except StepError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc


def _crawl(
    cfg: Settings,
    names: list[StoreName] | None,
    limit: int | None,
    no_limit: bool,
    run_id: str | None,
) -> CrawlSummary:
    if limit is not None and no_limit:
        raise typer.BadParameter("--limit and --no-limit are mutually exclusive")
    chosen = list(dict.fromkeys(n.value for n in names or StoreName))
    stores: list[Store] = [resolve_store(n, cfg.store_base_urls) for n in chosen]
    if no_limit:
        log.warning("--no-limit crawls every product sitemap: thousands of requests per store")
    summary = run_crawl(
        stores, None if no_limit else limit or cfg.default_limit, run_id or new_run_id(), cfg
    )
    typer.echo(summary.run_id)
    if not any(s.pages_archived for s in summary.stores):
        typer.echo("error: no store archived a page", err=True)
        raise typer.Exit(1)
    return summary


def _transform(cfg: Settings, run_id: str | None) -> None:
    summary: RunSummary = transform_run(run_id, cfg)
    for s in summary.stores:
        typer.echo(
            f"{s.store}: rows={s.rows_out} rejected={s.rejected} duplicates={s.duplicates} "
            f"finish_reason={s.finish_reason}"
        )
    typer.echo(f"status: {summary.status}")
    if summary.status == "failed":
        typer.echo(f"error: run {summary.run_id} produced no rows", err=True)
        raise typer.Exit(1)
    if summary.status == "partial":
        log.warning("run %s is partial: a store was blocked, empty or cut short", summary.run_id)


def _views(cfg: Settings) -> None:
    for name in create_views(RunPaths(cfg.data_dir)):
        typer.echo(name)


@app.command()
def crawl(
    store: StoreOpt = None,
    limit: LimitOpt = None,
    no_limit: NoLimitOpt = False,
    run_id: RunIdOpt = None,
) -> None:
    """Crawl the stores into a new raw run and print its run_id."""
    with _errors():
        _crawl(Settings(), store, limit, no_limit, run_id)


@app.command()
def transform(run_id: RunIdOpt = None) -> None:
    """Raw run -> Parquet files, rejects and a run summary."""
    with _errors():
        _transform(Settings(), run_id)


@app.command()
def views() -> None:
    """(Re)create the DuckDB views over the processed data and list them."""
    with _errors():
        _views(Settings())


@app.command()
def run(store: StoreOpt = None, limit: LimitOpt = None, no_limit: NoLimitOpt = False) -> None:
    """crawl -> transform -> views in one process."""
    cfg = Settings()
    with _errors():
        summary = _crawl(cfg, store, limit, no_limit, None)
        _transform(cfg, summary.run_id)
        _views(cfg)


def _fmt(value: object) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%SZ")
    return "" if value is None else str(value)


@app.command()
def stats() -> None:
    """Runs, snapshots, products and rejects per store."""
    with _errors():
        rows = warehouse_stats(RunPaths(Settings().data_dir))
    table = [list(rows[0]), *([_fmt(v) for v in r.values()] for r in rows)] if rows else []
    widths = [max(len(r[i]) for r in table) for i in range(len(table[0]))] if table else []
    for r in table:
        typer.echo("  ".join(c.ljust(w) for c, w in zip(r, widths, strict=True)).rstrip())
