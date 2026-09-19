from __future__ import annotations

import json
import sqlite3
from typing import Any

from pydantic import ValidationError

from app.database import db_session, utcnow
from app.models.employee import EmployeeRecord

E009_EMPLOYEE_ID = "E009"


def _validate_payload(payload: dict[str, Any]) -> EmployeeRecord:
    return EmployeeRecord.model_validate(payload)


def receive_employee_on_connection(
    connection: sqlite3.Connection,
    payload: dict[str, Any],
    batch_id: str,
) -> tuple[int, dict[str, Any], str | None]:
    """Mock Darwinbox target ingest using an existing DB connection."""
    try:
        record = _validate_payload(payload)
    except ValidationError as exc:
        first = exc.errors()[0]
        return 400, {"error": first.get("msg", "Invalid payload")}, str(first.get("msg"))

    employee_id = record.employee_id
    now = utcnow()

    if employee_id == E009_EMPLOYEE_ID:
        row = connection.execute(
            "SELECT push_count FROM mock_target_e009_state WHERE employee_id = ?",
            (E009_EMPLOYEE_ID,),
        ).fetchone()
        if row is None:
            connection.execute(
                "INSERT INTO mock_target_e009_state (employee_id, push_count) VALUES (?, 1)",
                (E009_EMPLOYEE_ID,),
            )
            return 500, {"error": "Simulated target failure for E009."}, "Simulated target failure"

    existing = connection.execute(
        "SELECT id FROM mock_target_records WHERE employee_id = ?",
        (employee_id,),
    ).fetchone()
    if existing:
        return 409, {"error": f"Duplicate employee_id '{employee_id}'."}, "Duplicate employee_id"

    cursor = connection.execute(
        """
        INSERT INTO mock_target_records (batch_id, employee_id, payload_json, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (batch_id, employee_id, json.dumps(record.model_dump(mode="json")), now),
    )
    target_id = cursor.lastrowid
    return 201, {"id": target_id, "batch_id": batch_id, "employee_id": employee_id}, None


def receive_employee(payload: dict[str, Any], batch_id: str) -> tuple[int, dict[str, Any], str | None]:
    with db_session() as connection:
        return receive_employee_on_connection(connection, payload, batch_id)


def delete_batch(batch_id: str, connection: sqlite3.Connection | None = None) -> dict[str, Any]:
    if connection is not None:
        cursor = connection.execute(
            "DELETE FROM mock_target_records WHERE batch_id = ?",
            (batch_id,),
        )
        return {"batch_id": batch_id, "deleted_count": cursor.rowcount}

    with db_session() as conn:
        return delete_batch(batch_id, connection=conn)


def list_batch_records(batch_id: str) -> list[dict[str, Any]]:
    with db_session() as connection:
        rows = connection.execute(
            "SELECT employee_id FROM mock_target_records WHERE batch_id = ? ORDER BY id",
            (batch_id,),
        ).fetchall()
    return [{"employee_id": row["employee_id"]} for row in rows]
