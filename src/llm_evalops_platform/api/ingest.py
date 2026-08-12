"""POST /v1/ingest/{app_type}/{version}

Idempotency: unique constraint on (app_type, schema_version, run_id).
Duplicate submissions return 200 with status="duplicate".
New submissions return 202 with status="accepted".

The canonical schema_version stored in the DB is f"{app_type}/{version}".
"""

from __future__ import annotations

import json
import time
from typing import Type

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from llm_evalops_platform.schemas.ingest import (
    AgentV1IngestRequest,
    BaseIngestRequest,
    FinetuneV1IngestRequest,
    IngestResponse,
    RagV1IngestRequest,
)
from llm_evalops_platform.storage.db import db

router = APIRouter()

_SCHEMA_MODELS: dict[str, Type[BaseIngestRequest]] = {
    "rag/v1": RagV1IngestRequest,
    "agent/v1": AgentV1IngestRequest,
    "finetune/v1": FinetuneV1IngestRequest,
}


@router.post(
    "/ingest/{app_type}/{version}",
    response_model=IngestResponse,
    status_code=202,
)
async def ingest_run(app_type: str, version: str, request: Request) -> IngestResponse:
    canonical_key = f"{app_type}/{version}"
    schema_model = _SCHEMA_MODELS.get(canonical_key)
    if schema_model is None:
        raise HTTPException(status_code=404, detail=f"Unknown schema: {canonical_key}")

    try:
        raw_payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    if not isinstance(raw_payload, dict):
        raise HTTPException(status_code=422, detail="JSON body must be an object")
    try:
        validated = schema_model.model_validate(raw_payload)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc

    payload = validated.model_dump(mode="json")
    run_id = validated.run_id

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
