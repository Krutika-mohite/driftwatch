"""
Tests run WITHOUT SQL Server: we replace the extract step with fake chunks.
That's a key testing idea — isolate the logic you own from external systems.

Run:  pytest -v
"""

import dataclasses
import functools
import json

import pandas as pd
import pytest

from driftwatch.pipeline import run as run_mod
from driftwatch.pipeline.errors import PermanentError, TransientError, error_type, is_transient
from driftwatch.pipeline.metadata import RunStore
from driftwatch.pipeline.retry import retry_call
from driftwatch.pipeline.snapshot import SnapshotWriter, read_ref


def _chunks():
    yield pd.DataFrame({"order_id": [1, 2], "qty": [1, 3], "status": ["PLACED", "SHIPPED"]})
    yield pd.DataFrame({"order_id": [3], "qty": [2], "status": ["DELIVERED"]})


# ---------------- snapshots ----------------

def test_commit_creates_snapshot_manifest_and_dev_ref(tmp_path):
    w = SnapshotWriter(tmp_path, "orders", "run1", "test").begin()
    for c in _chunks():
        w.write_chunk(c)
    m = w.commit()
    snap = tmp_path / "orders" / "snapshots" / m["snapshot_id"]
    assert (snap / "data.parquet").exists()
    assert json.loads((snap / "manifest.json").read_text())["row_count"] == 3
    assert read_ref(tmp_path / "orders", "dev") == m["snapshot_id"]
    assert not any((tmp_path / "orders" / "_staging").iterdir())  # staging emptied by the move


def test_abort_leaves_nothing_behind(tmp_path):
    w = SnapshotWriter(tmp_path, "orders", "run1", "test").begin()
    w.write_chunk(next(_chunks()))
    w.abort()
    assert not (tmp_path / "orders" / "snapshots").exists()
    assert read_ref(tmp_path / "orders", "dev") is None


def test_empty_snapshot_is_refused(tmp_path):
    w = SnapshotWriter(tmp_path, "orders", "run1", "test").begin()
    with pytest.raises(ValueError):
        w.commit()


def test_type_change_mid_read_fails(tmp_path):
    w = SnapshotWriter(tmp_path, "orders", "run1", "test").begin()
    w.write_chunk(pd.DataFrame({"qty": [1, 2]}))
    with pytest.raises(Exception):
        w.write_chunk(pd.DataFrame({"qty": ["one", "two"]}))


# ---------------- errors & retry ----------------

class FakeOdbcError(Exception):
    pass


def test_error_classification():
    assert is_transient(FakeOdbcError("08S01", "link failure"))
    assert is_transient(FakeOdbcError("HYT00", "timeout"))
    assert not is_transient(FakeOdbcError("42S02", "invalid object name"))
    assert error_type(FakeOdbcError("42S22", "invalid column")) == "permanent:42S22"


def test_retry_recovers_from_transient():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise TransientError("blip")
        return "ok"

    result, attempts = retry_call(flaky, max_attempts=3, is_retryable=is_transient, sleep=lambda s: None)
    assert (result, attempts) == ("ok", 3)


def test_retry_does_not_retry_permanent():
    calls = {"n": 0}

    def broken():
        calls["n"] += 1
        raise PermanentError("missing column")

    with pytest.raises(PermanentError):
        retry_call(broken, max_attempts=5, is_retryable=is_transient, sleep=lambda s: None)
    assert calls["n"] == 1


# ---------------- end-to-end table migration (fake source) ----------------

@pytest.fixture
def pipeline(tmp_path, monkeypatch):
    s = dataclasses.replace(run_mod.settings, data_dir=tmp_path, tables=("orders",), max_retries=3)
    monkeypatch.setattr(run_mod, "settings", s)
    monkeypatch.setattr(run_mod, "iter_table_chunks", lambda *a, **k: _chunks())
    monkeypatch.setattr(run_mod, "retry_call", functools.partial(retry_call, sleep=lambda x: None))
    store = RunStore(s.metadata_db)
    yield s, store
    store.close()


def test_transient_failure_recovers(pipeline):
    s, store = pipeline
    assert run_mod.migrate_table("orders", None, store, "b1", run_mod._Simulator("transient"))
    status, rows, attempts = store.con.execute("SELECT status, rows_written, attempts FROM pipeline_runs").fetchone()
    assert (status, rows, attempts) == ("SUCCESS", 3, 3)


def test_permanent_failure_keeps_previous_dev_and_alerts(pipeline):
    s, store = pipeline
    assert run_mod.migrate_table("orders", None, store, "b1", run_mod._Simulator(None))
    good = read_ref(s.lake_dir / "orders", "dev")

    assert not run_mod.migrate_table("orders", None, store, "b2", run_mod._Simulator("permanent"))
    assert read_ref(s.lake_dir / "orders", "dev") == good           # dev untouched
    assert len(list((s.lake_dir / "orders" / "snapshots").iterdir())) == 1  # no partial snapshot
    alert = json.loads(s.alerts_log.read_text().strip().splitlines()[-1])
    assert alert["severity"] == "CRITICAL" and alert["error_type"].startswith("permanent")
    last = store.con.execute("SELECT status, attempts FROM pipeline_runs WHERE batch_id='b2'").fetchone()
    assert last == ("FAILED", 1)