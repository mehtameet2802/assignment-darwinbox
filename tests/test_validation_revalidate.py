from __future__ import annotations

from pathlib import Path

import pytest
from flask_app import create_app

from app.database import init_db
from app.services.analysis_pipeline import (
    continue_after_duplicate_resolution,
    continue_after_validation_resolution,
)
from app.services.validation import list_validation_escalations
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


def test_continue_after_one_validation_fix_keeps_other_escalations(client) -> None:
    created = client.post("/api/migrations", json={"name": "Revalidate"})
    migration_id = created.get_json()["id"]
    client.post(f"/api/migrations/{migration_id}/demo-files")
    _run_demo_pipeline(client, migration_id)
    client.post(f"/api/migrations/{migration_id}/validate")

    before = list_validation_escalations(migration_id)
    e011 = next(e for e in before["escalations"] if e["employee_id"] == "E011")
    e010 = next(e for e in before["escalations"] if e["employee_id"] == "E010")
    assert e011["status"] == "NEEDS_REVIEW"
    assert e010["status"] == "NEEDS_REVIEW"

    client.patch(
        f"/api/migrations/{migration_id}/validation-escalations/{e011['id']}",
        json={"action": "enter_value", "field_name": "email", "value": "anjali@example.com"},
    )

    snapshot = continue_after_validation_resolution(migration_id)
    after = list_validation_escalations(migration_id)
    e010_after = next((e for e in after["escalations"] if e["employee_id"] == "E010"), None)
    assert e010_after is not None
    assert e010_after["status"] == "NEEDS_REVIEW"
    assert snapshot["validation_blocking"] >= 1
    assert snapshot["issues_requiring_review"] >= 1


def test_continue_after_duplicate_resolution_keeps_validation_escalations(client) -> None:
    created = client.post("/api/migrations", json={"name": "Dup then val"})
    migration_id = created.get_json()["id"]
    client.post(f"/api/migrations/{migration_id}/demo-files")
    _run_demo_pipeline(client, migration_id)
    client.post(f"/api/migrations/{migration_id}/validate")

    dup = client.get(f"/api/migrations/{migration_id}/duplicate-conflicts").get_json()
    e002 = next(c for c in dup["conflicts"] if c["employee_id"] == "E002")
    base = e002["members"][0]["payload"]
    client.patch(
        f"/api/migrations/{migration_id}/duplicate-conflicts/{e002['id']}",
        json={"action": "save", "final_payload": {**base, "email": "ravi@example.com"}},
    )

    snapshot = continue_after_duplicate_resolution(migration_id)
    after = list_validation_escalations(migration_id)
    open_issues = [e for e in after["escalations"] if e["status"] == "NEEDS_REVIEW"]
    assert len(open_issues) >= 2
    assert snapshot["validation_blocking"] >= 2
