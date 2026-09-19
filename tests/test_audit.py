from __future__ import annotations

from pathlib import Path
import pytest

from app.database import init_db
from flask_app import create_app
from tests.test_push import _prepare_ready_records


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "migration.db"
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr("app.database.DATABASE_PATH", db_path)
    monkeypatch.setattr("app.services.ingestion.UPLOAD_DIR", upload_dir)
    init_db(db_path)
    return create_app().test_client()


def test_demo_path_writes_audit_entries(client) -> None:
    created = client.post("/api/migrations", json={"name": "Audit"})
    migration_id = created.get_json()["id"]
    client.post(f"/api/migrations/{migration_id}/demo-files")
    _prepare_ready_records(client, migration_id)
    client.post(f"/api/migrations/{migration_id}/validate")
    client.post(f"/api/migrations/{migration_id}/push")
    client.post(f"/api/migrations/{migration_id}/push/retry")

    log = client.get(f"/api/migrations/{migration_id}/audit-log").get_json()
    actions = {entry["action"] for entry in log["entries"]}
    assert "migration created" in actions
    assert "file uploaded" in actions
    assert "mapping generated" in actions
    assert "validation escalation created" in actions
    assert "push attempted" in actions
    assert "push failed" in actions
    assert "push succeeded" in actions
    assert "retry requested" in actions
