"""
Immutable snapshots — the heart of safe migration.

Layout on disk (our home-made "data lake"):

    data/lake/<table>/
        _staging/<snapshot_id>/        <- being written; invisible to everyone
        snapshots/<snapshot_id>/
            data.parquet
            manifest.json              <- row count, schema, checksum, run_id
        refs/
            dev.json                   <- POINTER: {"snapshot_id": "..."}
            (test.json, prod.json come in Phase 3)

Key concepts:
  1. IMMUTABLE: a committed snapshot is never modified. New data = new snapshot.
  2. ATOMIC COMMIT: we write everything into _staging, then do ONE rename into
     snapshots/. A rename on the same disk is atomic: readers see either the
     whole snapshot or nothing — never half a file. If the run crashes, only
     _staging has junk, which abort() (or the next run) cleans up.
  3. REFS ARE POINTERS: "dev", "test", "prod" are tiny JSON files pointing at a
     snapshot. Promotion (Phase 3) = copy a pointer. Rollback = point back.
     That's why rollback will be instant. Apache Iceberg and lakeFS work this way.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


def new_snapshot_id() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{ts}-{uuid.uuid4().hex[:6]}"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def write_json_atomic(path: Path, payload: dict) -> None:
    """Write to a temp file, then os.replace — readers never see a half-written JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    os.replace(tmp, path)


class SnapshotWriter:
    def __init__(self, lake_dir: Path, table: str, run_id: str, source: str):
        self.table = table
        self.run_id = run_id
        self.source = source
        self.table_dir = lake_dir / table
        self.snapshot_id = new_snapshot_id()
        self.staging_dir = self.table_dir / "_staging" / self.snapshot_id
        self.final_dir = self.table_dir / "snapshots" / self.snapshot_id
        self._writer: pq.ParquetWriter | None = None
        self._schema: pa.Schema | None = None
        self.rows = 0

    # --- writing -------------------------------------------------------------
    def begin(self) -> "SnapshotWriter":
        self.staging_dir.mkdir(parents=True, exist_ok=False)
        return self

    def write_chunk(self, df: pd.DataFrame) -> None:
        if df.empty:
            return
        if self._schema is None:
            batch = pa.Table.from_pandas(df, preserve_index=False)
            # A column that is entirely NULL in the first chunk has no type yet;
            # default it to string so later chunks can still be written.
            # Decimal precision is guessed from the first chunk's values (e.g. 999.99 -> 5 digits);
            # a later 12345.67 wouldn't fit, so widen decimals to the max precision.
            fields = []
            for f in batch.schema:
                if pa.types.is_null(f.type):
                    f = pa.field(f.name, pa.string())
                elif pa.types.is_decimal(f.type):
                    f = pa.field(f.name, pa.decimal128(38, f.type.scale))
                fields.append(f)
            self._schema = pa.schema(fields)
            batch = batch.cast(self._schema)
            self._writer = pq.ParquetWriter(self.staging_dir / "data.parquet", self._schema, compression="zstd")
        else:
            # Every chunk must match the first chunk's schema. If the source
            # changes type mid-read, this raises and the whole snapshot is aborted.
            batch = pa.Table.from_pandas(df, schema=self._schema, preserve_index=False)
        self._writer.write_table(batch)
        self.rows += len(df)

    # --- finishing -----------------------------------------------------------
    def commit(self, set_ref: str | None = "dev") -> dict:
        if self._writer is None:
            raise ValueError(f"No rows were written for table '{self.table}' — refusing to commit an empty snapshot.")
        self._writer.close()

        data_file = self.staging_dir / "data.parquet"
        manifest = {
            "snapshot_id": self.snapshot_id,
            "table": self.table,
            "run_id": self.run_id,
            "source": self.source,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "row_count": self.rows,
            "file_bytes": data_file.stat().st_size,
            "sha256": _sha256(data_file),
            "schema": [{"name": f.name, "type": str(f.type)} for f in self._schema],
        }
        write_json_atomic(self.staging_dir / "manifest.json", manifest)

        # THE atomic step: staging -> snapshots
        self.final_dir.parent.mkdir(parents=True, exist_ok=True)
        os.replace(self.staging_dir, self.final_dir)

        if set_ref:
            set_ref_pointer(self.table_dir, set_ref, self.snapshot_id, reason=f"pipeline run {self.run_id}")
        return manifest

    def abort(self) -> None:
        """Throw away everything written by this run. Committed snapshots are untouched."""
        if self._writer is not None:
            try:
                self._writer.close()
            except Exception:  # noqa: BLE001
                pass
        shutil.rmtree(self.staging_dir, ignore_errors=True)


# --- refs (pointers) ------------------------------------------------------------

def set_ref_pointer(table_dir: Path, ref: str, snapshot_id: str, reason: str) -> None:
    if not (table_dir / "snapshots" / snapshot_id / "manifest.json").exists():
        raise FileNotFoundError(f"Snapshot {snapshot_id} does not exist for {table_dir.name}")
    write_json_atomic(
        table_dir / "refs" / f"{ref}.json",
        {
            "ref": ref,
            "snapshot_id": snapshot_id,
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "reason": reason,
        },
    )


def read_ref(table_dir: Path, ref: str) -> str | None:
    p = table_dir / "refs" / f"{ref}.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))["snapshot_id"]


def cleanup_stale_staging(table_dir: Path) -> int:
    """Remove leftovers from runs that crashed hard (power cut, killed process)."""
    staging = table_dir / "_staging"
    if not staging.exists():
        return 0
    removed = 0
    for d in staging.iterdir():
        shutil.rmtree(d, ignore_errors=True)
        removed += 1
    return removed