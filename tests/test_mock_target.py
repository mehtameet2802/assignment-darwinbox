from __future__ import annotations

import json
from pathlib import Path

import pytest
from flask_app import create_app

from app.database import db_session, init_db, utcnow
from app.services.mock_target import list_target_records_for_migration

E009_PAYLOAD = {
    "employee_id": "E009",
    "first_name": "Demo",
    "last_name": "Fail",
    "email": "demo.fail@example.com",
    "joining_date": "2024-08-07",
    "department": "Product",
    "city": "Mumbai",
}


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "migration.db"
    monkeypatch.setattr("app.database.DATABASE_PATH", db_path)
    init_db(db_path)
    return create_app().test_client()


def test_e009_first_post_returns_500(client) -> None:
    first = client.post("/mock-target/employees", json=E009_PAYLOAD, headers={"X-Batch-Id": "batch-1"})
    assert first.status_code == 500
    second = client.post("/mock-target/employees", json=E009_PAYLOAD, headers={"X-Batch-Id": "batch-1"})
    assert second.status_code == 201


def test_duplicate_returns_409(client) -> None:
    payload = {**E009_PAYLOAD, "employee_id": "E007"}
    first = client.post("/mock-target/employees", json=payload, headers={"X-Batch-Id": "b1"})
    assert first.status_code == 201
    second = client.post("/mock-target/employees", json=payload, headers={"X-Batch-Id": "b2"})
    assert second.status_code == 409


def test_list_target_records_one_per_employee_and_name_from_first_last(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "migration.db"
    monkeypatch.setattr("app.database.DATABASE_PATH", db_path)
    init_db(db_path)
    now = utcnow()
    payload = {
        "employee_id": "E001",
        "first_name": "Jane",
        "last_name": "Doe",
        "email": "jane@example.com",
        "department": "Engineering",
    }
    with db_session() as connection:
        connection.execute(
            """
            INSERT INTO migrations (name, entity, status, auto_remove_exact_duplicates, created_at)
            VALUES ('Test', 'employees', 'PUSHED', 1, ?)
            """,
            (now,),
        )
        migration_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
        connection.execute(
            """
            INSERT INTO push_batches (migration_id, status, operation, created_at)
            VALUES (?, 'COMPLETED', 'push', ?)
            """,
            (migration_id, now),
        )
        batch_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
        connection.execute(
            """
            INSERT INTO mock_target_records (batch_id, employee_id, payload_json, created_at)
            VALUES (?, 'E001', ?, ?)
            """,
            (str(batch_id), json.dumps(payload), now),
        )
        for status in ("EXACT_DEDUPED", "PUSHED"):
            connection.execute(
                """
                INSERT INTO normalized_records (migration_id, employee_id, payload_json, status, created_at)
                VALUES (?, 'E001', ?, ?, ?)
                """,
                (migration_id, json.dumps(payload), status, now),
            )

    records = list_target_records_for_migration(migration_id)
    assert len(records) == 1
    assert records[0]["employee_id"] == "E001"
    assert records[0]["name"] == "Jane Doe"
    assert records[0]["migration_record_status"] == "PUSHED"


def test_batch_delete_removes_records(client) -> None:
    payload = {**E009_PAYLOAD, "employee_id": "E008"}
    client.post("/mock-target/employees", json=payload, headers={"X-Batch-Id": "rollback-batch"})
    deleted = client.delete("/mock-target/batches/rollback-batch")
    assert deleted.status_code == 200
    assert deleted.get_json()["deleted_count"] == 1
