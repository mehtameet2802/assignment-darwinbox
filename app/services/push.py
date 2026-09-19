from __future__ import annotations

import json

from app.database import db_session, utcnow
from app.services.ingestion import IngestionError, get_migration
from app.services.audit import HUMAN, SYSTEM, append_audit
from app.services.mock_target import delete_batch, receive_employee_on_connection

PUSHED = "PUSHED"
PUSH_FAILED = "PUSH_FAILED"
READY_TO_PUSH = "READY_TO_PUSH"
ROLLED_BACK = "ROLLED_BACK"
ENDPOINT = "/mock-target/employees"
METHOD = "POST"


def _next_attempt_number(connection, normalized_record_id: int) -> int:
    row = connection.execute(
        """
        SELECT COALESCE(MAX(attempt_number), 0) AS max_attempt
        FROM push_attempts
        WHERE normalized_record_id = ?
        """,
        (normalized_record_id,),
    ).fetchone()
    return int(row["max_attempt"]) + 1


def _record_push_attempt(
    connection,
    *,
    push_batch_id: int,
    migration_id: int,
    normalized_record_id: int,
    employee_id: str,
    attempt_number: int,
    http_status: int | None,
    result: str,
    error_message: str | None,
) -> None:
    connection.execute(
        """
        INSERT INTO push_attempts (
            push_batch_id, migration_id, normalized_record_id, employee_id,
            attempt_number, endpoint, method, http_status, result, error_message, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            push_batch_id,
            migration_id,
            normalized_record_id,
            employee_id,
            attempt_number,
            ENDPOINT,
            METHOD,
            http_status,
            result,
            error_message,
            utcnow(),
        ),
    )


def _push_records(
    migration_id: int,
    *,
    only_failed: bool,
) -> dict:
    get_migration(migration_id)
    now = utcnow()
    status_filter = PUSH_FAILED if only_failed else READY_TO_PUSH

    with db_session() as connection:
        cursor = connection.execute(
            """
            INSERT INTO push_batches (migration_id, status, created_at)
            VALUES (?, 'ACTIVE', ?)
            """,
            (migration_id, now),
        )
        batch_id = cursor.lastrowid
        batch_key = str(batch_id)
        if only_failed:
            append_audit(connection, migration_id, HUMAN, "retry requested", "push", "Retry failed records")
        else:
            append_audit(connection, migration_id, SYSTEM, "push attempted", "batch", batch_key)

        rows = connection.execute(
            """
            SELECT id, employee_id, payload_json, status
            FROM normalized_records
            WHERE migration_id = ? AND status = ?
            ORDER BY id
            """,
            (migration_id, status_filter),
        ).fetchall()

        results = []
        for row in rows:
            payload = json.loads(row["payload_json"] or "{}")
            attempt_number = _next_attempt_number(connection, row["id"])
            http_status, body, error_message = receive_employee_on_connection(
                connection, payload, batch_id=batch_key
            )
            success = http_status == 201
            result_label = "success" if success else "failure"
            _record_push_attempt(
                connection,
                push_batch_id=batch_id,
                migration_id=migration_id,
                normalized_record_id=row["id"],
                employee_id=row["employee_id"] or payload.get("employee_id", ""),
                attempt_number=attempt_number,
                http_status=http_status,
                result=result_label,
                error_message=error_message or body.get("error"),
            )
            if success:
                connection.execute(
                    "UPDATE normalized_records SET status = ? WHERE id = ?",
                    (PUSHED, row["id"]),
                )
                append_audit(
                    connection,
                    migration_id,
                    SYSTEM,
                    "push succeeded",
                    row["employee_id"],
                    f"HTTP {http_status}",
                )
            else:
                connection.execute(
                    "UPDATE normalized_records SET status = ? WHERE id = ?",
                    (PUSH_FAILED, row["id"]),
                )
                append_audit(
                    connection,
                    migration_id,
                    SYSTEM,
                    "push failed",
                    row["employee_id"],
                    error_message or body.get("error") or f"HTTP {http_status}",
                )
            results.append(
                {
                    "normalized_record_id": row["id"],
                    "employee_id": row["employee_id"],
                    "http_status": http_status,
                    "result": result_label,
                    "attempt_number": attempt_number,
                }
            )

        connection.execute(
            "UPDATE push_batches SET status = 'COMPLETED' WHERE id = ?",
            (batch_id,),
        )
        connection.execute(
            "UPDATE migrations SET status = 'PUSHED' WHERE id = ?",
            (migration_id,),
        )

    return {
        "migration_id": migration_id,
        "push_batch_id": batch_id,
        "batch_key": batch_key,
        "only_failed": only_failed,
        "records_attempted": len(results),
        "results": results,
    }


def push_migration(migration_id: int) -> dict:
    return _push_records(migration_id, only_failed=False)


def retry_failed_push(migration_id: int) -> dict:
    return _push_records(migration_id, only_failed=True)


def rollback_latest_push(migration_id: int) -> dict:
    get_migration(migration_id)
    with db_session() as connection:
        batch = connection.execute(
            """
            SELECT id, status FROM push_batches
            WHERE migration_id = ? AND status = 'COMPLETED'
            ORDER BY id DESC
            LIMIT 1
            """,
            (migration_id,),
        ).fetchone()
        if batch is None:
            raise IngestionError("No completed push batch to rollback.", 404)

        batch_key = str(batch["id"])
        append_audit(connection, migration_id, HUMAN, "rollback requested", batch_key, "Rollback latest push batch")
        success_rows = connection.execute(
            """
            SELECT employee_id FROM push_attempts
            WHERE push_batch_id = ? AND result = 'success'
            """,
            (batch["id"],),
        ).fetchall()
        employee_ids = {row["employee_id"] for row in success_rows}
        deleted = delete_batch(batch_key, connection=connection)

        connection.execute(
            """
            UPDATE normalized_records
            SET status = ?
            WHERE migration_id = ? AND status = ? AND employee_id IN (
                SELECT employee_id FROM push_attempts
                WHERE push_batch_id = ? AND result = 'success'
            )
            """,
            (READY_TO_PUSH, migration_id, PUSHED, batch["id"]),
        )
        connection.execute(
            "UPDATE push_batches SET status = ?, rolled_back_at = ? WHERE id = ?",
            (ROLLED_BACK, utcnow(), batch["id"]),
        )
        append_audit(
            connection,
            migration_id,
            SYSTEM,
            "rollback completed",
            batch_key,
            f"Removed {deleted['deleted_count']} target records",
        )

    return {
        "migration_id": migration_id,
        "push_batch_id": batch["id"],
        "deleted_target_records": deleted["deleted_count"],
        "employee_ids_removed": sorted(employee_ids),
    }


def list_push_attempts(migration_id: int) -> dict:
    get_migration(migration_id)
    with db_session() as connection:
        rows = connection.execute(
            """
            SELECT pa.*, pb.status AS batch_status
            FROM push_attempts pa
            JOIN push_batches pb ON pb.id = pa.push_batch_id
            WHERE pa.migration_id = ?
            ORDER BY pa.id
            """,
            (migration_id,),
        ).fetchall()
    return {
        "migration_id": migration_id,
        "attempts": [dict(row) for row in rows],
    }
