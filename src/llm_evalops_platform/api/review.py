"""Public API for human review of compare sessions and failure cases."""
from __future__ import annotations

import json
import time

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from llm_evalops_platform.storage.db import db

router = APIRouter()


class BadCaseCreateRequest(BaseModel):
    case_id: str = Field(min_length=1, max_length=256)
    tag: str = Field(min_length=1, max_length=64)
    note: str | None = Field(default=None, max_length=2000)


class BadCaseResponse(BaseModel):
    id: int
    app_type: str
    run_id: str
    case_id: str
    tag: str
    note: str | None
    created_at: float


class BadCaseListResponse(BaseModel):
    bad_cases: list[BadCaseResponse]
    total: int


class CompareSessionDetailResponse(BaseModel):
    compare_session_id: int
    app_type: str
    task_set_id: str
    baseline_run_id: str
    candidate_run_id: str
    result: list[dict]
    decisions: list[dict]


class CompareSessionListResponse(BaseModel):
    sessions: list[CompareSessionDetailResponse]
    total: int


def _run_pk(app_type: str, run_id: str) -> int:
    with db.connection() as conn:
        row = conn.execute(
            "SELECT id FROM runs WHERE app_type=? AND run_id=?", (app_type, run_id)
        ).fetchone()
    if row is None:
        raise HTTPException(404, detail=f"Run {app_type}/{run_id} not found")
    return int(row["id"])


def _to_bad_case(row) -> BadCaseResponse:
    return BadCaseResponse(
        id=row["id"], app_type=row["app_type"], run_id=row["run_id"],
        case_id=row["case_id"], tag=row["tag"], note=row["note"],
        created_at=row["created_at"],
    )


@router.post("/runs/{app_type}/{run_id}/bad-cases", response_model=BadCaseResponse, status_code=201)
def create_bad_case(app_type: str, run_id: str, req: BadCaseCreateRequest) -> BadCaseResponse:
    run_pk = _run_pk(app_type, run_id)
    with db.connection() as conn:
        cursor = conn.execute(
            "INSERT INTO bad_case_tags (run_pk,case_id,tag,note,created_at) VALUES (?,?,?,?,?)",
            (run_pk, req.case_id, req.tag, req.note, time.time()),
        )
        row = conn.execute(
            """SELECT b.*, r.app_type, r.run_id FROM bad_case_tags b
               JOIN runs r ON r.id=b.run_pk WHERE b.id=?""", (cursor.lastrowid,)
        ).fetchone()
        conn.commit()
    return _to_bad_case(row)


@router.get("/runs/{app_type}/{run_id}/bad-cases", response_model=BadCaseListResponse)
def list_run_bad_cases(app_type: str, run_id: str) -> BadCaseListResponse:
    run_pk = _run_pk(app_type, run_id)
    with db.connection() as conn:
        rows = conn.execute(
            """SELECT b.*, r.app_type, r.run_id FROM bad_case_tags b
               JOIN runs r ON r.id=b.run_pk WHERE b.run_pk=? ORDER BY b.created_at DESC""",
            (run_pk,),
        ).fetchall()
    cases = [_to_bad_case(row) for row in rows]
    return BadCaseListResponse(bad_cases=cases, total=len(cases))


@router.get("/bad-cases", response_model=BadCaseListResponse)
def list_bad_cases(
    app_type: str | None = Query(default=None), tag: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500), offset: int = Query(default=0, ge=0),
) -> BadCaseListResponse:
    conditions: list[str] = []
    params: list[object] = []
    if app_type:
        conditions.append("r.app_type=?")
        params.append(app_type)
    if tag:
        conditions.append("b.tag=?")
        params.append(tag)
    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    query = """SELECT b.*, r.app_type, r.run_id FROM bad_case_tags b
               JOIN runs r ON r.id=b.run_pk""" + where
    with db.connection() as conn:
        total = conn.execute("SELECT COUNT(*) FROM (" + query + ")", params).fetchone()[0]
        rows = conn.execute(query + " ORDER BY b.created_at DESC LIMIT ? OFFSET ?", params + [limit, offset]).fetchall()
    return BadCaseListResponse(bad_cases=[_to_bad_case(row) for row in rows], total=total)


@router.get("/compare/{compare_session_id}", response_model=CompareSessionDetailResponse)
def get_compare_session(compare_session_id: int) -> CompareSessionDetailResponse:
    return _compare_detail(compare_session_id)


def _compare_detail(compare_session_id: int) -> CompareSessionDetailResponse:
    with db.connection() as conn:
        session = conn.execute("SELECT * FROM compare_sessions WHERE id=?", (compare_session_id,)).fetchone()
        if session is None:
            raise HTTPException(404, detail=f"Compare session {compare_session_id} not found")
        decisions = conn.execute(
            "SELECT id,decision,rules_json,detail_json,created_at FROM release_decisions WHERE compare_session_id=? ORDER BY created_at DESC",
            (compare_session_id,),
        ).fetchall()
    return CompareSessionDetailResponse(
        compare_session_id=session["id"], app_type=session["app_type"], task_set_id=session["task_set_id"],
        baseline_run_id=session["baseline_run_id"], candidate_run_id=session["candidate_run_id"],
        result=json.loads(session["result_json"] or "{}"),
        decisions=[{
            "release_decision_id": row["id"], "decision": row["decision"],
            "rules": json.loads(row["rules_json"]), "detail": json.loads(row["detail_json"]),
            "created_at": row["created_at"],
        } for row in decisions],
    )


@router.get("/compare", response_model=CompareSessionListResponse)
def list_compare_sessions(
    app_type: str | None = Query(default=None), limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> CompareSessionListResponse:
    conditions, params = [], []
    if app_type:
        conditions.append("app_type=?")
        params.append(app_type)
    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    with db.connection() as conn:
        total = conn.execute("SELECT COUNT(*) FROM compare_sessions" + where, params).fetchone()[0]
        ids = conn.execute(
            "SELECT id FROM compare_sessions" + where + " ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
    return CompareSessionListResponse(
        sessions=[_compare_detail(int(row["id"])) for row in ids], total=total
    )
