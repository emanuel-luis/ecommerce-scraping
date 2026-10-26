"""End to end: a real Scrapy crawl in a subprocess against loopback fixture servers."""

import gzip
import json
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import duckdb
import pytest
from conftest import FixtureSite

from ecommerce_scraping.runs import RunPaths

pytestmark = pytest.mark.timeout(240)

REPO_URL = "https://github.com/emanuel-luis/ecommerce-scraping"
NORMAL = ("levi", "tng")
Start = Callable[..., FixtureSite]


def cli(
    tmp_path: Path, sites: dict[str, FixtureSite], *args: str
) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("ECOMMERCE_")}
    env |= {
        "ECOMMERCE_DATA_DIR": str(tmp_path / "data"),
        "ECOMMERCE_DOWNLOAD_DELAY_S": "0",
        "ECOMMERCE_STORE_BASE_URLS": json.dumps({k: s.base for k, s in sites.items()}),
        "PYTHONIOENCODING": "utf-8",
    }
    return subprocess.run(
        [sys.executable, "-m", "ecommerce_scraping", *args],
        cwd=tmp_path,  # no repo .env
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=200,
        check=False,
    )


def sites_of(start: Start) -> dict[str, FixtureSite]:
    return {
        "hering": start("hering", mode="blocked"),
        "levi": start("levi"),
        "tng": start("tng"),
    }


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def rows(path: Path) -> list[dict[str, Any]]:
    con = duckdb.connect()
    try:
        cur = con.execute(
            f"SELECT * FROM read_parquet('{path.as_posix()}', hive_partitioning = false)"
        )
        names = [d[0] for d in cur.description]
        return sorted(
            (dict(zip(names, r, strict=True)) for r in cur.fetchall()), key=lambda r: str(r)
        )
    finally:
        con.close()


def test_run_end_to_end(start_site: Start, tmp_path: Path) -> None:
    sites = sites_of(start_site)
    result = cli(tmp_path, sites, "run", "--limit", "10")

    assert result.returncode == 0, result.stderr
    run_id = result.stdout.splitlines()[0]
    assert "blocked_403" in result.stderr

    assert sites["hering"].paths == ["/robots.txt"]
    for name in NORMAL:
        site = sites[name]
        assert site.requests
        for _path, agent in site.requests:
            assert agent.startswith("ecommerce-scraping/") and REPO_URL in agent
        for never in (
            "/blocked-product/p",
            "/second-sitemap-product/p",
            "/sitemap/product-1.xml",
            "/sitemap/category-0.xml",
        ):
            assert never not in site.paths

    paths = RunPaths(tmp_path / "data")
    crawl = {s["store"]: s for s in read_json(paths.raw_summary(run_id))["stores"]}
    assert (crawl["hering"]["finish_reason"], crawl["hering"]["pages_archived"]) == (
        "blocked_403",
        0,
    )
    for name in NORMAL:
        assert crawl[name]["robots_forbidden"] == 1 and crawl[name]["http_errors"] >= 1
        manifest = [
            json.loads(line)
            for line in (paths.raw_store_dir(run_id, name) / "manifest.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        urls = {m["url"].removeprefix(sites[name].base): m["final_url"] for m in manifest}
        base = sites[name].base
        assert len(manifest) == 4
        assert urls["/old-fixture-product/p"] == f"{base}/renamed-product/p"
        assert set(urls) == {
            "/fixture-product/p",
            "/no-jsonld-product/p",
            "/old-fixture-product/p",
            "/FIXTURE-PRODUCT/p",
        }

        products = rows(paths.products_file(name, run_id))
        assert len(products) == 2
        rejects = rows(paths.rejects_file(name, run_id))
        assert sorted(r["stage"] for r in rejects) == ["duplicate", "parse"]

    assert read_json(paths.run_summary(run_id))["status"] == "partial"

    con = duckdb.connect(str(paths.warehouse), read_only=True)
    try:
        counts = {
            view: con.execute(f"SELECT count(*) FROM {view}").fetchone()
            for view in ("product_snapshots", "products_latest", "rejects", "runs")
        }
    finally:
        con.close()
    assert counts == {
        "product_snapshots": (4,),
        "products_latest": (4,),
        "rejects": (4,),
        "runs": (3,),
    }

    for f in (tmp_path / "data").rglob("*"):
        if f.is_file():
            data = f.read_bytes()
            assert b"Zelda Synthetic" not in (gzip.decompress(data) if f.suffix == ".gz" else data)


def test_same_run_id_is_refused_and_transform_is_repeatable(
    start_site: Start, tmp_path: Path
) -> None:
    sites = {name: start_site(name) for name in NORMAL}
    first = cli(
        tmp_path,
        sites,
        "crawl",
        "-s",
        "levi",
        "-s",
        "tng",
        "--limit",
        "10",
        "--run-id",
        "20260103T000000Z",
    )
    assert first.returncode == 0, first.stderr
    again = cli(
        tmp_path,
        sites,
        "crawl",
        "-s",
        "levi",
        "-s",
        "tng",
        "--limit",
        "10",
        "--run-id",
        "20260103T000000Z",
    )
    assert again.returncode == 1 and "already exists" in again.stderr

    paths = RunPaths(tmp_path / "data")
    snapshots = []
    for _ in range(2):
        assert cli(tmp_path, sites, "transform", "--run-id", "20260103T000000Z").returncode == 0
        snapshots.append([rows(paths.products_file(n, "20260103T000000Z")) for n in NORMAL])
    assert snapshots[0] == snapshots[1] and all(len(p) == 2 for p in snapshots[0])
