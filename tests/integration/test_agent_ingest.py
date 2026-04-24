"""Integration test: agent run ingest, normalization, and task_set_id rules.

Covers:
  - eval run → task_set_id computed from benchmark_name + task_ids
  - service run → task_set_id = None, blocked from compare
  - NULL field semantics (dataset_version always None for agent)
"""

from __future__ import annotations

import hashlib


EVAL_RUN = {
    "run_id": "agent-eval-run-001",
    "run_type": "eval",
    "status": "success",
    "total_steps": 12,
    "total_tool_calls": 28,
    "tool_success_rate": 0.89,
    "total_tokens": 15200,
    "termination_reason": "task_completed",
    "wall_duration_ms": 47000,
    "git_commit": "abc1234",
    "preset": "default",
    "llm_profile": "claude-3-5-sonnet",
    "benchmark_name": "swe_bench_lite",
    "task_ids": ["django-001", "flask-002", "requests-003"],
}

SERVICE_RUN = {
    "run_id": "agent-service-run-001",
    "run_type": "service",
    "status": "success",
    "total_steps": 5,
    "total_tool_calls": 10,
    "tool_success_rate": 1.0,
    "total_tokens": 3000,
    "wall_duration_ms": 12000,
    "preset": "default",
    "llm_profile": "claude-3-5-sonnet",
}


def _expected_task_set_id(benchmark_name: str, task_ids: list[str]) -> str:
    key = f"{benchmark_name}:{','.join(sorted(task_ids))}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def test_eval_run_task_set_id(client, run_worker):
    client.post("/v1/ingest/agent/v1", json=EVAL_RUN)
    run_worker()

    r = client.get(f"/v1/runs/agent/{EVAL_RUN['run_id']}")
    assert r.status_code == 200
    run = r.json()["run"]
    expected = _expected_task_set_id("swe_bench_lite", EVAL_RUN["task_ids"])
    assert run["task_set_id"] == expected
    assert run["dataset_version"] is None
    assert run["config_version"] == "default"
    assert run["model_version"] == "claude-3-5-sonnet"
    assert run["source_commit"] == "abc1234"
    assert run["wall_duration_ms"] == 47000


def test_service_run_null_task_set_id(client, run_worker):
    client.post("/v1/ingest/agent/v1", json=SERVICE_RUN)
    run_worker()

    r = client.get(f"/v1/runs/agent/{SERVICE_RUN['run_id']}")
    assert r.status_code == 200
    assert r.json()["run"]["task_set_id"] is None


def test_service_run_cannot_compare(client, run_worker):
    client.post("/v1/ingest/agent/v1", json=EVAL_RUN)
    client.post("/v1/ingest/agent/v1", json=SERVICE_RUN)
    run_worker()

    r = client.post("/v1/compare", json={
        "app_type": "agent",
        "baseline_run_id": SERVICE_RUN["run_id"],
        "candidate_run_id": EVAL_RUN["run_id"],
    })
    assert r.status_code == 422
