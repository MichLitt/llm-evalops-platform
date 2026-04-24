"""GET /v1/runs and GET /v1/runs/{app_type}/{run_id}"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from llm_evalops_platform.schemas.responses import (
    ArtifactListResponse,
    ArtifactResponse,
    RunDetailResponse,
    RunListResponse,
    RunMetricResponse,
    RunMetricsListResponse,
    RunResponse,
)
from llm_evalops_platform.storage.db import db

router = APIRouter()


def _row_to_run(row) -> RunResponse:
    return RunResponse(
        app_type=row["app_type"],
        run_id=row["run_id"],
        schema_version=row["schema_version"],
        status=row["status"],
        task_set_id=row["task_set_id"],
        dataset_version=row["dataset_version"],
        config_version=row["config_version"],
        model_version=row["model_version"],
        source_commit=row["source_commit"],
        primary_artifact_path=row["primary_artifact_path"],
        wall_duration_ms=row["wall_duration_ms"],
        created_at=row["created_at"],
    )


@router.get("/runs", response_model=RunListResponse)
def list_runs(
    app_type: str | None = Query(default=None),
    task_set_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> RunListResponse:
    conditions = []
    params: list = []
    if app_type:
        conditions.append("app_type = ?")
        params.append(app_type)
    if task_set_id:
        conditions.append("task_set_id = ?")
        params.append(task_set_id)
    if status:
        conditions.append("status = ?")
        params.append(status)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    with db.connection() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM runs {where}", params).fetchone()[0]
        rows = conn.execute(
            f"SELECT * FROM runs {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()

    return RunListResponse(runs=[_row_to_run(r) for r in rows], total=total)


@router.get("/runs/{app_type}/{run_id}", response_model=RunDetailResponse)
def get_run(app_type: str, run_id: str) -> RunDetailResponse:
    with db.connection() as conn:
        row = conn.execute(
            "SELECT * FROM runs WHERE app_type = ? AND run_id = ?",
            (app_type, run_id),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Run {app_type}/{run_id} not found")

        metric_rows = conn.execute(
            "SELECT metric_name, metric_value FROM run_metrics WHERE run_pk = ?",
            (row["id"],),
        ).fetchall()

    return RunDetailResponse(
        run=_row_to_run(row),
        metrics=[RunMetricResponse(metric_name=r["metric_name"], metric_value=r["metric_value"])
                 for r in metric_rows],
    )


def _get_run_pk(conn, app_type: str, run_id: str) -> int:
    row = conn.execute(
        "SELECT id FROM runs WHERE app_type = ? AND run_id = ?",
        (app_type, run_id),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Run {app_type}/{run_id} not found")
    return row["id"]


@router.get("/runs/{app_type}/{run_id}/metrics", response_model=RunMetricsListResponse)
def get_run_metrics(app_type: str, run_id: str) -> RunMetricsListResponse:
    with db.connection() as conn:
        run_pk = _get_run_pk(conn, app_type, run_id)
        rows = conn.execute(
            "SELECT metric_name, metric_value FROM run_metrics WHERE run_pk = ?",
            (run_pk,),
        ).fetchall()
    return RunMetricsListResponse(
        metrics=[RunMetricResponse(metric_name=r["metric_name"], metric_value=r["metric_value"])
                 for r in rows],
    )


@router.get("/runs/{app_type}/{run_id}/artifacts", response_model=ArtifactListResponse)
def get_run_artifacts(app_type: str, run_id: str) -> ArtifactListResponse:
    with db.connection() as conn:
        run_pk = _get_run_pk(conn, app_type, run_id)
        rows = conn.execute(
            "SELECT artifact_type, artifact_path, created_at FROM artifacts WHERE run_pk = ?",
            (run_pk,),
        ).fetchall()
    return ArtifactListResponse(
        artifacts=[ArtifactResponse(
            artifact_type=r["artifact_type"],
            artifact_path=r["artifact_path"],
            created_at=r["created_at"],
        ) for r in rows],
    )
