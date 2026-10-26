import gzip
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from scrapy.utils.test import get_crawler

from ecommerce_scraping.models import ManifestEntry, RawPage
from ecommerce_scraping.pipelines import RawArchivePipeline
from ecommerce_scraping.runs import RunPaths, StepError
from ecommerce_scraping.spider import ProductsSpider
from ecommerce_scraping.stores import Store

RUN_ID = "20260103T023005Z"
FETCHED = datetime(2026, 1, 3, 2, 30, 6, tzinfo=UTC)


def make(tmp_path: Path) -> RawArchivePipeline:
    crawler = get_crawler(
        ProductsSpider, {"ECOMMERCE_DATA_DIR": str(tmp_path), "ECOMMERCE_RUN_ID": RUN_ID}
    )
    crawler.spider = ProductsSpider(store=Store("levi", "https://shop.example"))
    return RawArchivePipeline.from_crawler(crawler)


def page(url: str = "https://shop.example/a/p", html: str = "<p>café</p>") -> RawPage:
    return RawPage("levi", url, "https://shop.example/final/p", 200, FETCHED, html)


def test_archives_gzip_and_manifest(tmp_path: Path) -> None:
    pipe = make(tmp_path)
    pipe.open_spider()
    item = page()
    assert pipe.process_item(item) is item

    store_dir = RunPaths(tmp_path).raw_store_dir(RUN_ID, "levi")
    name = hashlib.sha256(item.url.encode()).hexdigest()[:16] + ".html.gz"
    stored = (store_dir / name).read_bytes()
    assert gzip.decompress(stored).decode("utf-8") == item.html

    (line,) = (store_dir / "manifest.jsonl").read_text(encoding="utf-8").splitlines()
    entry = ManifestEntry.model_validate(json.loads(line))
    assert entry.path == f"levi/{name}"
    assert (RunPaths(tmp_path).raw_run_dir(RUN_ID) / entry.path).read_bytes() == stored
    assert entry.sha256 == hashlib.sha256(stored).hexdigest()
    assert (entry.bytes, entry.url, entry.final_url, entry.fetched_at) == (
        len(stored),
        item.url,
        item.final_url,
        FETCHED,
    )
    assert pipe.crawler.stats.get_value("archive/pages") == 1
    assert not list(store_dir.glob("*.tmp"))


def test_distinct_urls_get_distinct_files_and_manifest_lines(tmp_path: Path) -> None:
    pipe = make(tmp_path)
    pipe.open_spider()
    pipe.process_item(page("https://shop.example/a/p"))
    pipe.process_item(page("https://shop.example/old-a/p"))  # same page after a redirect
    store_dir = RunPaths(tmp_path).raw_store_dir(RUN_ID, "levi")
    assert len(list(store_dir.glob("*.html.gz"))) == 2
    assert len((store_dir / "manifest.jsonl").read_text(encoding="utf-8").splitlines()) == 2


def test_bytes_are_deterministic(tmp_path: Path) -> None:
    stored = []
    for sub in ("one", "two"):
        pipe = make(tmp_path / sub)
        pipe.open_spider()
        pipe.process_item(page())
        (gz,) = RunPaths(tmp_path / sub).raw_store_dir(RUN_ID, "levi").glob("*.html.gz")
        stored.append(gz.read_bytes())
    assert stored[0] == stored[1]


def test_existing_store_dir_is_refused(tmp_path: Path) -> None:
    RunPaths(tmp_path).raw_store_dir(RUN_ID, "levi").mkdir(parents=True)
    with pytest.raises(StepError, match="already exists"):
        make(tmp_path).open_spider()
