# Driftwatch — Full Roadmap

> **Driftwatch** — AI-powered data migration: AI finds the problem, suggests the fix,
> and nothing changes without your permission.

Every tool in this roadmap is **free**. Nothing requires a credit card.

| Need | Free tool we use |
|---|---|
| Source database | SQL Server (Developer or Express edition — you already have it) |
| Language / editor | Python 3.10+ and VS Code |
| Destination "data lake" | Parquet files + DuckDB (later: Apache Iceberg or lakeFS in Docker) |
| Local LLM | Ollama (runs models like Qwen 2.5 / Llama 3.2 on your own machine) |
| Embeddings | sentence-transformers (runs locally) |
| Data quality library | Soda Core / Great Expectations (open source) |
| API + UI | FastAPI + Streamlit (later optionally React) |
| Tracing / monitoring | Langfuse (self-hosted), Prometheus, Grafana |
| Containers | Docker Desktop (free for personal use) |
| Kubernetes | kind or minikube (local cluster), Helm, KEDA, Argo CD |
| CI/CD | GitHub Actions (free for public repos), GitHub Container Registry |

**Hardware note:** a 3B-parameter model in Ollama runs on CPU with 8–16 GB RAM.
A GPU is nice but not required. Where a step needs a GPU (vLLM), an alternative is given.

---

## How each phase is structured

Every phase has four parts:
1. **Concept** — what you are learning and *why* it matters in a product company.
2. **Build** — what you will code.
3. **Done when** — a checklist; don't move on until it's ticked.
4. **Interview angle** — how you will explain it.

Timing assumes ~1.5–2 hours a day. Go slower if a concept isn't clear — understanding beats speed.

---

## Part A — Data pipeline foundation (no AI yet)

> Why no AI first? AI features need a reliable system to sit on. And you must know
> what "normal" looks like before an AI can detect "abnormal".

### Phase 0 — Setup (Day 1) ✅ *today*
- **Concept:** project structure, virtual environments, config via `.env`, connecting Python to SQL Server via ODBC.
- **Build:** source database `DriftwatchSource` with realistic e-commerce data (customers, products, orders).
- **Done when:** `check_connection.py` passes, source has data, first pipeline run succeeds.

### Phase 1 — Pipeline v1 with failure handling (Days 1–4)
- **Concept:** Extract-Load, chunked reads, **immutable snapshots**, atomic writes, run metadata, retries with exponential backoff, transient vs permanent errors.
- **Build:** extract each table → Parquet snapshot + manifest; record every run in a metadata DB; retry transient failures; raise alerts.
- **Done when:** you can stop SQL Server mid-run and the pipeline fails *cleanly*, alerts you, and leaves no half-written data.
- **Interview angle:** "Snapshots are immutable and written atomically, so a failed run can never corrupt the destination."

### Phase 2 — Alerts that reach a human (Day 5)
- **Concept:** alert routing, deduplication, severity.
- **Build:** alerts to a free channel — email (Gmail SMTP with an app password) or a Discord/Telegram webhook.
- **Done when:** a failed run sends you a readable message on your phone.

### Phase 3 — Environments, promotion and rollback (Days 6–9)
- **Concept:** the **Write-Audit-Publish (WAP)** pattern; references (pointers) vs copies; why rollback should be instant.
- **Build:** `dev`, `test`, `prod` refs per table; `promote` and `rollback` commands; promotion history.
- **Done when:** `promote dev→test`, `promote test→prod`, and `rollback prod` all work in under a second, with history recorded.
- **Interview angle:** "Promotion moves a pointer, not data — that's how Iceberg and lakeFS work, and I built it from first principles before using them."

### Phase 4 — Rule-based data quality (Days 10–12)
- **Concept:** data quality dimensions (completeness, validity, uniqueness, consistency, freshness), quality gates.
- **Build:** a small rule engine (rules as YAML), then compare with Soda Core.
- **Done when:** a bad snapshot is blocked from promotion with a clear report.

### Phase 5 — Fault injection (Days 13–14)
- **Concept:** you can't evaluate failure handling without failures. Chaos testing.
- **Build:** `inject_fault.py` — drops a column, inserts nulls, changes data types, duplicates rows, breaks the connection, shifts a category's meaning. Each fault is labelled with its true root cause.
- **Done when:** 20+ labelled fault scenarios exist. **This becomes your AI evaluation dataset later.**

---

## Part B — AI concepts, one at a time

### Phase 6 — Classical ML anomaly detection (Days 15–18)
- **Concept:** data profiling, baselines, z-scores, distribution drift (PSI, KS test), Isolation Forest. **When not to use an LLM.**
- **Build:** profile every snapshot; compare with history; flag anomalies with a score.
- **Done when:** injected faults (null spikes, row-count drops, distribution shifts) are caught; you know precision/recall on your fault set.

### Phase 7 — LLM fundamentals with Ollama (Days 19–22)
- **Concept:** tokens, context window, temperature, system vs user prompts, why outputs vary, local vs API models, quantization (Q4 vs Q8 GGUF).
- **Build:** a small `llm.py` client; experiments notebook measuring speed (tokens/sec) and quality across 2 models and 2 quantization levels.
- **Done when:** you can explain why the Q4 model is faster and what it costs in quality — with your own numbers.

### Phase 8 — Structured output and guardrails (Days 23–26)
- **Concept:** JSON schemas, Pydantic validation, retry-on-invalid, never trusting raw LLM output.
- **Build:** natural-language quality rules → validated rule JSON → executable checks. Example: *"order quantity must be between 1 and 100"*.
- **Done when:** 30 test sentences convert correctly ≥ 90% of the time, and invalid output never reaches execution.

### Phase 9 — Embeddings and schema mapping (Days 27–31)
- **Concept:** embeddings, cosine similarity, vector search, why names alone aren't enough (sample values + statistics).
- **Build:** a schema mapping assistant — source columns → destination columns with confidence; LLM confirms ambiguous matches and writes the transformation.
- **Done when:** mapping accuracy measured on a labelled set of schema pairs.

### Phase 10 — RAG over incident history (Days 32–35)
- **Concept:** chunking, retrieval, re-ranking, grounding, citing evidence, retrieval evaluation (recall@k).
- **Build:** a knowledge base of past incidents and runbooks; retrieval for similar failures.
- **Done when:** for an injected fault, the right past incident is in the top 3 results most of the time.

### Phase 11 — The failure triage agent (Days 36–42)
- **Concept:** agents, tool calling, the agent loop, **read-only tools**, step limits, evidence-based answers.
- **Build:** on failure, the agent inspects logs, schema history, profiles and similar incidents, then produces: root cause + evidence + suggested fix + confidence.
- **Done when:** diagnosis accuracy measured on all injected faults. This is your headline metric.

### Phase 12 — Human-in-the-loop approvals (Days 43–48)
- **Concept:** durable pause/resume, approval bound to the exact fix (hash), approval expiry, roles, audit trail, idempotent apply.
- **Build:** proposal store; Approve / Reject / Edit flow; fix applied to `dev` only after approval; quality re-check; separate promotion approval.
- **Done when:** editing a proposal after approval invalidates the approval; every action appears in the audit log.

### Phase 13 — AI security: data as untrusted input (Days 49–51)
- **Concept:** prompt injection through data values, least-privilege tools, output validation.
- **Build:** poisoned test datasets; hardening; a red-team test suite.
- **Done when:** no poisoned dataset can make the agent approve, promote, or run unsafe SQL.

### Phase 14 — Optimization (Days 52–58)
- **Concept:** latency and cost budgets, sampling vs full scans, caching (exact and semantic), batching LLM calls, model routing (small model first), quantization, streaming.
- **Build:** a benchmark script; apply one optimization at a time; record before/after.
- **Done when:** a table showing each optimization's effect on latency, cost (tokens), and accuracy.
- **GPU note:** vLLM needs a GPU. Without one, we optimize with Ollama + llama.cpp settings, which teaches the same concepts.

---

## Part C — Product, deployment and operations

### Phase 15 — API and UI (Days 59–64)
- **Build:** FastAPI backend (runs, alerts, proposals, approve, promote, rollback); Streamlit UI with a red / amber / green status board.

### Phase 16 — Observability (Days 65–67)
- **Concept:** logs vs metrics vs traces; LLM tracing.
- **Build:** structured logs; Prometheus metrics; Grafana dashboard; Langfuse traces of every AI call.

### Phase 17 — Docker (Days 68–71)
- **Concept:** images, layers, multi-stage builds, why model weights don't go in images, volumes, networks.
- **Build:** Dockerfiles per service; `docker compose` with SQL Server (free Developer image), Ollama, API, UI, worker.
- **Done when:** `docker compose up` runs the whole system on a fresh machine.

### Phase 18 — CI/CD (Days 72–76)
- **Concept:** CI vs CD, test pyramid, **AI evaluation gates**, GitOps.
- **Build:** GitHub Actions: lint → unit tests → pipeline tests → AI eval (fault diagnosis must not regress) → build images → push to GHCR.
- **Done when:** a pull request that lowers diagnosis accuracy is automatically blocked.

### Phase 19 — Kubernetes (Days 77–85)
- **Concept:** pods, deployments, services, config maps, secrets, namespaces, probes, resource limits, autoscaling, Helm, GitOps.
- **Build:** local cluster with kind; Helm chart; `dev` / `test` / `prod` namespaces; KEDA autoscaling of pipeline workers; Argo CD deploys from Git.
- **Done when:** a Git merge deploys automatically, and an Argo CD rollback restores the previous version.

### Phase 20 — Benchmark and showcase (Days 86–90)
- **Build:** publish the fault set as **MigrateBench**; compare 2–3 local models; write the README story with architecture diagram, metrics, and demo video.

---

## Progress tracker

Tick these off as you go.

- [ ] Phase 0 — Setup
- [ ] Phase 1 — Pipeline v1
- [ ] Phase 2 — Alerts
- [ ] Phase 3 — Promotion & rollback
- [ ] Phase 4 — Rule-based quality
- [ ] Phase 5 — Fault injection
- [ ] Phase 6 — Anomaly detection
- [ ] Phase 7 — LLM fundamentals
- [ ] Phase 8 — Structured output
- [ ] Phase 9 — Embeddings & mapping
- [ ] Phase 10 — RAG
- [ ] Phase 11 — Triage agent
- [ ] Phase 12 — Human approvals
- [ ] Phase 13 — AI security
- [ ] Phase 14 — Optimization
- [ ] Phase 15 — API & UI
- [ ] Phase 16 — Observability
- [ ] Phase 17 — Docker
- [ ] Phase 18 — CI/CD
- [ ] Phase 19 — Kubernetes
- [ ] Phase 20 — Benchmark & showcase
