from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from flask_app import create_app

from app.database import init_db
from app.services.mock_target import list_batch_records
from app.services.push import READY_TO_PUSH
from tests.test_duplicates import _ollama_side_effect


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "migration.db"
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr("app.database.DATABASE_PATH", db_path)
    monkeypatch.setattr("app.services.ingestion.UPLOAD_DIR", upload_dir)
    init_db(db_path)
    return create_app().test_client()


def _prepare_ready_records(client, migration_id: int) -> None:
    with patch("app.services.llm_client.LLMClient.infer_mapping", side_effect=_ollama_side_effect):
        client.post(f"/api/migrations/{migration_id}/mappings/generate?include_semantic=true")
    client.post(f"/api/migrations/{migration_id}/date-columns/scan")
    client.post(f"/api/migrations/{migration_id}/transform")
    client.post(f"/api/migrations/{migration_id}/duplicates/analyze")
    client.post(f"/api/migrations/{migration_id}/validate")


def test_e009_push_then_retry(client) -> None:
    created = client.post("/api/migrations", json={"name": "Push"})
    migration_id = created.get_json()["id"]
    client.post(f"/api/migrations/{migration_id}/demo-files")
    _prepare_ready_records(client, migration_id)

    first = client.post(f"/api/migrations/{migration_id}/push")
    assert first.status_code == 201
    first_payload = first.get_json()
    e009_first = next(r for r in first_payload["results"] if r["employee_id"] == "E009")
    assert e009_first["http_status"] == 500
    assert e009_first["result"] == "failure"

    succeeded = [r for r in first_payload["results"] if r["result"] == "success"]
    assert succeeded
    batch_key = first_payload["batch_key"]
    assert list_batch_records(batch_key)

    retry = client.post(f"/api/migrations/{migration_id}/push/retry")
    assert retry.status_code == 201
    retry_payload = retry.get_json()
    assert retry_payload["records_attempted"] == 1
    e009_retry = retry_payload["results"][0]
    assert e009_retry["employee_id"] == "E009"
    assert e009_retry["http_status"] == 201
    assert e009_retry["attempt_number"] == 2

    attempts = client.get(f"/api/migrations/{migration_id}/push/attempts").get_json()["attempts"]
    e009_attempts = [a for a in attempts if a["employee_id"] == "E009"]
    assert len(e009_attempts) == 2
    assert e009_attempts[0]["http_status"] == 500
    assert e009_attempts[1]["http_status"] == 201

    e007_attempts = [a for a in attempts if a["employee_id"] == "E007"]
    assert len(e007_attempts) == 1


def test_rollback_removes_target_batch_records(client) -> None:
    created = client.post("/api/migrations", json={"name": "Rollback"})
    migration_id = created.get_json()["id"]
    client.post(f"/api/migrations/{migration_id}/demo-files")
    _prepare_ready_records(client, migration_id)

    push = client.post(f"/api/migrations/{migration_id}/push").get_json()
    batch_key = push["batch_key"]
    before = list_batch_records(batch_key)

    rollback = client.post(f"/api/migrations/{migration_id}/push/rollback")
    assert rollback.status_code == 200
    assert list_batch_records(batch_key) == []

    from app.database import db_session

    with db_session() as connection:
        row = connection.execute(
            "SELECT status FROM normalized_records WHERE migration_id = ? AND employee_id = ?",
            (migration_id, before[0]["employee_id"]),
        ).fetchone()
    assert row["status"] == READY_TO_PUSH
