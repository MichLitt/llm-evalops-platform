from __future__ import annotations


def test_agent_contract_rejects_invalid_run_type(client):
    response = client.post(
        "/v1/ingest/agent/v1",
        json={"run_id": "bad-agent", "run_type": "batch"},
    )
    assert response.status_code == 422


def test_endpoint_rejects_mismatched_schema_version(client):
    response = client.post(
        "/v1/ingest/agent/v1",
        json={
            "run_id": "wrong-schema",
            "run_type": "eval",
            "schema_version": "rag/v1",
        },
    )
    assert response.status_code == 422


def test_rag_contract_rejects_non_numeric_metric(client):
    response = client.post(
        "/v1/ingest/rag/v1",
        json={"run_id": "bad-rag", "f1": "not-a-number"},
    )
    assert response.status_code == 422


def test_run_id_is_stripped_before_idempotency_check(client):
    payload = {"run_id": "  normalized-id  ", "dataset": "toy"}
    first = client.post("/v1/ingest/rag/v1", json=payload)
    second = client.post(
        "/v1/ingest/rag/v1",
        json={"run_id": "normalized-id", "dataset": "toy"},
    )

    assert first.status_code == 202
    assert first.json()["run_id"] == "normalized-id"
    assert second.status_code == 200
    assert second.json()["status"] == "duplicate"
