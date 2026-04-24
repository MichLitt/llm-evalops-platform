"""Domain models for runs, metrics, and artifacts.

These are plain dataclasses used inside the application layer.
Pydantic schemas for API serialization live in schemas/.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RunMetric:
    metric_name: str
    metric_value: float


@dataclass
class Artifact:
    artifact_type: str
    artifact_path: str


@dataclass
class Run:
    id: int
    app_type: str
    run_id: str
    schema_version: str
    status: str
    created_at: float
    ingest_report_id: int | None = None
    task_set_id: str | None = None
    dataset_version: str | None = None
    config_version: str | None = None
    model_version: str | None = None
    source_commit: str | None = None
    primary_artifact_path: str | None = None
    wall_duration_ms: int | None = None
    metrics: list[RunMetric] = field(default_factory=list)
    artifacts: list[Artifact] = field(default_factory=list)
