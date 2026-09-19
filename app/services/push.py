from __future__ import annotations

import json

from app.database import db_session, utcnow
from app.errors import AppError
from app.services.audit import HUMAN, SYSTEM, append_audit
from app.services.migrations import get_migration, require_migration
from app.services.mock_target import (
    delete_batch,
    list_target_records_for_migration,
    receive_employee_on_connection,
)
from app.status import PUSH_FAILED, PUSHED, READY_TO_PUSH, ROLLED_BACK

ENDPOINT = "/mock-target/employees"
METHOD = "POST"

OPERATION_PUSH = "push"
OPERATION_RETRY = "retry"
OPERATION_ROLLBACK = "rollback"


def _operation_label(operation: str | None) -> str:
    mapping = {
        OPERATION_PUSH: "Push",
        OPERATION_RETRY: "Retry",
        OPERATION_ROLLBACK: "Rollback",
    }
    return mapping.get(operation or OPERATION_PUSH, operation or "Push")


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
    normalized_record_id: int | None,
    employee_id: str,
    attempt_number: int,
    operation: str,
    http_status: int | None,
    result: str,
    error_message: str | None,
    response_body: dict | None = None,
) -> None:
    connection.execute(
        """
        INSERT INTO push_attempts (
            push_batch_id, migration_id, normalized_record_id, employee_id,
            attempt_number, endpoint, method, http_status, result, error_message,
            operation, response_json, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            push_batch_id,
            migration_id,
            normalized_record_id or 0,
            employee_id,
            attempt_number,
            ENDPOINT,
            METHOD,
            http_status,
            result,
            error_message,
            operation,
            json.dumps(response_body) if response_body else None,
            utcnow(),
        ),
    )


def _summarize_results(results: list[dict]) -> dict:
    successful = sum(1 for item in results if item.get("result") == "success")
    failed = sum(1 for item in results if item.get("result") == "failure")
    return {
        "total": len(results),
        "successful": successful,
        "failed": failed,
    }


def _result_row(
    *,
    normalized_record_id: int,
    employee_id: str,
    http_status: int | None,
    result_label: str,
    attempt_number: int,
    error_message: str | None,
    response_body: dict | None,
) -> dict:
    return {
        "normalized_record_id": normalized_record_id,
        "employee_id": employee_id,
        "http_status": http_status,
        "result": result_label,
        "attempt_number": attempt_number,
        "error_message": error_message,
        "response_body": response_body,
    }


def _push_records(
    migration_id: int,
    *,
    only_failed: bool,
) -> dict:
    now = utcnow()
    status_filter = PUSH_FAILED if only_failed else READY_TO_PUSH
    operation = OPERATION_RETRY if only_failed else OPERATION_PUSH

    with db_session() as connection:
        require_migration(migration_id, connection)
        cursor = connection.execute(
            """
            INSERT INTO push_batches (migration_id, status, operation, created_at)
            VALUES (?, 'ACTIVE', ?, ?)
            """,
            (migration_id, operation, now),
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
                operation=operation,
                http_status=http_status,
                result=result_label,
                error_message=error_message or (body.get("error") if body else None),
                response_body=body,
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
                _result_row(
                    normalized_record_id=row["id"],
                    employee_id=row["employee_id"] or payload.get("employee_id", ""),
                    http_status=http_status,
                    result_label=result_label,
                    attempt_number=attempt_number,
                    error_message=error_message or (body.get("error") if body else None),
                    response_body=body,
                )
            )

        connection.execute(
            "UPDATE push_batches SET status = 'COMPLETED' WHERE id = ?",
            (batch_id,),
        )
        connection.execute(
            "UPDATE migrations SET status = 'PUSHED' WHERE id = ?",
            (migration_id,),
        )

    summary = _summarize_results(results)
    return {
        "migration_id": migration_id,
        "push_batch_id": batch_id,
        "batch_key": batch_key,
        "operation": operation,
        "operation_label": _operation_label(operation) + " completed",
        "only_failed": only_failed,
        "records_attempted": len(results),
        "summary": summary,
        "results": results,
    }


def push_migration(migration_id: int) -> dict:
    return _push_records(migration_id, only_failed=False)


def retry_failed_push(migration_id: int) -> dict:
    return _push_records(migration_id, only_failed=True)


def rollback_latest_push(migration_id: int) -> dict:
    with db_session() as connection:
        require_migration(migration_id, connection)
        batch = connection.execute(
            """
            SELECT id, status FROM push_batches
            WHERE migration_id = ? AND status = 'COMPLETED' AND operation != ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (migration_id, OPERATION_ROLLBACK),
        ).fetchone()
        if batch is None:
            raise AppError("No completed push batch to rollback.", 404)

        batch_key = str(batch["id"])
        append_audit(connection, migration_id, HUMAN, "rollback requested", batch_key, "Rollback latest push batch")
        success_rows = connection.execute(
            """
            SELECT pa.employee_id, pa.normalized_record_id
            FROM push_attempts pa
            WHERE pa.push_batch_id = ? AND pa.result = 'success'
            """,
            (batch["id"],),
        ).fetchall()
        employee_ids = [row["employee_id"] for row in success_rows]

        rollback_cursor = connection.execute(
            """
            INSERT INTO push_batches (migration_id, status, operation, created_at)
            VALUES (?, 'ACTIVE', ?, ?)
            """,
            (migration_id, OPERATION_ROLLBACK, utcnow()),
        )
        rollback_batch_id = rollback_cursor.lastrowid

        deleted = delete_batch(batch_key, connection=connection)
        rollback_results: list[dict] = []
        for row in success_rows:
            rollback_results.append(
                {
                    "employee_id": row["employee_id"],
                    "result": "success",
                    "http_status": 200,
                    "error_message": None,
                    "response_body": {"batch_id": batch_key, "removed_from_target": True},
                }
            )
            _record_push_attempt(
                connection,
                push_batch_id=rollback_batch_id,
                migration_id=migration_id,
                normalized_record_id=row["normalized_record_id"],
                employee_id=row["employee_id"],
                attempt_number=0,
                operation=OPERATION_ROLLBACK,
                http_status=200,
                result="success",
                error_message=None,
                response_body={"batch_id": batch_key, "removed_from_target": True},
            )

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
        connection.execute(
            "UPDATE push_batches SET status = 'COMPLETED' WHERE id = ?",
            (rollback_batch_id,),
        )
        connection.execute(
            "UPDATE migrations SET completed_at = NULL WHERE id = ?",
            (migration_id,),
        )
        append_audit(
            connection,
            migration_id,
            SYSTEM,
            "rollback completed",
            batch_key,
            f"Removed {deleted['deleted_count']} target records",
        )

    summary = _summarize_results(rollback_results)
    return {
        "migration_id": migration_id,
        "push_batch_id": rollback_batch_id,
        "rolled_back_push_batch_id": batch["id"],
        "operation": OPERATION_ROLLBACK,
        "operation_label": "Rollback completed",
        "deleted_target_records": deleted["deleted_count"],
        "employee_ids_removed": sorted(set(employee_ids)),
        "records_returned_to_ready": len(employee_ids),
        "summary": summary,
        "results": rollback_results,
    }


def _record_status_counts(connection, migration_id: int) -> dict[str, int]:
    rows = connection.execute(
        """
        SELECT status, COUNT(*) AS count
        FROM normalized_records
        WHERE migration_id = ? AND status IN (?, ?, ?)
        GROUP BY status
        """,
        (migration_id, READY_TO_PUSH, PUSHED, PUSH_FAILED),
    ).fetchall()
    counts = {READY_TO_PUSH: 0, PUSHED: 0, PUSH_FAILED: 0}
    for row in rows:
        counts[row["status"]] = int(row["count"])
    return counts


def _latest_operation(connection, migration_id: int) -> dict | None:
    batch = connection.execute(
        """
        SELECT id, operation, status, created_at, rolled_back_at
        FROM push_batches
        WHERE migration_id = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (migration_id,),
    ).fetchone()
    if batch is None:
        return None

    attempts = connection.execute(
        """
        SELECT employee_id, attempt_number, operation, http_status, result,
               error_message, response_json
        FROM push_attempts
        WHERE push_batch_id = ?
        ORDER BY id
        """,
        (batch["id"],),
    ).fetchall()
    results = []
    for row in attempts:
        response_body = json.loads(row["response_json"]) if row["response_json"] else None
        results.append(
            {
                "employee_id": row["employee_id"],
                "attempt_number": row["attempt_number"],
                "operation": row["operation"] or batch["operation"],
                "operation_label": _operation_label(row["operation"] or batch["operation"]),
                "http_status": row["http_status"],
                "result": row["result"],
                "error_message": row["error_message"],
                "response_body": response_body,
            }
        )
    summary = _summarize_results(results)
    op = batch["operation"] or OPERATION_PUSH
    return {
        "push_batch_id": batch["id"],
        "operation": op,
        "operation_label": _operation_label(op) + " completed",
        "batch_status": batch["status"],
        "created_at": batch["created_at"],
        "rolled_back_at": batch["rolled_back_at"],
        "summary": summary,
        "results": results,
    }


def _workflow_state(
    *,
    counts: dict[str, int],
    target_count: int,
    completed_at: str | None,
    has_push_activity: bool,
) -> dict:
    ready = counts[READY_TO_PUSH]
    pushed = counts[PUSHED]
    failed = counts[PUSH_FAILED]

    if completed_at:
        return {
            "phase": "completed",
            "title": "Migration finished",
            "summary": (
                "You clicked **Complete migration**. This migration no longer appears on the Push page."
            ),
            "next_step": "Use **Audit log** anytime to review the full timeline (all migrations are listed there).",
            "can_complete": False,
        }

    if not has_push_activity and ready > 0:
        return {
            "phase": "awaiting_first_push",
            "title": "Ready for first push",
            "summary": (
                f"**{ready}** employee record(s) passed analysis and are waiting to be sent to the mock target."
            ),
            "next_step": "Click **Push to target** to submit them in one batch.",
            "can_complete": False,
        }

    if failed > 0:
        if pushed == 0 and target_count == 0:
            return {
                "phase": "all_failed",
                "title": "Every record failed — nothing in the target",
                "summary": (
                    f"All **{failed}** record(s) failed the mock API on push. "
                    "The target has **0** employees from this migration."
                ),
                "next_step": (
                    "Click **Retry failed records** to try again (demo: E009 succeeds on the 2nd attempt). "
                    "If you are done retrying, use **Complete migration** to close the push workflow anyway."
                ),
                "can_complete": True,
                "complete_mode": "unresolved",
            }
        return {
            "phase": "needs_retry",
            "title": "Push incomplete — failures need retry",
            "summary": (
                f"**{failed}** record(s) failed the target API. "
                f"**{pushed}** succeeded and are in the target ({target_count} stored there)."
            ),
            "next_step": (
                "Use **Retry failed records** until failures are cleared. "
                "**Complete migration** is only available when nothing is failed."
            ),
            "can_complete": False,
        }

    if ready > 0:
        return {
            "phase": "needs_push_after_rollback",
            "title": "Records ready again after rollback",
            "summary": (
                f"**{ready}** record(s) are back to READY_TO_PUSH (usually after **Roll back latest batch**). "
                f"The target currently holds **{target_count}** record(s) from other batches."
            ),
            "next_step": "Click **Push to target** when you want to send the ready rows again.",
            "can_complete": False,
        }

    if pushed > 0 and failed == 0 and ready == 0:
        return {
            "phase": "ready_to_finish",
            "title": "All employees reached the target",
            "summary": (
                f"**{pushed}** record(s) are PUSHED in this migration and **{target_count}** row(s) exist in the mock target. "
                "No failures and nothing left to push."
            ),
            "next_step": (
                "Click **Complete migration** when you are done (including any retries). "
                "The migration will leave Push and appear only under **Audit log**."
            ),
            "can_complete": True,
            "complete_mode": "success",
        }

    return {
        "phase": "idle",
        "title": "Nothing to push right now",
        "summary": "There are no READY_TO_PUSH or PUSH_FAILED records for this migration.",
        "next_step": "Return to **Analysis & review** if records are missing, or check **Audit log**.",
        "can_complete": False,
    }


def complete_push_workflow(migration_id: int) -> dict:
    overview = get_push_overview(migration_id)
    workflow = overview.get("workflow") or {}
    if not workflow.get("can_complete"):
        raise AppError(
            "Migration can only be completed when all records are pushed with no failures, "
            "or when every push attempt failed and nothing is waiting to push.",
            400,
        )
    mode = workflow.get("complete_mode") or "success"
    counts = overview.get("record_counts") or {}
    if counts.get("ready_to_push", 0) > 0:
        raise AppError("Cannot complete while records are still READY_TO_PUSH.", 400)

    now = utcnow()
    if mode == "unresolved":
        audit_reason = (
            f"Push workflow closed with {counts.get('push_failed', 0)} PUSH_FAILED record(s); "
            "no records in mock target"
        )
    else:
        audit_reason = "Push workflow finished successfully; migration left Push page"

    with db_session() as connection:
        require_migration(migration_id, connection)
        connection.execute(
            "UPDATE migrations SET completed_at = ? WHERE id = ?",
            (now, migration_id),
        )
        append_audit(
            connection,
            migration_id,
            HUMAN,
            "migration completed",
            "push",
            audit_reason,
        )
    return get_migration(migration_id)


def get_push_overview(migration_id: int) -> dict:
    with db_session() as connection:
        require_migration(migration_id, connection)
        migration_row = connection.execute(
            "SELECT completed_at FROM migrations WHERE id = ?",
            (migration_id,),
        ).fetchone()
        completed_at = migration_row["completed_at"] if migration_row else None
        batch_count = connection.execute(
            "SELECT COUNT(*) AS n FROM push_batches WHERE migration_id = ?",
            (migration_id,),
        ).fetchone()["n"]
        counts = _record_status_counts(connection, migration_id)
        latest = _latest_operation(connection, migration_id)
        failed_rows = connection.execute(
            """
            SELECT employee_id
            FROM normalized_records
            WHERE migration_id = ? AND status = ?
            ORDER BY employee_id
            """,
            (migration_id, PUSH_FAILED),
        ).fetchall()

        failed_records = []
        for row in failed_rows:
            last_error = connection.execute(
                """
                SELECT error_message, http_status
                FROM push_attempts
                WHERE migration_id = ? AND employee_id = ? AND result = 'failure'
                ORDER BY id DESC
                LIMIT 1
                """,
                (migration_id, row["employee_id"]),
            ).fetchone()
            failed_records.append(
                {
                    "employee_id": row["employee_id"],
                    "reason": last_error["error_message"] if last_error else "Push failed",
                    "http_status": last_error["http_status"] if last_error else None,
                }
            )

    target_records = list_target_records_for_migration(migration_id)
    history = list_push_attempts(migration_id)
    record_counts = {
        "ready_to_push": counts[READY_TO_PUSH],
        "pushed": counts[PUSHED],
        "push_failed": counts[PUSH_FAILED],
    }
    workflow = _workflow_state(
        counts=counts,
        target_count=len(target_records),
        completed_at=completed_at,
        has_push_activity=int(batch_count) > 0,
    )

    return {
        "migration_id": migration_id,
        "completed_at": completed_at,
        "record_counts": record_counts,
        "workflow": workflow,
        "latest_operation": latest,
        "failed_records": failed_records,
        "target_record_count": len(target_records),
        "target_records": target_records,
        "attempt_history": history["attempts"],
    }


def list_push_attempts(migration_id: int) -> dict:
    with db_session() as connection:
        require_migration(migration_id, connection)
        rows = connection.execute(
            """
            SELECT pa.*, pb.operation AS batch_operation
            FROM push_attempts pa
            JOIN push_batches pb ON pb.id = pa.push_batch_id
            WHERE pa.migration_id = ?
            ORDER BY pa.id
            """,
            (migration_id,),
        ).fetchall()

    attempts = []
    for row in rows:
        operation = row["operation"] or row["batch_operation"] or OPERATION_PUSH
        response_body = json.loads(row["response_json"]) if row["response_json"] else None
        attempts.append(
            {
                "id": row["id"],
                "employee_id": row["employee_id"],
                "operation": operation,
                "operation_label": _operation_label(operation),
                "attempt_number": row["attempt_number"] if row["attempt_number"] else None,
                "result": row["result"],
                "http_status": row["http_status"],
                "error_message": row["error_message"],
                "response_body": response_body,
                "created_at": row["created_at"],
                "push_batch_id": row["push_batch_id"],
            }
        )
    return {
        "migration_id": migration_id,
        "attempts": attempts,
    }
