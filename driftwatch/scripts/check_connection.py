"""
Step 2: prove Python can talk to SQL Server.

Run:  python scripts/check_connection.py

If this fails, nothing else will work — fix it first. The error messages below
cover the usual Windows problems.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pyodbc  # noqa: E402

from driftwatch.config import settings  # noqa: E402


def main() -> int:
    print("Installed ODBC drivers:")
    drivers = pyodbc.drivers()
    for d in drivers:
        print(f"   - {d}")

    if settings.sql_driver not in drivers:
        print(f"\n[X] Driver '{settings.sql_driver}' is not installed.")
        print("    Install 'Microsoft ODBC Driver 18 for SQL Server' (free) and run again,")
        print("    or set DW_SQL_DRIVER in .env to one of the drivers listed above.")
        return 1

    print(f"\nConnecting to {settings.sql_server} / {settings.sql_database} ...")
    try:
        with pyodbc.connect(settings.odbc_connection_string(), timeout=10) as conn:
            cur = conn.cursor()
            version = cur.execute("SELECT @@VERSION").fetchone()[0]
            print("[OK] Connected.")
            print("     " + version.splitlines()[0])

            rows = cur.execute(
                "SELECT t.name, SUM(p.rows) FROM sys.tables t "
                "JOIN sys.partitions p ON p.object_id = t.object_id AND p.index_id IN (0,1) "
                "GROUP BY t.name ORDER BY t.name"
            ).fetchall()
            if rows:
                print("\nTables in source:")
                for name, count in rows:
                    print(f"   - {name:<12} {count:>8,} rows")
            else:
                print("\nNo tables yet — run sql/01_create_source_db.sql first.")
    except pyodbc.Error as exc:
        print(f"\n[X] Connection failed:\n    {exc}\n")
        print("Common fixes:")
        print("  * Database not found  -> run sql/01_create_source_db.sql first")
        print("  * Server not found    -> check DW_SQL_SERVER (e.g. localhost\\SQLEXPRESS)")
        print("  * Login failed        -> use DW_SQL_TRUSTED=yes for Windows login")
        print("  * Service not running -> start 'SQL Server (MSSQLSERVER/SQLEXPRESS)' in services.msc")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
