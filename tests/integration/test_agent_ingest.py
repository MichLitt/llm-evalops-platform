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


USAGE_RUN = {
    "run_id": "agent-usage-run-001",
    "run_type": "eval",
    "status": "success",
    "total_steps": 2,
    "total_tool_calls": 1,
    "tool_success_rate": 1.0,
    "total_tokens": 2280,
    "input_tokens": 2200,
    "output_tokens": 80,
    "llm_call_count": 2,
    "token_usage_status": "provider",
    "estimated_cost_usd": 0.00236,
    "wall_duration_ms": 9000,
    "benchmark_name": "custom",
    "task_ids": ["t1"],
}


def _metrics(client, run_id: str) -> dict[str, float]:
    r = client.get(f"/v1/runs/agent/{run_id}/metrics")
    assert r.status_code == 200
    return {m["metric_name"]: m["metric_value"] for m in r.json()["metrics"]}


def test_provider_usage_fields_become_metrics(client, run_worker):
    assert client.post("/v1/ingest/agent/v1", json=USAGE_RUN).status_code in (200, 201, 202)
    run_worker()

    metrics = _metrics(client, USAGE_RUN["run_id"])
    assert metrics["total_tokens"] == 2280
    assert metrics["input_tokens"] == 2200
    assert metrics["output_tokens"] == 80
    assert metrics["llm_call_count"] == 2
    assert metrics["estimated_cost_usd"] == 0.00236


def test_unreported_usage_is_accepted_without_token_metrics(client, run_worker):
    payload = {
        **USAGE_RUN,
        "run_id": "agent-usage-run-002",
        "total_tokens": None,
        "input_tokens": None,
        "output_tokens": None,
        "token_usage_status": "unavailable",
        "estimated_cost_usd": None,
    }
    assert client.post("/v1/ingest/agent/v1", json=payload).status_code in (200, 201, 202)
    run_worker()

    metrics = _metrics(client, payload["run_id"])
    assert "total_tokens" not in metrics
    assert "input_tokens" not in metrics
    assert "estimated_cost_usd" not in metrics
    assert metrics["llm_call_count"] == 2


def test_unknown_token_usage_status_is_rejected(client):
    payload = {**USAGE_RUN, "run_id": "agent-usage-run-003", "token_usage_status": "estimated"}
    assert client.post("/v1/ingest/agent/v1", json=payload).status_code == 422


AGGREGATE_RUN = {
    **USAGE_RUN,
    "run_id": "agent-aggregate-run-001",
    "benchmark_name": "swebench_verified_subset",
    "task_ids": ["a__x-1", "b__x-2"],
    "resolved_rate": 0.5,
    "wall_duration_ms": None,
}


def test_benchmark_aggregate_carries_resolved_rate_and_may_omit_wall_time(client, run_worker):
    assert client.post("/v1/ingest/agent/v1", json=AGGREGATE_RUN).status_code in (200, 201, 202)
    run_worker()

    r = client.get(f"/v1/runs/agent/{AGGREGATE_RUN['run_id']}")
    assert r.status_code == 200
    assert r.json()["run"]["wall_duration_ms"] is None
    assert _metrics(client, AGGREGATE_RUN["run_id"])["resolved_rate"] == 0.5


def test_resolved_rate_outside_unit_interval_is_rejected(client):
    payload = {**AGGREGATE_RUN, "run_id": "agent-aggregate-run-002", "wall_duration_ms": 1000, "resolved_rate": 70}
    assert client.post("/v1/ingest/agent/v1", json=payload).status_code == 422
