# Day 1 — Setup, source database, and the first safe pipeline

**Goal for today:** data flows from SQL Server into versioned snapshots, and you
*see with your own eyes* that a failure can never leave broken data behind.

**Time:** ~2 hours. Do every step in order. Don't skip the experiments in Step 9 —
that's where the learning happens.

---

## Step 1 — Check your tools (10 min)

Open **PowerShell** and run:

```powershell
python --version      # need 3.10 or newer
git --version         # if missing: install "Git for Windows" (free)
```

Check the ODBC driver (this is how Python talks to SQL Server):

```powershell
Get-OdbcDriver | Where-Object Name -like "*SQL Server*" | Select-Object Name
```

You want to see **ODBC Driver 18 for SQL Server** (17 also works).
If it's missing, download *"Microsoft ODBC Driver 18 for SQL Server"* from
Microsoft's site (free) and install it.

In **VS Code**, install these free extensions:
- **Python** (Microsoft)
- **SQL Server (mssql)** (Microsoft) — lets you run `.sql` files inside VS Code

---

## Step 2 — Open the project (5 min)

1. Unzip `driftwatch.zip` to a short path, e.g. `D:\Projects\driftwatch`
   (avoid OneDrive folders — they sometimes lock files mid-write).
2. VS Code → **File → Open Folder** → select `driftwatch`.
3. Open a terminal inside VS Code: **Terminal → New Terminal**.

Project layout:

```
driftwatch/
├── ROADMAP.md               the full 20-phase plan
├── DAY_01.md                this guide
├── requirements.txt         Python libraries (all free)
├── .env.example             settings template
├── sql/
│   └── 01_create_source_db.sql
├── scripts/
│   ├── check_connection.py  "can Python reach SQL Server?"
│   ├── seed_source.py       fills the source with realistic data
│   └── inspect_lake.py      looks inside the destination
├── driftwatch/
│   ├── config.py            reads settings from .env
│   └── pipeline/
│       ├── run.py           ENTRY POINT — orchestrates everything
│       ├── extract.py       reads SQL Server in chunks
│       ├── snapshot.py      writes immutable, atomic snapshots
│       ├── errors.py        transient vs permanent errors
│       ├── retry.py         exponential backoff + jitter
│       ├── alerts.py        warns the user
│       └── metadata.py      records every run (DuckDB)
└── tests/
    └── test_pipeline.py     runs without SQL Server
```

---

## Step 3 — Virtual environment and libraries (10 min)

**Concept:** a virtual environment (`.venv`) is a private set of libraries for
this project only, so it never clashes with other Python projects. Every
professional Python project uses one, and Docker images do the same thing later.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

If PowerShell says *"running scripts is disabled"*, run this once, then activate again:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Your prompt now starts with `(.venv)`. Install the libraries:

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

In VS Code: **Ctrl+Shift+P → "Python: Select Interpreter"** → choose the one in `.venv`.

---

## Step 4 — Settings file (5 min)

```powershell
copy .env.example .env
```

Open `.env`. The only line you may need to change is `DW_SQL_SERVER`:

| Your SQL Server is… | Set |
|---|---|
| Developer / full edition (default instance) | `DW_SQL_SERVER=localhost` |
| Express edition | `DW_SQL_SERVER=localhost\SQLEXPRESS` |

Not sure? Press **Win+R → `services.msc`** and look for *SQL Server (…)*. The
name in brackets is the instance: `MSSQLSERVER` = default → `localhost`;
anything else → `localhost\THAT_NAME`.

**Concept:** `.env` holds settings and secrets. It's listed in `.gitignore`, so it
never reaches GitHub. Later, Kubernetes provides the same values as Secrets —
and the code doesn't change at all.

---

## Step 5 — Create the source database (5 min)

Open `sql/01_create_source_db.sql` in VS Code (or SSMS) and run it against your
local server (mssql extension: **Ctrl+Shift+E**).

It creates `DriftwatchSource` with three tables:

- `customers` — who buys
- `products` — what they buy
- `orders` — the transactions (links customers and products)

This is the **"old system"** we migrate data *from*.

---

## Step 6 — Prove the connection works (5 min)

```powershell
python scripts/check_connection.py
```

Expected: `[OK] Connected.` and the three tables with 0 rows.
If it fails, the script prints the usual fixes. **Don't continue until this passes.**

---

## Step 7 — Fill the source with data (5 min)

```powershell
python scripts/seed_source.py
```

This inserts 2,000 customers, 200 products and 20,000 orders using Faker's
Indian locale. Run `check_connection.py` again to see the row counts.

**Concepts inside `seed_source.py`:**
- `random.seed(42)` — everyone gets identical data. Reproducible data is how we'll
  later *prove* the AI catches problems; a moving baseline would make that impossible.
- ~3% missing emails and ~5% missing phones on purpose. Real data is never clean,
  and our future anomaly detector must learn that this level is **normal**.
- `fast_executemany` sends rows in bulk instead of 20,000 separate round-trips.
- One `commit()` at the end → all-or-nothing.

---

## Step 8 — Run the pipeline (10 min)

```powershell
python -m driftwatch.pipeline.run
```

Expected:

```
[OK] customers     2,000 rows -> snapshot 20261021T....-a1b2c3 (...)
[OK] products        200 rows -> snapshot ...
[OK] orders       20,000 rows -> snapshot ...

Batch ...: 3 succeeded, 0 failed
```

Now look inside the destination:

```powershell
python scripts/inspect_lake.py
```

Then open the `data/lake/orders/` folder in VS Code's explorer and look at:
- `snapshots/<id>/manifest.json` — row count, schema, SHA-256 checksum
- `refs/dev.json` — a tiny **pointer** to the current dev snapshot

### Read the code now, in this order

1. `pipeline/run.py` → `migrate_table()` — the whole flow on one screen
2. `pipeline/snapshot.py` → `commit()` and `abort()`
3. `pipeline/errors.py` → `is_transient()`
4. `pipeline/retry.py` → `backoff_delay()`

Read every comment. Each file opens with the concept it teaches.

---

## Step 9 — Break it on purpose (30 min)  ⭐ most important

### Experiment A — a transient failure that recovers

```powershell
python -m driftwatch.pipeline.run --tables orders --simulate transient
```

**Watch:** attempts 1 and 2 fail with a simulated network drop, each waits a
little longer (backoff), attempt 3 succeeds.

**Ask yourself:** why are the waits not exactly 1s and 2s? *(Hint: jitter.)*

### Experiment B — a permanent failure

```powershell
python -m driftwatch.pipeline.run --tables orders --simulate permanent
```

**Watch:**
- No retries — a schema problem won't fix itself.
- A `CRITICAL` alert with *what failed, what is blocked, what to do next*.
- Run `inspect_lake.py`: **dev still points at the last good snapshot**, and there
  is no half-written snapshot anywhere.

This is the core promise of Driftwatch: *a failed run can never damage good data.*

### Experiment C — a real failure: the database disappears

1. `services.msc` → right-click your SQL Server service → **Stop**.
2. Run `python -m driftwatch.pipeline.run`.
3. Watch it classify the error as **transient** (SQLSTATE `08001`), retry with
   backoff, give up after 3 attempts, and alert you for every table.
4. **Start** the service again and re-run — everything succeeds.

### Experiment D — a real permanent failure: a missing table

In SQL (VS Code or SSMS):

```sql
USE DriftwatchSource;
EXEC sp_rename 'dbo.products', 'products_old';
```

Run the pipeline. `products` fails as **permanent** (SQLSTATE `42S02`, invalid
object name) with no retries, while `customers` and `orders` **still succeed**.
That's *failure isolation*: one bad table doesn't stop the rest.

Put it back:

```sql
EXEC sp_rename 'dbo.products_old', 'products';
```

### Look at the evidence

```powershell
python scripts/inspect_lake.py
```

The run history shows every success and failure, attempt counts, and error types.
Open `data/alerts.log` too — one JSON alert per line.

> This history is exactly what the AI agent will read in Phase 11 to diagnose
> failures. You are already building its training ground.

---

## Step 10 — Run the tests (5 min)

```powershell
pytest -v
```

All 9 tests should pass — **without** SQL Server, because the tests replace the
extract step with fake data. **Concept:** isolate the logic you own from external
systems so tests are fast and reliable. This matters a lot for CI/CD in Phase 18.

---

## Step 11 — Save your work to Git (10 min)

```powershell
git init
git add .
git commit -m "Day 1: source DB, snapshot pipeline with retries, alerts and run metadata"
```

Create a free **public** repository named `driftwatch` on GitHub (public repos
get free GitHub Actions minutes, which we need for CI/CD), then:

```powershell
git remote add origin https://github.com/<your-username>/driftwatch.git
git branch -M main
git push -u origin main
```

Tick **Phase 0** in `ROADMAP.md`.

---

## What you learned today

| Concept | Where you saw it |
|---|---|
| Config outside code (12-factor style) | `.env`, `config.py` |
| Chunked, streaming extraction | `extract.py` |
| SQL injection safety for identifiers | `extract.py` → `_safe_name` |
| Immutable snapshots | `snapshot.py` |
| Atomic commit (staging → rename) | `snapshot.py` → `commit()` |
| Refs as pointers (basis of promotion/rollback) | `refs/dev.json` |
| Transient vs permanent errors | `errors.py` |
| Exponential backoff + jitter | `retry.py` |
| Failure isolation | `run.py` → one table per run |
| Run metadata as future AI evidence | `metadata.py` |
| Testing without external systems | `tests/test_pipeline.py` |

## Self-check — answer these in your own words

1. Why does the pipeline write to `_staging` first instead of straight to `snapshots`?
2. What would go wrong if we retried a *permanent* error 5 times?
3. Why is changing `dev.json` enough to "release" new data — why don't we copy files?
4. Why is the exit code `1` when any table fails? Who reads it?
5. If the PC loses power in the middle of a run, what's left on disk, and who cleans it up?

If you can answer all five clearly, you've understood Day 1.

---

## Next session (Day 2) — preview

- **Incremental extraction:** copy only rows changed since the last run, using the
  `updated_at` column (a "watermark"). This makes the pipeline much faster.
- **Schema capture:** save each table's schema per run, so changes can be detected —
  the first signal our AI agent will use.
- **Alerts on your phone:** email via Gmail (app password) or a Telegram bot, both free.
