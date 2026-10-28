"""
Look inside the destination: snapshots, refs, run history — and query with SQL.

Run:  python scripts/inspect_lake.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import duckdb  # noqa: E402

from driftwatch.config import settings  # noqa: E402
from driftwatch.pipeline.snapshot import read_ref  # noqa: E402


def main() -> int:
    lake = settings.lake_dir
    if not lake.exists():
        print("Lake is empty — run the pipeline first.")
        return 1

    print("=== Snapshots and refs ===")
    for table_dir in sorted(p for p in lake.iterdir() if p.is_dir()):
        dev = read_ref(table_dir, "dev")
        snaps = sorted((table_dir / "snapshots").glob("*")) if (table_dir / "snapshots").exists() else []
        print(f"\n{table_dir.name}  ({len(snaps)} snapshot(s))")
        for s in snaps[-5:]:
            m = json.loads((s / "manifest.json").read_text(encoding="utf-8"))
            marker = "  <- dev" if s.name == dev else ""
            print(f"   {s.name}  {m['row_count']:>8,} rows{marker}")

    print("\n=== Query the dev version with plain SQL (DuckDB reads Parquet directly) ===")
    orders_dev = read_ref(lake / "orders", "dev")
    if orders_dev:
        path = (lake / "orders" / "snapshots" / orders_dev / "data.parquet").as_posix()
        rows = duckdb.sql(
            f"SELECT order_status, COUNT(*) AS orders, ROUND(SUM(quantity*unit_price),0) AS gross "
            f"FROM read_parquet('{path}') GROUP BY 1 ORDER BY 2 DESC"
        ).fetchall()
        for status, n, gross in rows:
            print(f"   {status:<10} {n:>7,} orders   gross {gross:>16,.0f}")

    if settings.metadata_db.exists():
        print("\n=== Last runs ===")
        con = duckdb.connect(str(settings.metadata_db), read_only=True)
        for r in con.execute(
            "SELECT table_name, status, rows_written, attempts, error_type, "
            "date_diff('millisecond', started_at, finished_at) FROM pipeline_runs ORDER BY started_at DESC LIMIT 10"
        ).fetchall():
            table, status, rows, attempts, etype, ms = r
            print(f"   {table:<10} {status:<8} rows={rows or 0:<7} attempts={attempts or 0} "
                  f"{(ms or 0)/1000:.1f}s {etype or ''}")
        con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
