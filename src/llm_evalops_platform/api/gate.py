"""POST /v1/gate"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from llm_evalops_platform.domain.gate import GateRule
from llm_evalops_platform.schemas.responses import GateResponse, RuleResultResponse
from llm_evalops_platform.services.gate import evaluate_gate

router = APIRouter()


class GateRuleRequest(BaseModel):
    metric: str
    op: str
    threshold: float
    required: bool = True


class GateRequest(BaseModel):
    compare_session_id: int
    rules: list[GateRuleRequest]

    def to_domain(self) -> list[GateRule]:
        return [GateRule(metric=r.metric, op=r.op, threshold=r.threshold, required=r.required)
                for r in self.rules]


_VALID_OPS = {
    "gte", "lte", "gt", "lt",
    "delta_abs_gte", "delta_abs_lte",
    "delta_pct_gte", "delta_pct_lte",
}


@router.post("/gate", response_model=GateResponse, status_code=201)
def create_gate(req: GateRequest) -> GateResponse:
    if not req.rules:
        raise HTTPException(422, detail="rules must not be empty")
    for r in req.rules:
        if r.op not in _VALID_OPS:
            raise HTTPException(422, detail=f"Unknown op: {r.op!r}. Valid ops: {sorted(_VALID_OPS)}")

    try:
        decision = evaluate_gate(req.compare_session_id, req.to_domain())
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc))

    return GateResponse(
        release_decision_id=decision.id,
        compare_session_id=decision.compare_session_id,
        decision=decision.decision,
        detail=[
            RuleResultResponse(
                metric=r.metric, op=r.op, threshold=r.threshold,
                actual=r.actual, passed=r.passed, reason=r.reason,
            )
            for r in decision.detail
        ],
    )
