"""Domain models for gate rules and release decisions.

Supported ops — two strictly separated groups:
  Absolute:  gte / lte / gt / lt
  Delta abs: delta_abs_gte / delta_abs_lte
  Delta pct: delta_pct_gte / delta_pct_lte  (threshold is a decimal: 0.15 = 15%)

Never use delta_gte / delta_lte (ambiguous, excluded by design).

Boundary conditions (see PROJECT_PLAN.md Section 5):
  - delta_pct_* with baseline == 0 → percent_delta = None → passed=False, reason="percent_delta_undefined"
  - Rule references missing metric → passed=False, reason="metric_missing"
    required=True  → whole gate is rejected
    required=False → recorded in detail but does not affect decision
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class GateRule:
    metric: str
    op: str          # see module docstring for valid ops
    threshold: float
    required: bool = True


@dataclass
class RuleResult:
    metric: str
    op: str
    threshold: float
    actual: float | None    # None when metric is missing or percent_delta undefined
    passed: bool
    reason: str | None = None  # "metric_missing" | "percent_delta_undefined" | None


@dataclass
class ReleaseDecision:
    id: int
    compare_session_id: int
    decision: str           # "promoted" | "rejected"
    detail: list[RuleResult]
    created_at: float
