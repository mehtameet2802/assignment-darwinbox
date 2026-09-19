from __future__ import annotations

from pathlib import Path

import pytest
from flask_app import create_app

from app.database import init_db

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


def test_batch_delete_removes_records(client) -> None:
    payload = {**E009_PAYLOAD, "employee_id": "E008"}
    client.post("/mock-target/employees", json=payload, headers={"X-Batch-Id": "rollback-batch"})
    deleted = client.delete("/mock-target/batches/rollback-batch")
    assert deleted.status_code == 200
    assert deleted.get_json()["deleted_count"] == 1
