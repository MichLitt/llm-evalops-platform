# CLAUDE.md

## Commands

- Install: `uv sync`
- Run API server: `uv run python scripts/start_api.py`
- Run normalization worker: `uv run python scripts/start_worker.py`
- Run all tests: `uv run pytest`
- Run integration tests only: `uv run pytest tests/integration/ -v`
- Run unit tests only: `uv run pytest tests/unit/ -v`
- Add a dependency: `uv add <package>`
- Add a dev dependency: `uv add --dev <package>`

## Environment

Copy `.env.example` to `.env` before first run:

```
cp .env.example .env
```

Key variables:
- `DATABASE_URL` — SQLite file path; directory is created automatically. Default: `./data/evalops.db`
- `API_HOST` / `API_PORT` — API bind address. Default: `127.0.0.1:8000`
- `WORKER_POLL_INTERVAL_SECS` — how often the worker polls for pending records. Default: `5`
- `WORKER_LEASE_TIMEOUT_SECS` — seconds before a `processing` record is reclaimed. Default: `60`
- `WORKER_MAX_RETRIES` — max normalization attempts before marking `failed`. Default: `3`

## Architecture

API and worker run as **separate processes** against the same SQLite file (WAL mode).  
See `docs/ARCHITECTURE.md` for the full ingest → normalize → compare → gate flow.  
See `docs/ADAPTERS.md` for producer field contracts and how to add a new adapter.

## Documentation Update Rules

After any structural change, check and update these if stale:

| What changed | Files to update |
|---|---|
| Directory structure / module added or removed | `docs/ARCHITECTURE.md` Section "Directory Structure" |
| DB schema changed | `storage/migrations/` (new numbered file) + `docs/ARCHITECTURE.md` schema tables + `PROJECT_PLAN.md` Section 3.1 |
| New adapter added | `adapters/base.py` REGISTRY + `docs/ADAPTERS.md` + `PROJECT_PLAN.md` Sections 3.2 and 7 |
| API endpoint added or changed | `docs/ARCHITECTURE.md` Section "API Endpoints" |
| Gate rule op added | `services/gate.py` + `docs/ARCHITECTURE.md` + `PROJECT_PLAN.md` Section 5 |
| Consistency check invalidated | `PROJECT_PLAN.md` Section 12 |

## Gate Rules

Gate rules use `delta_abs_*` (absolute difference in metric units) or `delta_pct_*` (decimal ratio, e.g. `0.15` = 15%).  
**Never use** `delta_gte` / `delta_lte` — these ambiguous op names are intentionally excluded.  
See `PROJECT_PLAN.md` Section 5 for the full op table and boundary condition handling.

## Adapter Registration

All adapters must be registered in `adapters/base.py` REGISTRY.  
The registry key is the canonical `schema_version` string, e.g. `"rag/v1"`.  
Adapters without a registry entry cause the worker to mark the record `unsupported` (no retry).
