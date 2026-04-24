"""Unit tests for services/gate._evaluate_rule — edge cases and normal paths."""

from __future__ import annotations

import pytest

from llm_evalops_platform.domain.gate import GateRule
from llm_evalops_platform.services.gate import _evaluate_rule


def _entry(*, candidate_value=None, absolute_delta=None, percent_delta=None):
    return {
        "candidate_value": candidate_value,
        "absolute_delta": absolute_delta,
        "percent_delta": percent_delta,
    }


# ── metric_missing ────────────────────────────────────────────────────────────

def test_metric_not_in_delta_map():
    rule = GateRule(metric="f1", op="gte", threshold=0.5, required=True)
    result = _evaluate_rule(rule, {})
    assert result.passed is False
    assert result.reason == "metric_missing"


def test_candidate_value_none_abs_op():
    rule = GateRule(metric="f1", op="gte", threshold=0.5, required=True)
    result = _evaluate_rule(rule, {"f1": _entry(candidate_value=None)})
    assert result.passed is False
    assert result.reason == "metric_missing"


def test_absolute_delta_none_delta_abs_op():
    rule = GateRule(metric="f1", op="delta_abs_gte", threshold=0.0, required=True)
    result = _evaluate_rule(rule, {"f1": _entry(absolute_delta=None)})
    assert result.passed is False
    assert result.reason == "metric_missing"


# ── percent_delta_undefined (baseline == 0) ───────────────────────────────────

def test_percent_delta_none_pct_gte():
    rule = GateRule(metric="f1", op="delta_pct_gte", threshold=-0.05, required=True)
    result = _evaluate_rule(rule, {"f1": _entry(percent_delta=None)})
    assert result.passed is False
    assert result.reason == "percent_delta_undefined"


def test_percent_delta_none_pct_lte():
    rule = GateRule(metric="cost", op="delta_pct_lte", threshold=0.10, required=False)
    result = _evaluate_rule(rule, {"cost": _entry(percent_delta=None)})
    assert result.passed is False
    assert result.reason == "percent_delta_undefined"


# ── absolute ops ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("op,cv,threshold,expected", [
    ("gte", 0.8, 0.8, True),
    ("gte", 0.79, 0.8, False),
    ("lte", 0.05, 0.10, True),
    ("lte", 0.11, 0.10, False),
    ("gt",  0.81, 0.8, True),
    ("gt",  0.8,  0.8, False),
    ("lt",  0.09, 0.10, True),
    ("lt",  0.10, 0.10, False),
])
def test_abs_op(op, cv, threshold, expected):
    rule = GateRule(metric="m", op=op, threshold=threshold, required=True)
    result = _evaluate_rule(rule, {"m": _entry(candidate_value=cv)})
    assert result.passed is expected
    assert result.reason is None


# ── delta_abs ops ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("op,ad,threshold,expected", [
    ("delta_abs_gte", 0.05, 0.0,  True),
    ("delta_abs_gte", -0.01, 0.0, False),
    ("delta_abs_lte", -0.01, 0.0, True),
    ("delta_abs_lte", 0.01,  0.0, False),
])
def test_delta_abs_op(op, ad, threshold, expected):
    rule = GateRule(metric="m", op=op, threshold=threshold, required=True)
    result = _evaluate_rule(rule, {"m": _entry(absolute_delta=ad)})
    assert result.passed is expected
    assert result.reason is None


# ── delta_pct ops ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("op,pd,threshold,expected", [
    ("delta_pct_gte", -0.02, -0.05, True),   # -2% >= -5% → pass
    ("delta_pct_gte", -0.06, -0.05, False),  # -6% >= -5% → fail
    ("delta_pct_lte", 0.10,  0.15,  True),   # 10% <= 15% → pass
    ("delta_pct_lte", 0.16,  0.15,  False),  # 16% <= 15% → fail
])
def test_delta_pct_op(op, pd, threshold, expected):
    rule = GateRule(metric="m", op=op, threshold=threshold, required=True)
    result = _evaluate_rule(rule, {"m": _entry(percent_delta=pd)})
    assert result.passed is expected
    assert result.reason is None
