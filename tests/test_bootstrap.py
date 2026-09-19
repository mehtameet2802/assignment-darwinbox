from __future__ import annotations

from pathlib import Path

from flask_app import create_app

from app.database import init_db, ping_db
from app.schema import EMPLOYEE_TARGET_SCHEMA, target_schema_summary


def test_sqlite_connection_works(tmp_path: Path) -> None:
    db_path = tmp_path / "migration.db"
    init_db(db_path)
    result = ping_db(db_path)
    assert result["initialized"] == "true"
    assert result["sqlite_version"]


def test_target_schema_has_required_employee_fields() -> None:
    names = {field["name"] for field in EMPLOYEE_TARGET_SCHEMA["fields"]}
    assert names == {
        "employee_id",
        "first_name",
        "last_name",
        "email",
        "joining_date",
        "department",
        "city",
    }
    summary = target_schema_summary()
    assert summary["required_count"] == 3
    assert summary["optional_count"] == 4


def test_flask_health_endpoint(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "migration.db"
    monkeypatch.setattr("app.database.DATABASE_PATH", db_path)
    client = create_app().test_client()
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "ok"
    assert payload["sqlite"]["initialized"] == "true"
