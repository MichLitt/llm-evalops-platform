"""Shared pytest fixtures.

test_client  — FastAPI TestClient backed by an in-memory SQLite DB.
run_worker   — Synchronously drains all pending ingested_reports records.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from llm_evalops_platform.app import create_app
from llm_evalops_platform.storage import db as db_module
from llm_evalops_platform.storage.db import Database
from llm_evalops_platform.worker.normalizer import process_one


@pytest.fixture()
def test_db(tmp_path, monkeypatch):
    """Isolated per-test SQLite database."""
    db_path = str(tmp_path / "test_evalops.db")
    test_database = Database(db_path)
    test_database.init_db()
    monkeypatch.setattr(db_module, "db", test_database)
    # Also patch db references in storage and worker modules
    import llm_evalops_platform.storage.db as storage_db
    import llm_evalops_platform.worker.normalizer as worker_mod
    import llm_evalops_platform.services.compare as compare_mod
    import llm_evalops_platform.services.gate as gate_mod
    import llm_evalops_platform.api.ingest as ingest_mod
    import llm_evalops_platform.api.runs as runs_mod
    import llm_evalops_platform.api.compare as api_compare_mod
    import llm_evalops_platform.api.review as review_mod
    monkeypatch.setattr(storage_db, "db", test_database)
    monkeypatch.setattr(worker_mod, "db", test_database)
    monkeypatch.setattr(compare_mod, "db", test_database)
    monkeypatch.setattr(gate_mod, "db", test_database)
    monkeypatch.setattr(ingest_mod, "db", test_database)
    monkeypatch.setattr(runs_mod, "db", test_database)
    monkeypatch.setattr(api_compare_mod, "db", test_database)
    monkeypatch.setattr(review_mod, "db", test_database)
    return test_database


@pytest.fixture()
def client(test_db):
    app = create_app()
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def run_worker(test_db):
    """Drain all pending records synchronously."""
    def _drain():
        while process_one():
            pass
    return _drain
