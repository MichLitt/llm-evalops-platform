from __future__ import annotations


def test_token_protects_v1_but_not_health(client, monkeypatch):
    monkeypatch.setenv("EVALOPS_API_TOKEN", "test-token")
    assert client.get("/health").status_code == 200
    assert client.get("/v1/runs").status_code == 401
    assert client.get("/v1/runs", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get("/v1/runs", headers={"Authorization": "Bearer test-token"}).status_code == 200
