"""Run ids, the on-disk layout of the layers and the latest-run lookups."""

import json
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

_RUN_ID_FORMAT = "%Y%m%dT%H%M%SZ"


class StepError(RuntimeError):
    """A pipeline step failed; the CLI turns it into exit code 1."""


def utc_now() -> datetime:
    return datetime.now(UTC)


def naive_utc(value: datetime) -> datetime:
    """UTC wall-clock time without tzinfo: the Parquet and DuckDB columns are UTC TIMESTAMPs."""
    return value.astimezone(UTC).replace(tzinfo=None)


def new_run_id(now: datetime | None = None) -> str:
    """UTC start time as YYYYMMDDTHHMMSSZ; sorts in time order."""
    return (now or utc_now()).astimezone(UTC).strftime(_RUN_ID_FORMAT)


def run_date(run_id: str) -> date:
    """The UTC day a run started; a run never spans two partitions."""
    try:
        return datetime.strptime(run_id, _RUN_ID_FORMAT).date()
    except ValueError:
        raise ValueError(f"invalid run id: {run_id!r}") from None


@dataclass(frozen=True)
class RunPaths:
    data_dir: Path

    @property
    def raw_root(self) -> Path:
        return self.data_dir / "raw"

    @property
    def processed_root(self) -> Path:
        return self.data_dir / "processed"

    @property
    def runs_dir(self) -> Path:
        return self.processed_root / "_runs"

    @property
    def warehouse(self) -> Path:
        return self.data_dir / "warehouse.duckdb"

    def raw_run_dir(self, run_id: str) -> Path:
        return self.raw_root / run_id

    def raw_store_dir(self, run_id: str, store: str) -> Path:
        return self.raw_run_dir(run_id) / store

    def raw_summary(self, run_id: str) -> Path:
        return self.raw_run_dir(run_id) / "run.json"

    def run_summary(self, run_id: str) -> Path:
        return self.runs_dir / f"{run_id}.json"

    def _partition_file(self, kind: str, store: str, run_id: str) -> Path:
        part = self.processed_root / kind / f"store={store}" / f"run_date={run_date(run_id)}"
        return part / f"{run_id}.parquet"

    def products_file(self, store: str, run_id: str) -> Path:
        return self._partition_file("products", store, run_id)

    def rejects_file(self, store: str, run_id: str) -> Path:
        return self._partition_file("rejects", store, run_id)


def _load_object(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def latest_crawled_run(paths: RunPaths) -> str | None:
    """Newest raw run whose run.json exists and parses (it is written last)."""
    if not paths.raw_root.is_dir():
        return None
    done = [p.name for p in paths.raw_root.iterdir() if _load_object(p / "run.json") is not None]
    return max(done, default=None)


def latest_transformed_run(paths: RunPaths) -> str | None:
    """Newest run summary with status ok or partial."""
    if not paths.runs_dir.is_dir():
        return None
    done = [
        p.stem
        for p in paths.runs_dir.glob("*.json")
        if (s := _load_object(p)) is not None and s.get("status") in {"ok", "partial"}
    ]
    return max(done, default=None)


class _StepLogger(logging.LoggerAdapter[logging.Logger]):
    def process(self, msg: Any, kwargs: Any) -> tuple[Any, Any]:
        extra = self.extra or {}
        return f"run_id={extra['run_id']} step={extra['step']} {msg}", kwargs


def step_logger(run_id: str, step: str) -> logging.LoggerAdapter[logging.Logger]:
    return _StepLogger(logging.getLogger("ecommerce_scraping"), {"run_id": run_id, "step": step})
