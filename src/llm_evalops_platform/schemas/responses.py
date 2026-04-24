"""Pydantic schemas for API responses."""

from __future__ import annotations

from pydantic import BaseModel


class RunMetricResponse(BaseModel):
    metric_name: str
    metric_value: float


class RunResponse(BaseModel):
    app_type: str
    run_id: str
    schema_version: str
    status: str
    task_set_id: str | None
    dataset_version: str | None
    config_version: str | None
    model_version: str | None
    source_commit: str | None
    primary_artifact_path: str | None
    wall_duration_ms: int | None
    created_at: float


class RunListResponse(BaseModel):
    runs: list[RunResponse]
    total: int


class RunDetailResponse(BaseModel):
    run: RunResponse
    metrics: list[RunMetricResponse]


class MetricDeltaResponse(BaseModel):
    metric_name: str
    baseline_value: float | None
    candidate_value: float | None
    absolute_delta: float | None
    percent_delta: float | None


class CompareResponse(BaseModel):
    compare_session_id: int
    app_type: str
    task_set_id: str
    baseline_run_id: str
    candidate_run_id: str
    deltas: list[MetricDeltaResponse]


class RuleResultResponse(BaseModel):
    metric: str
    op: str
    threshold: float
    actual: float | None
    passed: bool
    reason: str | None = None


class GateResponse(BaseModel):
    release_decision_id: int
    compare_session_id: int
    decision: str   # "promoted" | "rejected"
    detail: list[RuleResultResponse]


class ArtifactResponse(BaseModel):
    artifact_type: str
    artifact_path: str
    created_at: float


class ArtifactListResponse(BaseModel):
    artifacts: list[ArtifactResponse]


class RunMetricsListResponse(BaseModel):
    metrics: list[RunMetricResponse]
