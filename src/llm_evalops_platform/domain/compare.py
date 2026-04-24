"""Domain models for compare sessions.

percent_delta is None when baseline == 0 (avoid division by zero).
The gate layer handles None percent_delta via the boundary conditions in
PROJECT_PLAN.md Section 5.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MetricDelta:
    metric_name: str
    baseline_value: float | None
    candidate_value: float | None
    absolute_delta: float | None    # candidate - baseline; None if either value missing
    percent_delta: float | None     # (candidate - baseline) / |baseline|; None if baseline == 0


@dataclass
class CompareResult:
    deltas: list[MetricDelta]


@dataclass
class CompareSession:
    id: int
    app_type: str
    task_set_id: str
    baseline_run_id: str
    candidate_run_id: str
    result: CompareResult
    created_at: float
