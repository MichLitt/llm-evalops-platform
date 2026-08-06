# AGENTS.md

When this repository is checked out inside `agent-systems-portfolio`, also read
`../AGENTS.md` and `../docs/engineering/ENGINEERING_GUIDE.md`. This file remains
the complete local entry point for a standalone clone and defines
EvalOps-specific rules.

## Commands

- Install: `uv sync && cp .env.example .env`
- API: `uv run python scripts/start_api.py`
- Worker: `uv run python scripts/start_worker.py`
- All tests: `uv run pytest`
- Integration tests: `uv run pytest tests/integration/ -v`
- Unit tests: `uv run pytest tests/unit/ -v`

## Architecture Invariants

- API and worker are separate processes using the same SQLite database in WAL mode.
- Raw reports enter `ingested_reports`; only the worker writes normalized `runs` and `run_metrics`.
- Ingest is idempotent by `(app_type, schema_version, run_id)`.
- URL schema and payload `schema_version` must match and pass the Pydantic producer model.
- Unknown/unregistered adapters become `unsupported` and are not retried.
- Compare requires matching non-null task sets; gate consumes a persisted compare session.

## Environment

- `DATABASE_URL` — SQLite path; default `./data/evalops.db`
- `API_HOST` / `API_PORT` — default `127.0.0.1:8000`
- `WORKER_POLL_INTERVAL_SECS` — default 5
- `WORKER_LEASE_TIMEOUT_SECS` — default 60
- `WORKER_MAX_RETRIES` — default 3

## Contract Changes

When changing `agent/v1` or `rag/v1`:

1. Update `schemas/ingest.py` and the matching adapter.
2. Update `docs/ADAPTERS.md` and `docs/ARCHITECTURE.md`.
3. Update `PROJECT_PLAN.md` if its contract/status becomes stale.
4. Run EvalOps tests plus the producer's tests.
5. Run `../scripts/run_three_project_closure.sh`.

Gate ops use explicit `delta_abs_*` or `delta_pct_*` names. Never introduce
ambiguous `delta_gte` / `delta_lte` aliases.

## Database Changes

- Add a new numbered migration; never rewrite an applied migration silently.
- Update architecture schema documentation in the same task.
- Add migration and backward-compatibility coverage.

## Required Handoff

- `uv run pytest` passes.
- Contract changes pass the root closure script.
- `README.md`, `PROJECT_PLAN.md`, `docs/ARCHITECTURE.md`, and `docs/ADAPTERS.md` agree.
- `git diff --check` passes.
