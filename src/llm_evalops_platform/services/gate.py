"""Gate service — evaluates a rule set against a compare session.

Op groups (PROJECT_PLAN.md Section 5):
  Absolute:   gte / lte / gt / lt      — candidate metric value vs threshold
  Delta abs:  delta_abs_gte / delta_abs_lte — absolute_delta vs threshold
  Delta pct:  delta_pct_gte / delta_pct_lte — percent_delta vs threshold (0.15 = 15%)

Boundary conditions:
  - delta_pct_* when percent_delta is None (baseline==0):
      passed=False, reason="percent_delta_undefined"
  - rule metric not found in compare result:
      passed=False, reason="metric_missing"
  - required=True  and passed=False → whole gate is "rejected"
  - required=False and passed=False → recorded in detail only
"""

from __future__ import annotations

import json
import time

from llm_evalops_platform.domain.gate import GateRule, ReleaseDecision, RuleResult
from llm_evalops_platform.storage.db import db

_ABS_OPS = {
    "gte": lambda v, t: v >= t,
    "lte": lambda v, t: v <= t,
    "gt":  lambda v, t: v > t,
    "lt":  lambda v, t: v < t,
}


def _evaluate_rule(rule: GateRule, delta_map: dict[str, dict]) -> RuleResult:
    entry = delta_map.get(rule.metric)
    op = rule.op

    if entry is None:
        return RuleResult(
            metric=rule.metric, op=op, threshold=rule.threshold,
            actual=None, passed=False, reason="metric_missing",
        )

    if op in _ABS_OPS:
        cv = entry.get("candidate_value")
        if cv is None:
            return RuleResult(
                metric=rule.metric, op=op, threshold=rule.threshold,
                actual=None, passed=False, reason="metric_missing",
            )
        return RuleResult(
            metric=rule.metric, op=op, threshold=rule.threshold,
            actual=cv, passed=_ABS_OPS[op](cv, rule.threshold),
        )

    if op in ("delta_abs_gte", "delta_abs_lte"):
        ad = entry.get("absolute_delta")
        if ad is None:
            return RuleResult(
                metric=rule.metric, op=op, threshold=rule.threshold,
                actual=None, passed=False, reason="metric_missing",
            )
        fn = (lambda v, t: v >= t) if op == "delta_abs_gte" else (lambda v, t: v <= t)
        return RuleResult(
            metric=rule.metric, op=op, threshold=rule.threshold,
            actual=ad, passed=fn(ad, rule.threshold),
        )

    if op in ("delta_pct_gte", "delta_pct_lte"):
        pd = entry.get("percent_delta")
        if pd is None:
            return RuleResult(
                metric=rule.metric, op=op, threshold=rule.threshold,
                actual=None, passed=False, reason="percent_delta_undefined",
            )
        fn = (lambda v, t: v >= t) if op == "delta_pct_gte" else (lambda v, t: v <= t)
        return RuleResult(
            metric=rule.metric, op=op, threshold=rule.threshold,
            actual=pd, passed=fn(pd, rule.threshold),
        )

    raise ValueError(f"Unknown op: {op!r}")


def evaluate_gate(compare_session_id: int, rules: list[GateRule]) -> ReleaseDecision:
    with db.connection() as conn:
        row = conn.execute(
            "SELECT result_json FROM compare_sessions WHERE id = ?",
            (compare_session_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"compare_session {compare_session_id} not found")

        raw_deltas: list[dict] = json.loads(row["result_json"] or "[]")
        delta_map = {d["metric_name"]: d for d in raw_deltas}

        results = [_evaluate_rule(r, delta_map) for r in rules]
        rejected = any(
            not r.passed and rules[i].required
            for i, r in enumerate(results)
        )
        decision = "rejected" if rejected else "promoted"
        now = time.time()

        detail_json = json.dumps([
            {
                "metric": r.metric, "op": r.op, "threshold": r.threshold,
                "actual": r.actual, "passed": r.passed, "reason": r.reason,
            }
            for r in results
        ])
        rules_json = json.dumps([
            {"metric": r.metric, "op": r.op, "threshold": r.threshold, "required": r.required}
            for r in rules
        ])
        cursor = conn.execute(
            """
            INSERT INTO release_decisions
                (compare_session_id, rules_json, decision, detail_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (compare_session_id, rules_json, decision, detail_json, now),
        )
        conn.commit()
        decision_id = cursor.lastrowid

    return ReleaseDecision(
        id=decision_id,
        compare_session_id=compare_session_id,
        decision=decision,
        detail=results,
        created_at=now,
    )
