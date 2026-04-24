"""Adapter layer — converts raw ingest payloads to normalized runs + run_metrics.

Modules
-------
base        — BaseAdapter ABC, NormalizedOutput dataclass, REGISTRY dict
rag_v1      — EvalRunReport → runs + run_metrics  (registered as "rag/v1")
agent_v1    — agent run summary → runs + run_metrics  (registered as "agent/v1")
finetune_v1 — stub; NOT registered; worker marks finetune/v1 records as unsupported

Import all adapter modules here so their REGISTRY entries are populated
before the worker starts dispatching.
"""

from llm_evalops_platform.adapters import agent_v1, rag_v1  # noqa: F401 — side-effect imports
from llm_evalops_platform.adapters.base import REGISTRY, BaseAdapter, NormalizedOutput

__all__ = ["REGISTRY", "BaseAdapter", "NormalizedOutput"]
