"""Adapter for rag/v1 — maps EvalRunReport fields to NormalizedOutput.

Field contract (PROJECT_PLAN.md Section 3.2):
  task_set_id    ← dataset      (dataset name is the task set identifier)
  dataset_version← dataset
  config_version ← retriever_mode
  model_version  ← generator_model
  source_commit  = None         (not available in EvalRunReport)
  wall_duration_ms = None       (only per-query averages available; not a real wall time)

Latency metrics: each avg_*_latency_ms stored individually, plus a derived
avg_end_to_end_latency_ms = sum of all four averages.
"""

from __future__ import annotations

from typing import Any

from llm_evalops_platform.adapters.base import REGISTRY, BaseAdapter, NormalizedOutput

_METRIC_FIELDS = [
    "em", "f1", "recall_at_k",
    "avg_faithfulness", "hallucination_rate",
    "avg_retrieval_latency_ms", "avg_rerank_latency_ms",
    "avg_generation_latency_ms", "avg_query_expansion_latency_ms",
    "total_generation_cost_usd", "avg_generation_cost_usd",
]

_LATENCY_FIELDS = [
    "avg_retrieval_latency_ms",
    "avg_rerank_latency_ms",
    "avg_generation_latency_ms",
    "avg_query_expansion_latency_ms",
]


class RagV1Adapter(BaseAdapter):
    def normalize(self, payload: dict[str, Any]) -> NormalizedOutput:
        metrics: list[tuple[str, float]] = []

        for name in _METRIC_FIELDS:
            val = payload.get(name)
            if val is not None:
                metrics.append((name, float(val)))

        end_to_end = sum(
            float(payload.get(f) or 0) for f in _LATENCY_FIELDS
        )
        metrics.append(("avg_end_to_end_latency_ms", end_to_end))

        return NormalizedOutput(
            app_type="rag",
            run_id=payload["run_id"],
            schema_version="rag/v1",
            status="success",
            task_set_id=payload.get("dataset") or None,
            dataset_version=payload.get("dataset") or None,
            config_version=payload.get("retriever_mode") or None,
            model_version=payload.get("generator_model") or None,
            source_commit=None,
            wall_duration_ms=None,
            metrics=metrics,
        )


REGISTRY["rag/v1"] = RagV1Adapter()
