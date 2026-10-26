import gzip
import hashlib
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb
import pytest

from ecommerce_scraping.config import Settings
from ecommerce_scraping.jsonld import redact_page
from ecommerce_scraping.models import CrawlSummary, ManifestEntry, RunSummary, StoreCrawl
from ecommerce_scraping.runs import RunPaths, StepError
from ecommerce_scraping.schema import PRODUCT_COLUMNS, REJECT_COLUMNS
from ecommerce_scraping.transform import product_key, transform_run

RUN_ID = "20260103T230005Z"
T0 = datetime(2026, 1, 3, 23, 0, 6, tzinfo=UTC)
PAGES = Path(__file__).parent / "fixtures" / "pages"
LEVI_URL = "https://www.levi.com.br/camiseta-levi-s-perfect-graphic-tee-lb0010208/p"
TNG_URL = "https://www.tng.com.br/cinto-social-giratorio-bnmcis30950/p"

Page = tuple[str, str, str]  # url, final_url, html


def fixture(name: str) -> str:
    return (PAGES / name).read_text(encoding="utf-8")


def product_html(offer: dict[str, Any], canonical: str = "https://shop.example.test/x/p") -> str:
    node = {"@context": "https://schema.org", "@type": "Product", "name": "Tee", "offers": offer}
    return (
        f'<html><head><link rel="canonical" href="{canonical}">'
        f'<script type="application/ld+json">{json.dumps(node)}</script></head></html>'
    )


def write_run(
    root: Path,
    stores: dict[str, list[Page]],
    run_id: str = RUN_ID,
    reasons: dict[str, str] | None = None,
    summary: bool = True,
) -> Settings:
    paths = RunPaths(root)
    run_dir = paths.raw_run_dir(run_id)
    crawls = []
    for store, pages in stores.items():
        store_dir = paths.raw_store_dir(run_id, store)
        store_dir.mkdir(parents=True)
        lines = []
        for i, (url, final_url, html) in enumerate(pages):
            data = gzip.compress(redact_page(html).encode("utf-8"), mtime=0)
            target = store_dir / f"{i}.html.gz"
            target.write_bytes(data)
            entry = ManifestEntry(
                url=url,
                final_url=final_url,
                status=200,
                fetched_at=T0 + timedelta(seconds=i),
                path=target.relative_to(run_dir).as_posix(),
                sha256=hashlib.sha256(data).hexdigest(),
                bytes=len(data),
            )
            lines.append(entry.model_dump_json())
        (store_dir / "manifest.jsonl").write_text(
            "".join(x + "\n" for x in lines), encoding="utf-8"
        )
        crawls.append(
            StoreCrawl(
                store=store,
                finish_reason=(reasons or {}).get(store, "finished"),
                pages_archived=len(pages),
                robots_forbidden=0,
                http_errors=0,
                retries=0,
                started_at=T0,
                finished_at=T0,
            )
        )
    if summary:
        paths.raw_summary(run_id).write_text(
            CrawlSummary(run_id=run_id, stores=crawls).model_dump_json(), encoding="utf-8"
        )
    return Settings(data_dir=root)


def good() -> dict[str, list[Page]]:
    return {
        "levi": [(LEVI_URL, LEVI_URL, fixture("levi.html"))],
        "tng": [(TNG_URL, TNG_URL, fixture("tng.html"))],
    }


def read(path: Path) -> list[dict[str, Any]]:
    con = duckdb.connect()
    cur = con.execute(f"SELECT * FROM read_parquet('{path.as_posix()}', hive_partitioning = false)")
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]


def test_happy_path(tmp_path: Path) -> None:
    cfg = write_run(tmp_path, good())
    summary = transform_run(RUN_ID, cfg)
    paths = RunPaths(tmp_path)

    assert summary.status == "ok"
    assert [(s.store, s.rows_out, s.rejected, s.duplicates) for s in summary.stores] == [
        ("levi", 1, 0, 0),
        ("tng", 1, 0, 0),
    ]
    (row,) = read(paths.products_file("levi", RUN_ID))
    assert tuple(row) == PRODUCT_COLUMNS
    assert row["product_key"] == "/camiseta-levi-s-perfect-graphic-tee-lb0010208/p"
    assert row["currency"] == "BRL"
    assert isinstance(row["price"], Decimal)
    assert row["scraped_at"] == T0.replace(tzinfo=None)
    assert row["raw_path"] == "levi/0.html.gz"
    assert RunSummary.model_validate_json(paths.run_summary(RUN_ID).read_text("utf-8")) == summary

    con = duckdb.connect()
    types = dict(
        con.execute(
            f"DESCRIBE SELECT * FROM read_parquet('{paths.products_file('tng', RUN_ID).as_posix()}', hive_partitioning = false)"
        ).fetchall()[i][:2]
        for i in range(len(PRODUCT_COLUMNS))
    )
    assert types["price"] == "DECIMAL(12,2)"
    assert types["scraped_at"] == "TIMESTAMP"
    assert "store" not in types
    assert "run_date" not in types


def test_partition_path_uses_run_date(tmp_path: Path) -> None:
    cfg = write_run(tmp_path, good())
    transform_run(RUN_ID, cfg)
    assert (
        tmp_path / "processed/products/store=levi/run_date=2026-01-03" / f"{RUN_ID}.parquet"
    ).is_file()
    assert (
        tmp_path / "processed/rejects/store=tng/run_date=2026-01-03" / f"{RUN_ID}.parquet"
    ).is_file()


def test_parse_reject(tmp_path: Path) -> None:
    pages = good()
    url = "https://shop.example.test/synthetic-tee/p"
    pages["levi"].append((url, url, fixture("synthetic_no_jsonld.html")))
    summary = transform_run(RUN_ID, write_run(tmp_path, pages))
    levi = summary.stores[0]
    assert (levi.rows_out, levi.rejected, levi.duplicates) == (1, 1, 0)
    (rej,) = read(RunPaths(tmp_path).rejects_file("levi", RUN_ID))
    assert tuple(rej) == REJECT_COLUMNS
    assert (rej["stage"], rej["reason"], rej["url"]) == ("parse", "no ld+json Product", url)
    assert rej["raw_path"] == "levi/1.html.gz"


def test_validate_rejects(tmp_path: Path) -> None:
    no_currency = product_html({"@type": "Offer", "price": 10})
    inverted = product_html(
        {"@type": "AggregateOffer", "lowPrice": 20, "highPrice": 10, "priceCurrency": "BRL"}
    )
    pages = good()
    pages["levi"] += [
        ("https://shop.example.test/a/p", "https://shop.example.test/a/p", no_currency),
        ("https://shop.example.test/b/p", "https://shop.example.test/b/p", inverted),
    ]
    summary = transform_run(RUN_ID, write_run(tmp_path, pages))
    assert (summary.stores[0].rows_out, summary.stores[0].rejected) == (1, 2)
    rejects = read(RunPaths(tmp_path).rejects_file("levi", RUN_ID))
    assert [r["stage"] for r in rejects] == ["validate", "validate"]
    assert "currency" in rejects[0]["reason"]
    assert "high_price must be >= price" in rejects[1]["reason"]
    assert all(len(r["reason"]) <= 300 for r in rejects)


def test_duplicate_final_url(tmp_path: Path) -> None:
    html = fixture("levi.html")
    pages = {
        "levi": [
            ("https://www.levi.com.br/a/p", LEVI_URL, html),
            ("https://www.levi.com.br/b/p", LEVI_URL + "/?utm=1", html),
        ]
    }
    summary = transform_run(RUN_ID, write_run(tmp_path, pages))
    s = summary.stores[0]
    assert (s.rows_out, s.rejected, s.duplicates) == (1, 0, 1)
    (row,) = read(RunPaths(tmp_path).products_file("levi", RUN_ID))
    assert row["url"] == LEVI_URL
    (rej,) = read(RunPaths(tmp_path).rejects_file("levi", RUN_ID))
    assert (rej["stage"], rej["reason"]) == ("duplicate", f"duplicate of {LEVI_URL}")
    assert rej["url"] == "https://www.levi.com.br/b/p"


def test_checksum_mismatch_and_unreadable(tmp_path: Path) -> None:
    pages = {"levi": [(LEVI_URL, LEVI_URL, fixture("levi.html"))] * 2}
    # same final_url twice would be a duplicate; make the second one distinct
    pages["levi"][1] = (LEVI_URL + "2", LEVI_URL + "2", fixture("levi.html"))
    cfg = write_run(tmp_path, pages)
    store_dir = RunPaths(tmp_path).raw_store_dir(RUN_ID, "levi")
    (store_dir / "0.html.gz").write_bytes(b"tampered")
    (store_dir / "1.html.gz").unlink()
    summary = transform_run(RUN_ID, cfg)
    s = summary.stores[0]
    assert (s.rows_out, s.rejected, s.duplicates) == (0, 2, 0)
    reasons = {r["reason"] for r in read(RunPaths(tmp_path).rejects_file("levi", RUN_ID))}
    assert "raw checksum mismatch" in reasons
    assert any(r.startswith("raw file unreadable") for r in reasons)
    assert summary.status == "failed"


def test_bad_gzip_with_matching_checksum(tmp_path: Path) -> None:
    cfg = write_run(tmp_path, {"levi": [(LEVI_URL, LEVI_URL, fixture("levi.html"))]})
    paths = RunPaths(tmp_path)
    bad = b"not gzip"
    (paths.raw_store_dir(RUN_ID, "levi") / "0.html.gz").write_bytes(bad)
    manifest = paths.raw_store_dir(RUN_ID, "levi") / "manifest.jsonl"
    entry = ManifestEntry.model_validate_json(manifest.read_text("utf-8"))
    manifest.write_text(
        entry.model_copy(update={"sha256": hashlib.sha256(bad).hexdigest()}).model_dump_json()
        + "\n",
        encoding="utf-8",
    )
    summary = transform_run(RUN_ID, cfg)
    assert summary.stores[0].rejected == 1
    (rej,) = read(paths.rejects_file("levi", RUN_ID))
    assert rej["stage"] == "parse"


def test_rerun_is_identical(tmp_path: Path) -> None:
    cfg = write_run(tmp_path, good())
    paths = RunPaths(tmp_path)
    first = transform_run(RUN_ID, cfg)
    files = sorted(p for p in tmp_path.rglob("*") if p.is_file())
    rows = [read(paths.products_file(s, RUN_ID)) for s in ("levi", "tng")]
    second = transform_run(RUN_ID, cfg)
    assert sorted(p for p in tmp_path.rglob("*") if p.is_file()) == files
    assert [read(paths.products_file(s, RUN_ID)) for s in ("levi", "tng")] == rows
    assert second.model_copy(update={"transformed_at": T0}) == first.model_copy(
        update={"transformed_at": T0}
    )


def test_stale_summary_removed_when_rerun_crashes(tmp_path: Path) -> None:
    cfg = write_run(tmp_path, good())
    paths = RunPaths(tmp_path)
    transform_run(RUN_ID, cfg)
    assert paths.run_summary(RUN_ID).is_file()
    (paths.raw_store_dir(RUN_ID, "tng") / "manifest.jsonl").write_text("{broken\n", "utf-8")
    with pytest.raises(StepError, match="corrupt manifest line 1"):
        transform_run(RUN_ID, cfg)
    assert not paths.run_summary(RUN_ID).exists()


def test_status_partial_for_empty_store(tmp_path: Path) -> None:
    pages = good()
    pages["empty"] = []
    summary = transform_run(RUN_ID, write_run(tmp_path, pages))
    assert summary.status == "partial"
    empty = summary.stores[2]
    assert (empty.rows_out, empty.rejected, empty.duplicates) == (0, 0, 0)
    paths = RunPaths(tmp_path)
    assert read(paths.products_file("empty", RUN_ID)) == []
    assert read(paths.rejects_file("empty", RUN_ID)) == []


def test_status_partial_for_blocked_store(tmp_path: Path) -> None:
    cfg = write_run(tmp_path, good(), reasons={"tng": "blocked_429"})
    assert transform_run(RUN_ID, cfg).status == "partial"


def test_status_failed(tmp_path: Path) -> None:
    cfg = write_run(tmp_path, {"levi": []})
    assert transform_run(RUN_ID, cfg).status == "failed"


def test_latest_run_default(tmp_path: Path) -> None:
    write_run(tmp_path, good(), run_id="20260101T000000Z")
    cfg = write_run(tmp_path, good(), run_id="20260102T000000Z")
    write_run(tmp_path, good(), run_id="20260105T000000Z", summary=False)
    assert transform_run(None, cfg).run_id == "20260102T000000Z"


def test_no_run(tmp_path: Path) -> None:
    with pytest.raises(StepError, match="no crawled run"):
        transform_run(None, Settings(data_dir=tmp_path))


def test_missing_run_json(tmp_path: Path) -> None:
    cfg = write_run(tmp_path, good(), summary=False)
    with pytest.raises(StepError, match="crawl not finished"):
        transform_run(RUN_ID, cfg)


def test_missing_manifest_means_no_entries(tmp_path: Path) -> None:
    cfg = write_run(tmp_path, {"levi": []})
    (RunPaths(tmp_path).raw_store_dir(RUN_ID, "levi") / "manifest.jsonl").unlink()
    assert transform_run(RUN_ID, cfg).stores[0].rows_out == 0


def test_reviewer_names_never_reach_parquet(tmp_path: Path) -> None:
    url = "https://shop.example.test/review-hoodie/p"
    cfg = write_run(tmp_path, {"levi": [(url, url, fixture("synthetic_reviews.html"))]})
    summary = transform_run(RUN_ID, cfg)
    assert summary.stores[0].rows_out == 1
    paths = RunPaths(tmp_path)
    values = read(paths.products_file("levi", RUN_ID)) + read(paths.rejects_file("levi", RUN_ID))
    assert "Zelda" not in repr(values)
    assert b"Zelda" not in paths.products_file("levi", RUN_ID).read_bytes()


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://x.com/A/B/p?color=1#frag", "/a/b/p"),
        ("https://x.com/a/b/p/", "/a/b/p"),
        ("https://X.com/Ab/P", "/ab/p"),
        ("https://x.com", "/"),
        ("https://x.com/?q=1", "/"),
        ("https://x.com//", "/"),
    ],
)
def test_product_key(url: str, expected: str) -> None:
    assert product_key(url) == expected
