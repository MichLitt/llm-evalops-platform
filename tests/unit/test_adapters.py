"""Unit tests for adapter field mapping — rag/v1 and agent/v1."""

from __future__ import annotations

import hashlib

import pytest

from llm_evalops_platform.adapters.rag_v1 import RagV1Adapter
from llm_evalops_platform.adapters.agent_v1 import AgentV1Adapter, _compute_task_set_id

_rag = RagV1Adapter()
_agent = AgentV1Adapter()


# ── rag/v1 ────────────────────────────────────────────────────────────────────

_RAG_PAYLOAD = {
    "run_id": "rag-001",
    "dataset": "hotpotqa",
    "retriever_mode": "bm25",
    "generator_model": "claude-3-haiku",
    "em": 0.55,
    "f1": 0.61,
    "avg_retrieval_latency_ms": 45.0,
    "avg_rerank_latency_ms": 10.0,
    "avg_generation_latency_ms": 320.0,
    "avg_query_expansion_latency_ms": 5.0,
}


def test_rag_field_mapping():
    out = _rag.normalize(_RAG_PAYLOAD)
    assert out.app_type == "rag"
    assert out.run_id == "rag-001"
    assert out.task_set_id == "hotpotqa"
    assert out.dataset_version == "hotpotqa"
    assert out.config_version == "bm25"
    assert out.model_version == "claude-3-haiku"


def test_rag_null_fields():
    out = _rag.normalize(_RAG_PAYLOAD)
    assert out.source_commit is None
    assert out.wall_duration_ms is None


def test_rag_end_to_end_latency_derived():
    out = _rag.normalize(_RAG_PAYLOAD)
    metric_map = dict(out.metrics)
    assert metric_map["avg_end_to_end_latency_ms"] == pytest.approx(380.0)  # 45+10+320+5


def test_rag_end_to_end_latency_missing_fields():
    payload = {**_RAG_PAYLOAD, "avg_rerank_latency_ms": None, "avg_query_expansion_latency_ms": None}
    out = _rag.normalize(payload)
    metric_map = dict(out.metrics)
    assert metric_map["avg_end_to_end_latency_ms"] == pytest.approx(365.0)  # 45+0+320+0


def test_rag_metrics_present():
    out = _rag.normalize(_RAG_PAYLOAD)
    metric_map = dict(out.metrics)
    assert "em" in metric_map
    assert "f1" in metric_map
    assert metric_map["f1"] == pytest.approx(0.61)


# ── agent/v1 ──────────────────────────────────────────────────────────────────

_AGENT_EVAL_PAYLOAD = {
    "run_id": "agent-eval-001",
    "run_type": "eval",
    "benchmark_name": "swe-bench",
    "task_ids": ["task-3", "task-1", "task-2"],
    "status": "completed",
    "preset": "default",
    "llm_profile": "claude-3-sonnet",
    "git_commit": "abc123",
    "wall_duration_ms": 90000,
    "total_steps": 12,
    "total_tool_calls": 30,
    "tool_success_rate": 0.9,
    "total_tokens": 5000,
    "verification_pass_rate": 0.8,
    "wall_latency_p95_ms": 12000,
}

_AGENT_SERVICE_PAYLOAD = {
    "run_id": "agent-svc-001",
    "run_type": "service",
    "status": "completed",
    "wall_duration_ms": 5000,
    "total_steps": 3,
    "tool_success_rate": 1.0,
    "total_tokens": 800,
}


def test_agent_eval_task_set_id_deterministic():
    out1 = _agent.normalize(_AGENT_EVAL_PAYLOAD)
    out2 = _agent.normalize(_AGENT_EVAL_PAYLOAD)
    assert out1.task_set_id == out2.task_set_id
    assert out1.task_set_id is not None
    assert len(out1.task_set_id) == 16


def test_agent_eval_task_set_id_sorted():
    # task_ids order should not affect result
    p1 = {**_AGENT_EVAL_PAYLOAD, "task_ids": ["task-1", "task-2", "task-3"]}
    p2 = {**_AGENT_EVAL_PAYLOAD, "task_ids": ["task-3", "task-1", "task-2"]}
    assert _agent.normalize(p1).task_set_id == _agent.normalize(p2).task_set_id


def test_agent_eval_task_set_id_value():
    expected = hashlib.sha256("swe-bench:task-1,task-2,task-3".encode()).hexdigest()[:16]
    assert _compute_task_set_id(_AGENT_EVAL_PAYLOAD) == expected


def test_agent_service_task_set_id_none():
    out = _agent.normalize(_AGENT_SERVICE_PAYLOAD)
    assert out.task_set_id is None


def test_agent_dataset_version_always_none():
    out = _agent.normalize(_AGENT_EVAL_PAYLOAD)
    assert out.dataset_version is None


def test_agent_field_mapping():
    out = _agent.normalize(_AGENT_EVAL_PAYLOAD)
    assert out.config_version == "default"
    assert out.model_version == "claude-3-sonnet"
    assert out.source_commit == "abc123"
    assert out.wall_duration_ms == 90000


def test_agent_metrics():
    out = _agent.normalize(_AGENT_EVAL_PAYLOAD)
    metric_map = dict(out.metrics)
    assert metric_map["tool_success_rate"] == pytest.approx(0.9)
    assert metric_map["total_tokens"] == pytest.approx(5000)
    assert metric_map["verification_pass_rate"] == pytest.approx(0.8)
    assert metric_map["wall_latency_p95_ms"] == pytest.approx(12000)
