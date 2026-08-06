# Architecture

## Overview

`llm-evalops-platform` is a passive ingest platform: it receives completed run reports from upstream systems (RAG, Agent, Finetune), normalizes them into a unified schema, and supports compare and gate operations.

```
Producer (RAG / Agent / Finetune)
    │
    │  POST /v1/ingest/{app_type}/{version}
    │  canonical_key = f"{app_type}/{version}"
    ▼
┌─────────────────────────────────┐
│  Ingest API                     │
│  - Pydantic schema validation   │
│  - Idempotent write             │
│    (unique: app_type+schema_version+run_id)
│  - Returns 202 (new) / 200 (dup)│
└────────────────┬────────────────┘
                 │  status = pending
                 ▼
┌─────────────────────────────────┐
│  Normalization Worker           │
│  - Polls pending records        │
│  - Reclaims timed-out           │
│    processing records           │
│  - Routes via REGISTRY          │
│  - Writes runs + run_metrics    │
└─────────────────────────────────┘

Consumer API
  GET  /v1/runs?app_type=&task_set_id=&status=&limit=&offset=
  GET  /v1/runs/{app_type}/{run_id}
  GET  /v1/runs/{app_type}/{run_id}/metrics
  POST /v1/compare
  POST /v1/gate
```

## Directory Structure

```
llm-evalops-platform/
│
├── pyproject.toml            Python 3.12, uv, FastAPI, Pydantic, pydantic-settings
├── .python-version           Pins Python 3.12 for uv
├── .env.example              Environment variable template
├── AGENTS.md                 Canonical commands and engineering invariants
├── CLAUDE.md                 Compatibility pointer to AGENTS.md
│
├── src/llm_evalops_platform/
│   │
│   ├── __init__.py           Package version
│   ├── config.py             Settings (pydantic-settings, reads from .env)
│   ├── app.py                FastAPI app factory; mounts all routers
│   │
│   ├── api/                  FastAPI routers — one file per resource group
│   │   ├── ingest.py         POST /v1/ingest/{app_type}/{version}
│   │   ├── runs.py           GET /v1/runs, GET /v1/runs/{app_type}/{run_id}
│   │   ├── compare.py        POST /v1/compare
│   │   └── gate.py           POST /v1/gate
│   │
│   ├── worker/               Normalization worker — runs as a separate process
│   │   └── normalizer.py     process_one() + run_loop() + claim/reclaim state machine
│   │
│   ├── domain/               Pure Python dataclasses — no framework imports
│   │   ├── runs.py           Run, RunMetric, Artifact
│   │   ├── compare.py        MetricDelta, CompareResult, CompareSession
│   │   └── gate.py           GateRule, RuleResult, ReleaseDecision
│   │
│   ├── storage/              SQLite connection management
│   │   ├── db.py             Database class + shared `db` singleton
│   │   └── migrations/
│   │       └── 001_initial.sql   Full schema; add numbered files for future changes
│   │
│   ├── adapters/             Payload normalizers — one file per schema_version
│   │   ├── base.py           BaseAdapter ABC, NormalizedOutput, REGISTRY dict
│   │   ├── rag_v1.py         EvalRunReport → NormalizedOutput (registered as "rag/v1")
│   │   ├── agent_v1.py       agent run summary → NormalizedOutput (registered as "agent/v1")
│   │   └── finetune_v1.py    Stub — NOT registered; worker marks records unsupported
│   │
│   ├── services/             Business logic — called by API routers
│   │   ├── compare.py        compute_compare(): fetch metrics, compute deltas, persist
│   │   └── gate.py           evaluate_gate(): apply GateRule list, persist decision
│   │
│   └── schemas/              Pydantic models for API boundary
│       ├── ingest.py         Per-schema ingest requests; IngestResponse
│       └── responses.py      RunResponse, CompareResponse, GateResponse, etc.
│
├── scripts/
│   ├── start_api.py          Entry point: uvicorn server
│   └── start_worker.py       Entry point: normalization worker loop
│
├── tests/
│   ├── conftest.py           Shared fixtures: test_db, client, run_worker
│   ├── integration/          End-to-end tests against real DB and API
│   │   ├── test_rag_ingest_to_gate.py   Full RAG chain (MVP acceptance test)
│   │   ├── test_agent_ingest.py         Agent ingest + task_set_id rules
│   │   ├── test_idempotent_ingest.py    Duplicate submission handling
│   │   └── test_ingest_validation.py    Versioned producer schema validation
│   └── unit/                 Isolated unit tests (gate rule engine, adapters, etc.)
│
└── docs/
    ├── ARCHITECTURE.md       This file
    └── ADAPTERS.md           Producer field contracts; how to add a new adapter
```

## Data Model

See `PROJECT_PLAN.md` Section 3 for the full table definitions.

Key relationships:

```
ingested_reports (raw audit)
    │ ingest_report_id FK
    ▼
runs (normalized, surrogate PK `id`)
    ├── run_metrics  (run_pk FK → runs.id)
    ├── artifacts    (run_pk FK → runs.id)
    └── bad_case_tags (run_pk FK → runs.id)

compare_sessions
    │ compare_session_id FK
    ▼
release_decisions
```

## API Endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/v1/ingest/{app_type}/{version}` | Submit a run report; 202 new / 200 duplicate |
| GET | `/v1/runs` | List runs; supports `app_type`, `task_set_id`, `status`, `limit`, `offset` |
| GET | `/v1/runs/{app_type}/{run_id}` | Run detail with metrics |
| POST | `/v1/compare` | Compare two runs; validates same `app_type` and `task_set_id` |
| POST | `/v1/gate` | Apply rules to a compare session; returns `promoted`/`rejected` |
| GET | `/health` | Liveness check |

## Worker State Machine

```
pending ──(claim)──► processing ──(success)──► processed
                         │
                         ├──(error, attempt < max)──► pending (attempt_count++)
                         ├──(error, attempt >= max)──► failed
                         └──(no adapter)──────────► unsupported
```

Reclaim: if a `processing` record has `claimed_at < now - LEASE_TIMEOUT_SECS`, the worker
resets it to `pending` on its next poll cycle.
