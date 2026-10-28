"""
Run metadata — the pipeline's memory.

Concept: every run is recorded: when, which table, how many rows, success or
failure, why it failed, how many attempts. This history is GOLD later:
  * Phase 6 anomaly detection compares today's run with past runs.
  * Phase 11 the AI agent reads this to diagnose failures.
  * Phase 16 Grafana dashboards are built on it.

We use DuckDB — a free, file-based analytical database (like SQLite, but built
for analytics). No server to install.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import duckdb

_SCHEMA = """
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id        VARCHAR PRIMARY KEY,
    batch_id      VARCHAR NOT NULL,     -- one CLI invocation = one batch of table runs
    table_name    VARCHAR NOT NULL,
    status        VARCHAR NOT NULL,     -- RUNNING | SUCCESS | FAILED
    started_at    TIMESTAMP NOT NULL,
    finished_at   TIMESTAMP,
    rows_written  BIGINT,
    snapshot_id   VARCHAR,
    attempts      INTEGER,
    error_type    VARCHAR,
    error_message VARCHAR
);
"""


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class RunStore:
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.con = duckdb.connect(str(db_path))
        self.con.execute(_SCHEMA)

    def start(self, run_id: str, batch_id: str, table: str) -> None:
        self.con.execute(
            "INSERT INTO pipeline_runs (run_id, batch_id, table_name, status, started_at) VALUES (?, ?, ?, 'RUNNING', ?)",
            [run_id, batch_id, table, _now()],
        )

    def succeed(self, run_id: str, rows: int, snapshot_id: str, attempts: int) -> None:
        self.con.execute(
            "UPDATE pipeline_runs SET status='SUCCESS', finished_at=?, rows_written=?, snapshot_id=?, attempts=? WHERE run_id=?",
            [_now(), rows, snapshot_id, attempts, run_id],
        )

    def fail(self, run_id: str, attempts: int, error_type: str, message: str) -> None:
        self.con.execute(
            "UPDATE pipeline_runs SET status='FAILED', finished_at=?, attempts=?, error_type=?, error_message=? WHERE run_id=?",
            [_now(), attempts, error_type, message[:2000], run_id],
        )

    def recent(self, limit: int = 20):
        return self.con.execute(
            "SELECT table_name, status, rows_written, attempts, error_type, "
            "date_diff('millisecond', started_at, finished_at) AS ms, snapshot_id "
            "FROM pipeline_runs ORDER BY started_at DESC LIMIT ?",
            [limit],
        ).fetchall()

    def close(self) -> None:
        self.con.close()
