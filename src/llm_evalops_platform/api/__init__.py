"""API layer — FastAPI routers, one module per resource group.

Modules
-------
ingest   — POST /v1/ingest/{app_type}/{version}
runs     — GET  /v1/runs, GET /v1/runs/{app_type}/{run_id}, GET .../metrics, .../artifacts
compare  — POST /v1/compare
gate     — POST /v1/gate

All routers are mounted in app.py under the /v1 prefix.
"""
