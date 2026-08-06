"""Pydantic schemas for ingest request payloads.

All ingest schemas share a base requiring `run_id`.
Unknown extra fields are forwarded as-is so the raw payload can always be
stored verbatim in ingested_reports.raw_payload.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

RunId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class BaseIngestRequest(BaseModel):
    run_id: RunId

    model_config = ConfigDict(extra="allow")


class RagV1IngestRequest(BaseIngestRequest):
    """Matches rag-benchmark-system EvalRunReport fields."""
    schema_version: Literal["rag/v1"] = "rag/v1"
    dataset: str = ""
    retriever_mode: str = ""
    generator_model: str = ""
    num_queries: int = 0
    em: float = 0.0
    f1: float = 0.0
    recall_at_k: float = 0.0
    avg_faithfulness: float | None = None
    hallucination_rate: float | None = None
    avg_retrieval_latency_ms: float = 0.0
    avg_rerank_latency_ms: float = 0.0
    avg_generation_latency_ms: float = 0.0
    avg_query_expansion_latency_ms: float = 0.0
    total_generation_cost_usd: float | None = None
    avg_generation_cost_usd: float | None = None


class AgentV1IngestRequest(BaseIngestRequest):
    """Matches llm-coding-agent-system EvalOpsClient payload."""
    schema_version: Literal["agent/v1"] = "agent/v1"
    run_type: Literal["eval", "service"]
    status: str = ""
    total_steps: int = 0
    total_tool_calls: int = 0
    tool_success_rate: float | None = None
    total_tokens: int = 0
    termination_reason: str | None = None
    wall_duration_ms: int = 0
    git_commit: str | None = None
    preset: str | None = None
    llm_profile: str | None = None
    # eval-only fields
    benchmark_name: str | None = None
    task_ids: list[str] | None = None


class FinetuneV1IngestRequest(BaseIngestRequest):
    """Stub — worker marks these unsupported until adapter is implemented."""
    schema_version: Literal["finetune/v1"] = "finetune/v1"


class IngestResponse(BaseModel):
    ingest_id: int
    run_id: str
    status: str   # "accepted" (new) or "duplicate" (idempotent hit)
