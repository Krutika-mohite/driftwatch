"""
Extract — read a table from SQL Server in chunks.

Concepts:
  * CHUNKING: never load a whole table into memory. 5,000 rows at a time keeps
    memory flat whether the table has 20 thousand or 20 million rows.
  * DETERMINISTIC ORDER: ORDER BY the primary key, so two runs over the same
    data produce identical snapshots (needed for reliable comparisons later).
  * SQL INJECTION SAFETY: table names can't be passed as query parameters, so
    we validate them against a strict pattern AND an allow-list before building SQL.
"""

from __future__ import annotations

import re
from typing import Iterator

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")


def make_engine(url: str) -> Engine:
    # pool_pre_ping: test a pooled connection before using it (catches dropped connections)
    return create_engine(url, pool_pre_ping=True, fast_executemany=True)


def _safe_name(name: str, allowed: tuple[str, ...]) -> str:
    if name not in allowed or not _IDENTIFIER.match(name):
        raise ValueError(f"Table '{name}' is not allowed (allowed: {', '.join(allowed)})")
    return name


def primary_key_columns(engine: Engine, table: str) -> list[str]:
    sql = text(
        """
        SELECT c.name
        FROM sys.indexes i
        JOIN sys.index_columns ic ON ic.object_id = i.object_id AND ic.index_id = i.index_id
        JOIN sys.columns c        ON c.object_id = ic.object_id AND c.column_id = ic.column_id
        WHERE i.is_primary_key = 1 AND i.object_id = OBJECT_ID(:full_name)
        ORDER BY ic.key_ordinal
        """
    )
    with engine.connect() as conn:
        return [r[0] for r in conn.execute(sql, {"full_name": f"dbo.{table}"})]


def iter_table_chunks(engine: Engine, table: str, allowed: tuple[str, ...], chunk_size: int) -> Iterator[pd.DataFrame]:
    table = _safe_name(table, allowed)
    pk = primary_key_columns(engine, table)
    order_by = ", ".join(f"[{c}]" for c in pk) if pk else "(SELECT NULL)"
    query = f"SELECT * FROM dbo.[{table}] ORDER BY {order_by}"

    # stream_results: fetch rows from the server gradually instead of all at once
    with engine.connect().execution_options(stream_results=True) as conn:
        for chunk in pd.read_sql(text(query), conn, chunksize=chunk_size):
            yield chunk
