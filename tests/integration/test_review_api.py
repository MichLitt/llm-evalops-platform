"""Review-loop API tests: human tags and persisted compare/gate evidence."""
from __future__ import annotations

from tests.integration.test_rag_ingest_to_gate import GATE_RULES, RAG_BASELINE, RAG_CANDIDATE


def _create_compared_runs(client, run_worker) -> int:
    assert client.post("/v1/ingest/rag/v1", json=RAG_BASELINE).status_code == 202
    assert client.post("/v1/ingest/rag/v1", json=RAG_CANDIDATE).status_code == 202
    run_worker()
    compare = client.post("/v1/compare", json={
        "app_type": "rag", "baseline_run_id": RAG_BASELINE["run_id"],
        "candidate_run_id": RAG_CANDIDATE["run_id"],
    })
    assert compare.status_code == 201
    session_id = compare.json()["compare_session_id"]
    gate = client.post("/v1/gate", json={"compare_session_id": session_id, "rules": GATE_RULES})
    assert gate.status_code == 201
    return session_id


def test_create_and_list_bad_case_for_run(client, run_worker):
    _create_compared_runs(client, run_worker)
    created = client.post(
        f"/v1/runs/rag/{RAG_CANDIDATE['run_id']}/bad-cases",
        json={"case_id": "hotpotqa-42", "tag": "missing-citation", "note": "Page range absent."},
    )
    assert created.status_code == 201
    assert created.json()["run_id"] == RAG_CANDIDATE["run_id"]

    listed = client.get(f"/v1/runs/rag/{RAG_CANDIDATE['run_id']}/bad-cases")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["bad_cases"][0]["tag"] == "missing-citation"


def test_bad_case_cross_run_filter_and_missing_run(client, run_worker):
    _create_compared_runs(client, run_worker)
    client.post(
        f"/v1/runs/rag/{RAG_CANDIDATE['run_id']}/bad-cases",
        json={"case_id": "case-1", "tag": "retrieval-miss"},
    )
    filtered = client.get("/v1/bad-cases", params={"app_type": "rag", "tag": "retrieval-miss"})
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1
    missing = client.post("/v1/runs/rag/not-real/bad-cases", json={"case_id": "x", "tag": "x"})
    assert missing.status_code == 404


def test_compare_session_detail_contains_metrics_and_gate_evidence(client, run_worker):
    session_id = _create_compared_runs(client, run_worker)
    response = client.get(f"/v1/compare/{session_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["baseline_run_id"] == RAG_BASELINE["run_id"]
    assert any(delta["metric_name"] == "f1" for delta in data["result"])
    assert data["decisions"][0]["decision"] == "promoted"
    assert client.get("/v1/compare/9999").status_code == 404


def test_compare_session_list_and_ui_are_public(client, run_worker):
    _create_compared_runs(client, run_worker)
    listed = client.get("/v1/compare")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    ui = client.get("/ui/")
    assert ui.status_code == 200
    assert "EvalOps Review" in ui.text
    assert "bad-cases" in ui.text
