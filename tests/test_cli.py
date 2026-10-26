from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from test_transform import LEVI_URL, TNG_URL, fixture, good, write_run
from typer.testing import CliRunner

from ecommerce_scraping import __version__, cli
from ecommerce_scraping.config import Settings
from ecommerce_scraping.models import CrawlSummary, StoreCrawl
from ecommerce_scraping.runs import StepError
from ecommerce_scraping.stores import STORES, Store

runner = CliRunner()
NOW = datetime(2026, 1, 3, tzinfo=UTC)


@pytest.fixture(autouse=True)
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)  # no repo .env
    monkeypatch.setenv("ECOMMERCE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ECOMMERCE_STORE_BASE_URLS", '{"levi": "http://127.0.0.1:1/"}')
    return tmp_path / "data"


class FakeCrawl:
    """Stands in for cli.run_crawl; records its arguments."""

    def __init__(self, pages: int = 3, error: StepError | None = None) -> None:
        self.pages, self.error = pages, error
        self.calls: list[tuple[list[Store], int | None, str, Settings]] = []

    def __call__(
        self, stores: list[Store], limit: int | None, run_id: str, cfg: Settings
    ) -> CrawlSummary:
        self.calls.append((stores, limit, run_id, cfg))
        if self.error:
            raise self.error
        crawls = [
            StoreCrawl(
                store=s.name,
                finish_reason="finished",
                pages_archived=self.pages,
                robots_forbidden=0,
                http_errors=0,
                retries=0,
                started_at=NOW,
                finished_at=NOW,
            )
            for s in stores
        ]
        return CrawlSummary(run_id=run_id, stores=crawls)


def invoke(*args: str) -> Any:
    return runner.invoke(cli.app, list(args))


def test_store_choices_match_the_registry() -> None:
    assert {s.value for s in cli.StoreName} == set(STORES)


def test_version_and_help() -> None:
    result = invoke("--version")
    assert result.exit_code == 0 and result.stdout.strip() == __version__
    result = invoke("crawl", "--help")
    assert result.exit_code == 0 and "hering" in result.output and "--no-limit" in result.output
    result = invoke("--help")
    for command in ("crawl", "transform", "views", "run", "stats"):
        assert command in result.output


def test_crawl_resolves_stores_with_overrides_and_prints_the_run_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeCrawl()
    monkeypatch.setattr(cli, "run_crawl", fake)
    result = invoke(
        "crawl", "-s", "levi", "--store", "tng", "-s", "levi", "--run-id", "20260103T000000Z"
    )
    assert result.exit_code == 0 and result.stdout.strip() == "20260103T000000Z"
    ((stores, limit, run_id, _cfg),) = fake.calls
    assert [(s.name, s.base_url) for s in stores] == [
        ("levi", "http://127.0.0.1:1"),
        ("tng", STORES["tng"].base_url),
    ]
    assert (limit, run_id) == (20, "20260103T000000Z")


def test_crawl_defaults_to_every_store_and_a_new_run_id(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeCrawl()
    monkeypatch.setattr(cli, "run_crawl", fake)
    result = invoke("crawl")
    assert result.exit_code == 0
    ((stores, _limit, run_id, _cfg),) = fake.calls
    assert [s.name for s in stores] == list(STORES)
    assert result.stdout.strip() == run_id and run_id.endswith("Z")


def test_crawl_limit_and_no_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeCrawl()
    monkeypatch.setattr(cli, "run_crawl", fake)
    assert invoke("crawl", "--limit", "5").exit_code == 0
    result = invoke("crawl", "--no-limit")
    assert result.exit_code == 0 and "thousands of requests" in result.stderr
    assert [c[1] for c in fake.calls] == [5, None]
    assert invoke("crawl", "--limit", "0").exit_code == 2
    assert invoke("crawl", "--limit", "5", "--no-limit").exit_code == 2
    assert len(fake.calls) == 2


@pytest.mark.parametrize("command", ["crawl", "transform"])
@pytest.mark.parametrize("bad", ["manual-1", "../x"])
def test_bad_run_id_is_rejected_before_any_work(
    command: str, bad: str, env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeCrawl()
    monkeypatch.setattr(cli, "run_crawl", fake)
    result = invoke(command, "--run-id", bad)
    assert result.exit_code == 2 and "YYYYMMDDTHHMMSSZ" in result.output
    assert not fake.calls and not env.exists()


def test_bad_settings_are_a_clean_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ECOMMERCE_DOWNLOAD_DELAY_S", "-1")
    for command in ("crawl", "stats"):
        result = invoke(command)
        assert result.exit_code == 1 and "error: invalid settings:" in result.stderr
        assert "Traceback" not in result.output


def test_crawl_step_error_exits_1(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "run_crawl", FakeCrawl(error=StepError("raw run directory exists")))
    result = invoke("crawl")
    assert result.exit_code == 1 and "error: raw run directory exists" in result.stderr


def test_crawl_without_pages_exits_1(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "run_crawl", FakeCrawl(pages=0))
    result = invoke("crawl", "--run-id", "20260103T000000Z")
    assert result.exit_code == 1
    assert (
        result.stdout.strip() == "20260103T000000Z" and "no store archived a page" in result.stderr
    )


def test_transform_ok_prints_a_line_per_store(env: Path) -> None:
    write_run(env, good())
    result = invoke("transform")
    assert result.exit_code == 0
    assert "levi: rows=1 rejected=0 duplicates=0 finish_reason=finished" in result.stdout
    assert "tng: rows=1" in result.stdout and "status: ok" in result.stdout


def test_transform_partial_warns_and_exits_0(env: Path) -> None:
    write_run(env, good(), reasons={"tng": "blocked_403"}, run_id="20260103T000000Z")
    result = invoke("transform", "--run-id", "20260103T000000Z")
    assert result.exit_code == 0 and "status: partial" in result.stdout
    assert "blocked_403" in result.stdout and "partial" in result.stderr


def test_transform_failed_exits_1(env: Path) -> None:
    write_run(env, {"levi": [(LEVI_URL, LEVI_URL, "<html></html>")]})
    result = invoke("transform")
    assert result.exit_code == 1 and "status: failed" in result.stdout


def test_transform_without_a_run_exits_1() -> None:
    result = invoke("transform")
    assert result.exit_code == 1 and result.stderr.startswith("error: no crawled run")


def test_views_and_stats_on_a_transformed_run(env: Path) -> None:
    write_run(
        env,
        {"levi": [(LEVI_URL, LEVI_URL, fixture("levi.html"))], "tng": [(TNG_URL, TNG_URL, "<p>")]},
    )
    assert invoke("transform").exit_code == 0
    result = invoke("views")
    assert result.exit_code == 0 and "products_latest" in result.stdout.split()
    result = invoke("stats")
    assert result.exit_code == 0
    header, levi, tng = result.stdout.splitlines()
    assert header.split() == [
        "store",
        "runs",
        "snapshots",
        "products",
        "rejects",
        "last_run_id",
        "last_scraped_at",
    ]
    assert levi.split()[:6] == ["levi", "1", "1", "1", "0", "20260103T230005Z"]
    assert levi.endswith("2026-01-03 23:00:06Z")
    assert tng.split()[:5] == ["tng", "1", "0", "0", "1"]
    assert header.index("runs") == levi.index("1") == tng.index("1")  # aligned columns


def test_views_and_stats_without_a_transformed_run() -> None:
    for command in ("views", "stats"):
        result = invoke(command)
        assert result.exit_code == 1 and "no transformed run yet" in result.stderr


def test_run_chains_crawl_transform_and_views(env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def crawl_into_data_dir(
        stores: list[Store], limit: int | None, run_id: str, cfg: Settings
    ) -> CrawlSummary:
        write_run(env, good(), run_id=run_id)  # the real crawl would write the same files
        return FakeCrawl()(stores, limit, run_id, cfg)

    monkeypatch.setattr(cli, "run_crawl", crawl_into_data_dir)
    result = invoke("run", "-s", "levi", "-s", "tng", "--limit", "3")
    assert result.exit_code == 0, result.output
    lines = result.stdout.splitlines()
    assert lines[0].endswith("Z") and "status: ok" in lines and "product_snapshots" in lines


def test_run_stops_when_the_crawl_archived_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "run_crawl", FakeCrawl(pages=0))
    result = invoke("run")
    assert result.exit_code == 1 and "status:" not in result.stdout


def test_run_reports_a_step_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "run_crawl", FakeCrawl(error=StepError("boom")))
    result = invoke("run")
    assert result.exit_code == 1 and "error: boom" in result.stderr
