from __future__ import annotations

from pathlib import Path

import pytest

from app.database import init_db
from app.services.validation import REQUIRED_VALUE_MISSING, VALIDATION_FAILURE, list_validation_escalations
from flask_app import create_app
from tests.test_duplicates import _run_demo_pipeline


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "migration.db"
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr("app.database.DATABASE_PATH", db_path)
    monkeypatch.setattr("app.services.ingestion.UPLOAD_DIR", upload_dir)
    init_db(db_path)
    return create_app().test_client()


def test_e010_and_e011_validation_escalations(client) -> None:
    created = client.post("/api/migrations", json={"name": "Validation"})
    migration_id = created.get_json()["id"]
    client.post(f"/api/migrations/{migration_id}/demo-files")
    _run_demo_pipeline(client, migration_id)

    response = client.post(f"/api/migrations/{migration_id}/validate")
    assert response.status_code == 201
    payload = list_validation_escalations(migration_id)
    e010 = next((e for e in payload["escalations"] if e["employee_id"] == "E010"), None)
    e011 = next((e for e in payload["escalations"] if e["employee_id"] == "E011"), None)
    assert e010 is not None
    assert e010["issue_type"] == VALIDATION_FAILURE
    assert e010["field_name"] == "email"
    assert e011 is not None
    assert e011["issue_type"] == REQUIRED_VALUE_MISSING
    assert e011["field_name"] == "email"


def test_resolve_e011_email_makes_ready(client) -> None:
    created = client.post("/api/migrations", json={"name": "Validation"})
    migration_id = created.get_json()["id"]
    client.post(f"/api/migrations/{migration_id}/demo-files")
    _run_demo_pipeline(client, migration_id)
    client.post(f"/api/migrations/{migration_id}/validate")
    e011 = next(
        e for e in list_validation_escalations(migration_id)["escalations"] if e["employee_id"] == "E011"
    )
    resolved = client.patch(
        f"/api/migrations/{migration_id}/validation-escalations/{e011['id']}",
        json={"action": "enter_value", "field_name": "email", "value": "anjali@example.com"},
    )
    assert resolved.status_code == 200
    updated = next(e for e in resolved.get_json()["escalations"] if e["employee_id"] == "E011")
    assert updated["status"] == "RESOLVED"


def test_unified_review_queue_lists_validation_items(client) -> None:
    created = client.post("/api/migrations", json={"name": "Validation"})
    migration_id = created.get_json()["id"]
    client.post(f"/api/migrations/{migration_id}/demo-files")
    _run_demo_pipeline(client, migration_id)
    client.post(f"/api/migrations/{migration_id}/validate")
    queue = client.get(f"/api/migrations/{migration_id}/review-queue").get_json()
    types = {item["issue_type"] for item in queue["items"]}
    assert VALIDATION_FAILURE in types
    assert REQUIRED_VALUE_MISSING in types
