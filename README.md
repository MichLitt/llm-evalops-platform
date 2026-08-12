# LLM EvalOps Platform

Agent eval, observability, and release platform for the AI intern portfolio.

Receives completed run reports from upstream systems (agent, RAG, post-training), normalizes them into a unified schema, and supports cross-version comparison and threshold-based release gating.

**Current status (2026-08-06):** Agent/RAG MVP closure is complete. Ingest
payloads are validated against their versioned producer schemas; the full local
PDF → RAG → Agent tool → EvalOps compare/gate path is verified by the parent
workspace closure script. The local suite has 45 passing tests.

## Architecture

```
Producer (llm-coding-agent-system / rag-benchmark-system / finetune)
    │
    │  POST /v1/ingest/{app_type}/{version}
    ▼
┌─────────────────────────────────┐
│  Ingest API                     │
│  Pydantic validation + idempotent write  │
└────────────────┬────────────────┘
                 │  status = pending
                 ▼
┌─────────────────────────────────┐
│  Normalization Worker           │
│  Polls pending → routes via     │
│  REGISTRY → writes runs +       │
│  run_metrics                    │
└─────────────────────────────────┘

Consumer API
  GET  /v1/runs                          — list runs (filter by app_type, task_set_id, status)
  GET  /v1/runs/{app_type}/{run_id}      — single run detail
  GET  /v1/runs/{app_type}/{run_id}/metrics
  POST /v1/compare                       — cross-version metric delta
  POST /v1/gate                          — threshold-based release decision
```

The API and normalization worker run as **separate processes** against the same SQLite database (WAL mode). See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full ingest → normalize → compare → gate flow.

## Supported Producers

| Schema key | Producer | Status |
|------------|----------|--------|
| `agent/v1` | `llm-coding-agent-system` | Active |
| `rag/v1` | `rag-benchmark-system` | Active |
| `finetune/v1` | `coding-llm-finetune` | Stub (unsupported, no retry) |

See [`docs/ADAPTERS.md`](docs/ADAPTERS.md) for per-producer field contracts and how to add a new adapter.

## Quick Start

```bash
# Install
uv sync
cp .env.example .env

# Start API server (default: 127.0.0.1:8000)
uv run python scripts/start_api.py

# Start normalization worker (separate terminal)
uv run python scripts/start_worker.py

# Open the human review page (runs, compare/gate evidence, and bad-case tags)
open http://127.0.0.1:8000/ui/

# Run all tests
uv run pytest
```

The review page consumes only `/v1` endpoints. It shows normalized runs and
metrics, persisted compare/gate decisions, and lets reviewers tag an individual
run's failure case with a short taxonomy label and note. Programmatic clients
can use `GET/POST /v1/runs/{app_type}/{run_id}/bad-cases`, `GET /v1/bad-cases`,
and `GET /v1/compare[/{compare_session_id}]` directly.

### Enable reporting from producers

**llm-coding-agent-system:**
```bash
export EVALOPS_ENDPOINT=http://localhost:8000/v1/ingest/agent/v1
uv run python -m coder_agent run "fix the bug"
```

**rag-benchmark-system:**
```bash
export EVALOPS_ENDPOINT=http://localhost:8000/v1/ingest/rag/v1
uv run python scripts/run_naive_rag_baseline.py --config config/default.yaml --dataset hotpotqa --num-queries 50
```

### Compare two runs

```bash
curl -X POST http://localhost:8000/v1/compare \
  -H "Content-Type: application/json" \
  -d '{
    "app_type": "agent",
    "baseline_run_id": "run-abc",
    "candidate_run_id": "run-xyz"
  }'
```

The response contains `compare_session_id`; use it for the gate request.

### Check release gate

```bash
curl -X POST http://localhost:8000/v1/gate \
  -H "Content-Type: application/json" \
  -d '{
    "compare_session_id": 1,
    "rules": [
      {"metric": "tool_success_rate", "op": "gte", "threshold": 0.95},
      {"metric": "tool_success_rate", "op": "delta_abs_gte", "threshold": 0.05}
    ]
  }'
```

### Verify the three-project closure

From the parent workspace, run the real local HTTP workflow. It starts
temporary RAG and EvalOps services, uploads a generated PDF, calls the Agent
retrieval tool, submits both producer schemas, and persists two release
decisions:

```bash
./scripts/run_three_project_closure.sh
```

No LLM key, external model, or cloud service is required.

## Project Structure

```
src/llm_evalops_platform/
  api/          FastAPI routers — ingest, runs, compare, gate
  worker/       Normalization worker — polls pending records, routes via REGISTRY
  adapters/     Payload normalizers — one file per schema_version
  domain/       Pure Python dataclasses — Run, RunMetric, CompareResult, ReleaseDecision
  schemas/      Pydantic request/response models
  services/     Business logic — compare delta and gate evaluation
  storage/      SQLite connection management + migrations
```

## Tech Stack

| Component | Choice |
|-----------|--------|
| API | FastAPI + uvicorn |
| Database | SQLite (WAL mode) |
| Validation | Pydantic v2 + pydantic-settings |
| Tests | pytest + pytest-asyncio + httpx |
| Package manager | uv |
