# Driftwatch

**AI-powered data migration — AI finds the problem, suggests the fix, and nothing changes without your permission.**

Driftwatch moves data from a source (SQL Server) into versioned destinations
(`dev` → `test` → `prod`). It detects failures and data-quality problems, explains them,
proposes fixes for a human to approve, and lets you promote or roll back any
environment in one click.

> Status: 🚧 being built in public as a learning project. See [ROADMAP.md](ROADMAP.md).

## Current capabilities (Phase 0–1)

- Chunked extraction from SQL Server
- Immutable Parquet snapshots with manifests and checksums
- Atomic commits — a failed run never leaves partial data
- Transient vs permanent error classification, with exponential backoff + jitter
- Failure isolation per table
- Alerts and full run history (DuckDB)

## Quick start

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env          # set DW_SQL_SERVER
# run sql/01_create_source_db.sql in SQL Server
python scripts/check_connection.py
python scripts/seed_source.py
python -m driftwatch.pipeline.run
python scripts/inspect_lake.py
pytest -v
```

Full walkthrough: [DAY_01.md](DAY_01.md)

## Tech stack (all free)

Python · SQL Server · Parquet · DuckDB · Ollama · sentence-transformers · FastAPI ·
Streamlit · Docker · kind · Helm · KEDA · Argo CD · GitHub Actions · Prometheus · Grafana · Langfuse
