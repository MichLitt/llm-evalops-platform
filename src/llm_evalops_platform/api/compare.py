"""POST /v1/compare

Pre-conditions (returns 422 if violated):
  - Both (app_type, run_id) pairs must exist in runs table
  - Both runs must share the same app_type
  - Both runs must have the same non-NULL task_set_id
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from llm_evalops_platform.schemas.responses import CompareResponse, MetricDeltaResponse
from llm_evalops_platform.services.compare import compute_compare
from llm_evalops_platform.storage.db import db

router = APIRouter()


class CompareRequest(BaseModel):
    app_type: str
    baseline_run_id: str
    candidate_run_id: str


@router.post("/compare", response_model=CompareResponse, status_code=201)
def create_compare(req: CompareRequest) -> CompareResponse:
    with db.connection() as conn:
        def fetch_run(run_id: str) -> dict | None:
            row = conn.execute(
                "SELECT task_set_id FROM runs WHERE app_type = ? AND run_id = ?",
                (req.app_type, run_id),
            ).fetchone()
            return dict(row) if row else None

        base = fetch_run(req.baseline_run_id)
        cand = fetch_run(req.candidate_run_id)

    if base is None:
        raise HTTPException(422, detail=f"baseline run not found: {req.app_type}/{req.baseline_run_id}")
    if cand is None:
        raise HTTPException(422, detail=f"candidate run not found: {req.app_type}/{req.candidate_run_id}")
    if not base["task_set_id"]:
        raise HTTPException(422, detail="baseline run has no task_set_id; cannot compare")
    if not cand["task_set_id"]:
        raise HTTPException(422, detail="candidate run has no task_set_id; cannot compare")
    if base["task_set_id"] != cand["task_set_id"]:
        raise HTTPException(
            422,
            detail=f"task_set_id mismatch: {base['task_set_id']!r} vs {cand['task_set_id']!r}",
        )

    try:
        session = compute_compare(req.app_type, req.baseline_run_id, req.candidate_run_id)
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc))

    return CompareResponse(
        compare_session_id=session.id,
        app_type=session.app_type,
        task_set_id=session.task_set_id,
        baseline_run_id=session.baseline_run_id,
        candidate_run_id=session.candidate_run_id,
        deltas=[
            MetricDeltaResponse(
                metric_name=d.metric_name,
                baseline_value=d.baseline_value,
                candidate_value=d.candidate_value,
                absolute_delta=d.absolute_delta,
                percent_delta=d.percent_delta,
            )
            for d in session.result.deltas
        ],
    )
