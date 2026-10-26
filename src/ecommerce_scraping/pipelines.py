"""Item pipeline that lands redacted pages in the raw layer."""

from __future__ import annotations

import gzip
import hashlib
import os
from pathlib import Path
from typing import TYPE_CHECKING

from ecommerce_scraping.models import ManifestEntry, RawPage
from ecommerce_scraping.runs import RunPaths, StepError

if TYPE_CHECKING:
    from typing import Self

    from scrapy import Spider
    from scrapy.crawler import Crawler


class RawArchivePipeline:
    """One gzip file per page plus a manifest line; refuses to reuse a store's run directory."""

    def __init__(self, crawler: Crawler, paths: RunPaths, run_id: str) -> None:
        self.crawler = crawler
        self.paths = paths
        self.run_id = run_id
        self.run_dir = paths.raw_run_dir(run_id)
        self.store_dir: Path | None = None

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        settings = crawler.settings
        paths = RunPaths(Path(settings["ECOMMERCE_DATA_DIR"]))
        return cls(crawler, paths, settings["ECOMMERCE_RUN_ID"])

    def open_spider(self, spider: Spider | None = None) -> None:
        spider = self.crawler.spider
        assert spider is not None
        store_dir = self.paths.raw_store_dir(self.run_id, spider.store.name)  # type: ignore[attr-defined]
        if store_dir.exists():
            raise StepError(f"raw directory already exists: {store_dir}")
        store_dir.mkdir(parents=True)
        self.store_dir = store_dir

    def process_item(self, item: RawPage, spider: Spider | None = None) -> RawPage:
        assert self.store_dir is not None, "open_spider was not called"
        data = gzip.compress(item.html.encode("utf-8"), mtime=0)  # mtime=0: same bytes every run
        name = hashlib.sha256(item.url.encode("utf-8")).hexdigest()[:16] + ".html.gz"
        target = self.store_dir / name
        tmp = target.with_name(name + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, target)
        entry = ManifestEntry(
            url=item.url,
            final_url=item.final_url,
            status=item.status,
            fetched_at=item.fetched_at,
            path=target.relative_to(self.run_dir).as_posix(),
            sha256=hashlib.sha256(data).hexdigest(),
            bytes=len(data),
        )
        with (self.store_dir / "manifest.jsonl").open("a", encoding="utf-8", newline="\n") as f:
            f.write(entry.model_dump_json() + "\n")
        self.crawler.stats.inc_value("archive/pages")
        return item
