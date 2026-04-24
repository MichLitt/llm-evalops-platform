"""Compare service — computes per-metric deltas between two runs.

percent_delta is set to None when baseline == 0 to avoid division by zero.
The gate layer reads None percent_delta and applies boundary conditions from
PROJECT_PLAN.md Section 5.
"""

from __future__ import annotations

import json
import time

from llm_evalops_platform.domain.compare import CompareResult, CompareSession, MetricDelta
from llm_evalops_platform.storage.db import db


def _pct_delta(candidate: float, baseline: float) -> float | None:
    if baseline == 0:
        return None
    return (candidate - baseline) / abs(baseline)


def compute_compare(
    app_type: str,
    baseline_run_id: str,
    candidate_run_id: str,
) -> CompareSession:
    """Fetch metrics for both runs, compute deltas, persist compare_session."""
    with db.connection() as conn:
        def get_run_pk(run_id: str) -> int | None:
            row = conn.execute(
                "SELECT id FROM runs WHERE app_type = ? AND run_id = ?",
                (app_type, run_id),
            ).fetchone()
            return row["id"] if row else None

        def get_task_set_id(run_pk: int) -> str | None:
            row = conn.execute(
                "SELECT task_set_id FROM runs WHERE id = ?", (run_pk,)
            ).fetchone()
            return row["task_set_id"] if row else None

        def get_metrics(run_pk: int) -> dict[str, float]:
            rows = conn.execute(
                "SELECT metric_name, metric_value FROM run_metrics WHERE run_pk = ?",
                (run_pk,),
            ).fetchall()
            return {r["metric_name"]: r["metric_value"] for r in rows}

        base_pk = get_run_pk(baseline_run_id)
        cand_pk = get_run_pk(candidate_run_id)
        if base_pk is None or cand_pk is None:
            raise ValueError("One or both run_ids not found")

        task_set_id = get_task_set_id(base_pk)
        if not task_set_id:
            raise ValueError("baseline run has no task_set_id; cannot compare")

        base_metrics = get_metrics(base_pk)
        cand_metrics = get_metrics(cand_pk)

        all_names = sorted(set(base_metrics) | set(cand_metrics))
        deltas: list[MetricDelta] = []
        for name in all_names:
            bv = base_metrics.get(name)
            cv = cand_metrics.get(name)
            abs_delta = (cv - bv) if (bv is not None and cv is not None) else None
            pct = _pct_delta(cv, bv) if (bv is not None and cv is not None) else None
            deltas.append(MetricDelta(
                metric_name=name,
                baseline_value=bv,
                candidate_value=cv,
                absolute_delta=abs_delta,
                percent_delta=pct,
            ))

        result_json = json.dumps([
            {
                "metric_name": d.metric_name,
                "baseline_value": d.baseline_value,
                "candidate_value": d.candidate_value,
                "absolute_delta": d.absolute_delta,
                "percent_delta": d.percent_delta,
            }
            for d in deltas
        ])
        now = time.time()
        cursor = conn.execute(
            """
            INSERT INTO compare_sessions
                (app_type, task_set_id, baseline_run_id, candidate_run_id, result_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (app_type, task_set_id, baseline_run_id, candidate_run_id, result_json, now),
        )
        conn.commit()
        session_id = cursor.lastrowid

    return CompareSession(
        id=session_id,
        app_type=app_type,
        task_set_id=task_set_id,
        baseline_run_id=baseline_run_id,
        candidate_run_id=candidate_run_id,
        result=CompareResult(deltas=deltas),
        created_at=now,
    )
