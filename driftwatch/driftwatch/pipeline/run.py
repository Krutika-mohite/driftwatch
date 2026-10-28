"""
The pipeline entry point.

Run:
    python -m driftwatch.pipeline.run                     # all tables
    python -m driftwatch.pipeline.run --tables orders
    python -m driftwatch.pipeline.run --simulate transient   # practise: retries
    python -m driftwatch.pipeline.run --simulate permanent   # practise: fail + alert

Flow for each table:
    start run record -> [extract chunks -> write staging] (retried if transient)
        success -> atomic commit -> dev ref updated -> run = SUCCESS
        failure -> abort staging -> run = FAILED -> ALERT
One table failing does not stop the others (failure isolation).
"""

from __future__ import annotations

import argparse
import sys
import time
import uuid

from driftwatch.config import settings
from driftwatch.pipeline.alerts import Alert, send_alert
from driftwatch.pipeline.errors import PermanentError, TransientError, error_type, is_transient
from driftwatch.pipeline.extract import iter_table_chunks, make_engine
from driftwatch.pipeline.metadata import RunStore
from driftwatch.pipeline.retry import retry_call
from driftwatch.pipeline.snapshot import SnapshotWriter, cleanup_stale_staging


class _Simulator:
    """Injects a failure after the first chunk, so you can watch the safety mechanisms work."""

    def __init__(self, mode: str | None, transient_failures: int = 2):
        self.mode = mode
        self.remaining = transient_failures

    def maybe_fail(self, chunk_no: int) -> None:
        if chunk_no != 2 or not self.mode:
            return
        if self.mode == "transient" and self.remaining > 0:
            self.remaining -= 1
            raise TransientError("Simulated network drop while reading (SQLSTATE 08S01)")
        if self.mode == "permanent":
            raise PermanentError("Simulated schema problem: column 'order_status' not found in destination mapping")


def migrate_table(table: str, engine, store: RunStore, batch_id: str, sim: _Simulator) -> bool:
    run_id = uuid.uuid4().hex[:12]
    store.start(run_id, batch_id, table)
    removed = cleanup_stale_staging(settings.lake_dir / table)
    if removed:
        print(f"   cleaned {removed} stale staging folder(s) from an earlier crashed run")

    tries = {"n": 0}

    def attempt() -> dict:
        tries["n"] += 1
        writer = SnapshotWriter(settings.lake_dir, table, run_id, source=f"{settings.sql_server}/{settings.sql_database}").begin()
        try:
            for n, chunk in enumerate(iter_table_chunks(engine, table, settings.tables, settings.chunk_size), start=1):
                sim.maybe_fail(n)
                writer.write_chunk(chunk)
            return writer.commit(set_ref="dev")
        except BaseException:
            writer.abort()  # whatever happened, leave no half-written data behind
            raise

    def on_retry(n: int, exc: BaseException, delay: float) -> None:
        print(f"   attempt {n} failed ({error_type(exc)}): retrying in {delay:.1f}s ...")

    started = time.perf_counter()
    try:
        manifest, attempts = retry_call(attempt, max_attempts=settings.max_retries, is_retryable=is_transient, on_retry=on_retry)
    except Exception as exc:  # noqa: BLE001
        etype = error_type(exc)
        attempts = tries["n"]
        store.fail(run_id, attempts, etype, str(exc))
        send_alert(
            Alert(
                severity="CRITICAL",
                title=f"Migration of '{table}' failed",
                table=table,
                run_id=run_id,
                details=str(exc),
                error_type=etype,
                blocked=f"No new snapshot for '{table}'. The previous dev snapshot is still in place and unchanged.",
                next_step=("Transient error persisted after retries — check SQL Server is running and reachable."
                           if is_transient(exc) else
                           "Permanent error — needs a fix before re-running (retrying will not help)."),
            ),
            settings.alerts_log,
        )
        return False

    secs = time.perf_counter() - started
    store.succeed(run_id, manifest["row_count"], manifest["snapshot_id"], attempts)
    retry_note = f" after {attempts} attempts" if attempts > 1 else ""
    print(f"[OK] {table:<10} {manifest['row_count']:>8,} rows -> snapshot {manifest['snapshot_id']} "
          f"({manifest['file_bytes'] / 1024:,.0f} KB, {secs:.1f}s){retry_note}")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Driftwatch pipeline: SQL Server -> Parquet snapshots")
    parser.add_argument("--tables", default="all", help="comma-separated table names, or 'all'")
    parser.add_argument("--simulate", choices=["transient", "permanent"], help="inject a failure to practise")
    args = parser.parse_args(argv)

    tables = settings.tables if args.tables == "all" else tuple(t.strip() for t in args.tables.split(","))
    batch_id = uuid.uuid4().hex[:8]
    print(f"Driftwatch batch {batch_id}: {', '.join(tables)}\n")

    engine = make_engine(settings.sqlalchemy_url())
    store = RunStore(settings.metadata_db)
    sim = _Simulator(args.simulate)
    try:
        results = {t: migrate_table(t, engine, store, batch_id, sim) for t in tables}
    finally:
        store.close()
        engine.dispose()

    failed = [t for t, ok in results.items() if not ok]
    print(f"\nBatch {batch_id}: {len(results) - len(failed)} succeeded, {len(failed)} failed")
    return 1 if failed else 0  # non-zero exit code -> schedulers & CI know it failed


if __name__ == "__main__":
    sys.exit(main())
