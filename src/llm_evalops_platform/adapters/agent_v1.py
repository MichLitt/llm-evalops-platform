"""Adapter for agent/v1 — maps llm-coding-agent-system run summary to NormalizedOutput.

Field contract (PROJECT_PLAN.md Section 3.2):

task_set_id rules:
  - eval run (run_type="eval", benchmark_name + task_ids present):
      sha256(f"{benchmark_name}:{','.join(sorted(task_ids))}")[:16]
  - service run (run_type="service" or missing benchmark_name/task_ids):
      None  — cannot participate in compare

Other mappings:
  config_version  ← preset
  model_version   ← llm_profile
  source_commit   ← git_commit
  dataset_version = None  (agent runs have no fixed dataset)
  wall_duration_ms← wall_duration_ms  (real wall time; semantically consistent with domain)
"""

from __future__ import annotations

import hashlib
from typing import Any

from llm_evalops_platform.adapters.base import REGISTRY, BaseAdapter, NormalizedOutput

_METRIC_FIELDS = [
    "total_steps", "total_tool_calls", "tool_success_rate", "total_tokens",
    # Controlled-evaluation extensions.  They remain optional so existing
    # service reports keep their stable contract while G3 aggregate reports
    # can be compared and gated without a parallel schema.
    "verification_pass_rate", "tool_retry_rate", "retrieval_hit_rate",
    "citation_correctness_rate", "wall_latency_p50_ms",
    "wall_latency_p95_ms", "estimated_cost_usd",
]


def _compute_task_set_id(payload: dict[str, Any]) -> str | None:
    if payload.get("run_type") != "eval":
        return None
    benchmark = payload.get("benchmark_name")
    task_ids = payload.get("task_ids")
    if not benchmark or not task_ids:
        return None
    key = f"{benchmark}:{','.join(sorted(task_ids))}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


class AgentV1Adapter(BaseAdapter):
    def normalize(self, payload: dict[str, Any]) -> NormalizedOutput:
        metrics: list[tuple[str, float]] = []
        for name in _METRIC_FIELDS:
            val = payload.get(name)
            if val is not None:
                metrics.append((name, float(val)))

        wall = payload.get("wall_duration_ms")

        return NormalizedOutput(
            app_type="agent",
            run_id=payload["run_id"],
            schema_version="agent/v1",
            status=payload.get("status", "unknown"),
            task_set_id=_compute_task_set_id(payload),
            dataset_version=None,
            config_version=payload.get("preset") or None,
            model_version=payload.get("llm_profile") or None,
            source_commit=payload.get("git_commit") or None,
            wall_duration_ms=int(wall) if wall is not None else None,
            metrics=metrics,
        )


REGISTRY["agent/v1"] = AgentV1Adapter()
