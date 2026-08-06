"""Integration test: full RAG ingest → normalize → compare → gate chain.

Covers MVP acceptance criteria #1, #3, #4, #5 from PROJECT_PLAN.md Section 10.
"""

from __future__ import annotations

import pytest


RAG_BASELINE = {
    "run_id": "rag-run-baseline-001",
    "schema_version": "rag/v1",
    "dataset": "hotpotqa",
    "retriever_mode": "bm25",
    "generator_model": "claude-3-haiku",
    "num_queries": 100,
    "em": 0.55,
    "f1": 0.61,
    "recall_at_k": 0.80,
    "avg_faithfulness": 0.88,
    "hallucination_rate": 0.05,
    "avg_retrieval_latency_ms": 45.0,
    "avg_rerank_latency_ms": 0.0,
    "avg_generation_latency_ms": 320.0,
    "avg_query_expansion_latency_ms": 0.0,
    "total_generation_cost_usd": 0.12,
    "avg_generation_cost_usd": 0.0012,
}

RAG_CANDIDATE = {
    **RAG_BASELINE,
    "run_id": "rag-run-candidate-001",
    "retriever_mode": "dense",
    "em": 0.62,
    "f1": 0.68,
    "recall_at_k": 0.85,
    "avg_faithfulness": 0.90,
    "hallucination_rate": 0.04,
    "avg_retrieval_latency_ms": 80.0,
    "total_generation_cost_usd": 0.13,
    "avg_generation_cost_usd": 0.0013,
}

GATE_RULES = [
    {"metric": "f1",             "op": "gte",           "threshold": 0.60, "required": True},
    {"metric": "f1",             "op": "delta_pct_gte", "threshold": -0.05, "required": True},
    {"metric": "hallucination_rate", "op": "lte",       "threshold": 0.10, "required": True},
    {"metric": "avg_generation_cost_usd", "op": "delta_pct_lte", "threshold": 0.20, "required": False},
]


def test_rag_ingest_accepted(client, run_worker):
    r = client.post("/v1/ingest/rag/v1", json=RAG_BASELINE)
    assert r.status_code == 202
    assert r.json()["status"] == "accepted"
    assert r.json()["run_id"] == RAG_BASELINE["run_id"]


def test_rag_ingest_idempotent(client, run_worker):
    client.post("/v1/ingest/rag/v1", json=RAG_BASELINE)
    r2 = client.post("/v1/ingest/rag/v1", json=RAG_BASELINE)
    assert r2.status_code == 200
    assert r2.json()["status"] == "duplicate"


def test_rag_full_chain(client, run_worker, test_db):
    # 1. ingest both runs
    client.post("/v1/ingest/rag/v1", json=RAG_BASELINE)
    client.post("/v1/ingest/rag/v1", json=RAG_CANDIDATE)

    # 2. normalize
    run_worker()

    # 3. verify run detail and NULL semantics
    r = client.get(f"/v1/runs/rag/{RAG_BASELINE['run_id']}")
    assert r.status_code == 200
    run = r.json()["run"]
    assert run["task_set_id"] == "hotpotqa"
    assert run["config_version"] == "bm25"
    assert run["model_version"] == "claude-3-haiku"
    assert run["source_commit"] is None      # not available in rag/v1
    assert run["wall_duration_ms"] is None   # not available in rag/v1

    # verify derived metric
    metrics = {m["metric_name"]: m["metric_value"] for m in r.json()["metrics"]}
    assert "avg_end_to_end_latency_ms" in metrics
    assert metrics["avg_end_to_end_latency_ms"] == pytest.approx(365.0)  # 45+0+320+0

    # 4. compare
    comp = client.post("/v1/compare", json={
        "app_type": "rag",
        "baseline_run_id": RAG_BASELINE["run_id"],
        "candidate_run_id": RAG_CANDIDATE["run_id"],
    })
    assert comp.status_code == 201
    comp_data = comp.json()
    delta_map = {d["metric_name"]: d for d in comp_data["deltas"]}
    assert delta_map["f1"]["absolute_delta"] == pytest.approx(0.07)

    # 5. gate
    gate = client.post("/v1/gate", json={
        "compare_session_id": comp_data["compare_session_id"],
        "rules": GATE_RULES,
    })
    assert gate.status_code == 201
    gate_data = gate.json()
    assert gate_data["decision"] == "promoted"
    detail_map = {d["metric"]: d for d in gate_data["detail"]}
    assert detail_map["f1"]["passed"] is True
    assert detail_map["hallucination_rate"]["passed"] is True

    with test_db.connection() as conn:
        persisted = conn.execute(
            "SELECT decision FROM release_decisions WHERE id = ?",
            (gate_data["release_decision_id"],),
        ).fetchone()
    assert persisted is not None
    assert persisted["decision"] == "promoted"
