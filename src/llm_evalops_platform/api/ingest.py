"""POST /v1/ingest/{app_type}/{version}

Idempotency: unique constraint on (app_type, schema_version, run_id).
Duplicate submissions return 200 with status="duplicate".
New submissions return 202 with status="accepted".

The canonical schema_version stored in the DB is f"{app_type}/{version}".
"""

from __future__ import annotations

import json
import time

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from llm_evalops_platform.schemas.ingest import IngestResponse
from llm_evalops_platform.storage.db import db

router = APIRouter()

_KNOWN_SCHEMAS = {"rag/v1", "agent/v1", "finetune/v1"}


@router.post(
    "/ingest/{app_type}/{version}",
    response_model=IngestResponse,
    status_code=202,
)
async def ingest_run(app_type: str, version: str, request: Request) -> IngestResponse:
    canonical_key = f"{app_type}/{version}"
    if canonical_key not in _KNOWN_SCHEMAS:
        raise HTTPException(status_code=404, detail=f"Unknown schema: {canonical_key}")

    try:
        payload: dict = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    run_id = payload.get("run_id")
    if not run_id:
        raise HTTPException(status_code=422, detail="Missing required field: run_id")

    raw = json.dumps(payload, ensure_ascii=False)
    now = time.time()

    t0 = time.perf_counter()
    with db.connection() as conn:
        existing = conn.execute(
            "SELECT id FROM ingested_reports WHERE app_type=? AND schema_version=? AND run_id=?",
            (app_type, canonical_key, run_id),
        ).fetchone()

        if existing:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            _log("duplicate", app_type, canonical_key, run_id, latency_ms)
            resp = IngestResponse(ingest_id=existing["id"], run_id=run_id, status="duplicate")
            return JSONResponse(status_code=200, content=resp.model_dump())

        cursor = conn.execute(
            """
            INSERT INTO ingested_reports
                (app_type, schema_version, run_id, raw_payload, status, received_at)
            VALUES (?, ?, ?, ?, 'pending', ?)
            """,
            (app_type, canonical_key, run_id, raw, now),
        )
        conn.commit()
        ingest_id = cursor.lastrowid

    latency_ms = int((time.perf_counter() - t0) * 1000)
    _log("accepted", app_type, canonical_key, run_id, latency_ms)
    return IngestResponse(ingest_id=ingest_id, run_id=run_id, status="accepted")


def _log(status: str, app_type: str, schema_version: str, run_id: str, latency_ms: int) -> None:
    import logging
    logging.getLogger(__name__).info(
        '{"event":"ingest","status":"%s","app_type":"%s","schema_version":"%s","run_id":"%s","latency_ms":%d}',
        status, app_type, schema_version, run_id, latency_ms,
    )
