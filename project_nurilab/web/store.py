"""SQLite job records: one file, one table."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_COLUMNS = (
    "id",
    "status",
    "error_code",
    "created_at",
    "finished_at",
    "upload_name",
    "file_count",
    "review_client",
    "review_model",
    "review_status",
    "review_failure_code",
    "risk_level",
    "static_risk_level",
    "report_path",
)
_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    error_code TEXT,
    created_at TEXT NOT NULL,
    finished_at TEXT,
    upload_name TEXT NOT NULL,
    file_count INTEGER NOT NULL,
    review_client TEXT NOT NULL,
    review_model TEXT,
    review_status TEXT,
    review_failure_code TEXT,
    risk_level TEXT,
    static_risk_level TEXT,
    report_path TEXT
)
"""


@dataclass(frozen=True, slots=True)
class JobRecord:
    """One analysis job. ``report_path`` is the JSON report under the data dir."""

    id: str
    status: str
    created_at: str
    upload_name: str
    file_count: int
    review_client: str
    review_model: str | None = None
    error_code: str | None = None
    finished_at: str | None = None
    review_status: str | None = None
    review_failure_code: str | None = None
    risk_level: str | None = None
    static_risk_level: str | None = None
    report_path: str | None = None


class JobStore:
    """Job table access. Each call opens its own connection, so any thread may call."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        with self._connect() as conn:
            conn.execute(_SCHEMA)

    def create(self, job: JobRecord) -> None:
        values = [getattr(job, column) for column in _COLUMNS]
        placeholders = ", ".join("?" for _ in _COLUMNS)
        with self._connect() as conn:
            conn.execute(
                f"INSERT INTO jobs ({', '.join(_COLUMNS)}) VALUES ({placeholders})",
                values,
            )

    def get(self, job_id: str) -> JobRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT {', '.join(_COLUMNS)} FROM jobs WHERE id = ?", (job_id,)
            ).fetchone()
        return JobRecord(**dict(zip(_COLUMNS, row, strict=True))) if row else None

    def update(self, job_id: str, **values: Any) -> None:
        unknown = set(values) - set(_COLUMNS[1:])
        if unknown:
            raise ValueError(f"Unknown job columns: {sorted(unknown)}")
        assignments = ", ".join(f"{column} = ?" for column in values)
        with self._connect() as conn:
            conn.execute(
                f"UPDATE jobs SET {assignments} WHERE id = ?",
                [*values.values(), job_id],
            )

    def interrupt_unfinished(self) -> list[str]:
        """Fail queued and running jobs left by a stopped server; return their ids."""

        with self._connect() as conn:
            ids = [
                row[0]
                for row in conn.execute(
                    "SELECT id FROM jobs WHERE status IN ('queued', 'running')"
                )
            ]
            conn.execute(
                "UPDATE jobs SET status = 'failed', error_code = 'interrupted', "
                "finished_at = ? WHERE status IN ('queued', 'running')",
                (now_iso(),),
            )
        return ids

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        # "with conn" commits or rolls back; closing() then closes it.
        with closing(sqlite3.connect(self.path)) as conn, conn:
            yield conn


def now_iso() -> str:
    return datetime.now(UTC).isoformat()
