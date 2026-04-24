"""Adapter base class and registry.

Each adapter converts a raw ingest payload (dict) into the normalized fields
written to `runs` and `run_metrics`.  Register adapters with the REGISTRY dict
keyed by canonical schema_version string (e.g. "rag/v1").

The worker dispatches by looking up REGISTRY[schema_version].  If the key is
absent the record is marked `unsupported` and never retried.

To add a new adapter:
  1. Create adapters/{app_type}_v{n}.py and implement NormalizedOutput.
  2. Add an entry to REGISTRY at the bottom of this file.
  3. Update docs/ADAPTERS.md and PROJECT_PLAN.md Section 3.2.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class NormalizedOutput:
    """Flat representation written to runs + run_metrics by the worker."""
    # runs fields
    app_type: str
    run_id: str
    schema_version: str
    status: str
    task_set_id: str | None = None
    dataset_version: str | None = None
    config_version: str | None = None
    model_version: str | None = None
    source_commit: str | None = None
    primary_artifact_path: str | None = None
    wall_duration_ms: int | None = None
    # run_metrics rows: list of (name, value) pairs
    metrics: list[tuple[str, float]] = field(default_factory=list)


class BaseAdapter(ABC):
    @abstractmethod
    def normalize(self, payload: dict[str, Any]) -> NormalizedOutput:
        """Convert raw ingest payload to normalized output.

        Must not raise on missing optional fields — fill them as None.
        Should raise ValueError for genuinely malformed payloads (triggers retry).
        """


# Registry maps canonical schema_version → adapter instance.
# Import adapter modules below to populate this dict.
REGISTRY: dict[str, BaseAdapter] = {}
