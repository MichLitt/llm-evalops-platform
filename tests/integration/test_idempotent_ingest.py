"""Integration test: idempotent ingest — same run_id submitted multiple times."""

from __future__ import annotations

PAYLOAD = {
    "run_id": "idempotent-test-001",
    "schema_version": "rag/v1",
    "dataset": "squad",
    "retriever_mode": "bm25",
    "generator_model": "claude-haiku",
    "em": 0.70,
    "f1": 0.75,
}


def test_duplicate_returns_200(client):
    r1 = client.post("/v1/ingest/rag/v1", json=PAYLOAD)
    assert r1.status_code == 202
    assert r1.json()["status"] == "accepted"

    r2 = client.post("/v1/ingest/rag/v1", json=PAYLOAD)
    assert r2.status_code == 200
    assert r2.json()["status"] == "duplicate"
    assert r2.json()["ingest_id"] == r1.json()["ingest_id"]


def test_no_duplicate_run_after_worker(client, run_worker):
    client.post("/v1/ingest/rag/v1", json=PAYLOAD)
    client.post("/v1/ingest/rag/v1", json=PAYLOAD)
    run_worker()

    r = client.get("/v1/runs", params={"app_type": "rag"})
    runs = [run for run in r.json()["runs"] if run["run_id"] == PAYLOAD["run_id"]]
    assert len(runs) == 1
