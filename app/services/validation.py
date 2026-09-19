from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from app.database import db_session, utcnow
from app.errors import AppError
from app.models.employee import EmployeeRecord
from app.schema import EMPLOYEE_TARGET_SCHEMA
from app.services.audit import AGENT, HUMAN, SYSTEM, append_audit
from app.services.cleaning_escalations import collect_record_cleaning_failures
from app.services.date_escalations import list_date_escalations
from app.services.duplicates import open_duplicate_conflict_record_ids
from app.services.mapping_store import list_mappings_from_connection
from app.services.migrations import require_migration
from app.status import EXCLUDED, NEEDS_REVIEW, READY_TO_PUSH, RESOLVED, TRANSFORMED

REQUIRED_VALUE_MISSING = "REQUIRED_VALUE_MISSING"
VALIDATION_FAILURE = "VALIDATION_FAILURE"

REQUIRED_FIELDS = [f["name"] for f in EMPLOYEE_TARGET_SCHEMA["fields"] if f["required"]]


def _date_format_lookup_from_payload(dates_payload: dict) -> dict[tuple[int, str], str]:
    lookup: dict[tuple[int, str], str] = {}
    for item in dates_payload["escalations"]:
        if item["chosen_format"]:
            lookup[(item["source_file_id"], item["source_column"])] = item["chosen_format"]
    return lookup


def _is_missing(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def assess_record(payload: dict) -> dict:
    for field in REQUIRED_FIELDS:
        if _is_missing(payload.get(field)):
            return {
                "status": NEEDS_REVIEW,
                "issue_type": REQUIRED_VALUE_MISSING,
                "field_name": field,
                "rule_fired": REQUIRED_VALUE_MISSING,
                "review_reason": f"Required target field '{field}' has no usable value.",
            }
    try:
        EmployeeRecord.model_validate(payload)
    except ValidationError as exc:
        first = exc.errors()[0]
        loc = ".".join(str(part) for part in first.get("loc", ()))
        field_name = loc or "unknown"
        return {
            "status": NEEDS_REVIEW,
            "issue_type": VALIDATION_FAILURE,
            "field_name": field_name,
            "rule_fired": VALIDATION_FAILURE,
            "review_reason": f"Validation failure on '{field_name}': {first.get('msg', 'invalid value')}",
        }
    return {"status": READY_TO_PUSH, "issue_type": None, "field_name": None, "rule_fired": None, "review_reason": None}


def validate_migration(migration_id: int) -> dict:
    validated = 0
    escalated = 0
    ready = 0
    now = utcnow()

    with db_session() as connection:
        require_migration(migration_id, connection)
        connection.execute(
            "DELETE FROM validation_escalations WHERE migration_id = ?",
            (migration_id,),
        )
        skip_record_ids = open_duplicate_conflict_record_ids(connection, migration_id)
        mappings_payload = list_mappings_from_connection(connection, migration_id)
        active_mappings = mappings_payload["mappings"]
        date_formats = _date_format_lookup_from_payload(list_date_escalations(migration_id))
        rows = connection.execute(
            """
            SELECT id, employee_id, payload_json, status
            FROM normalized_records
            WHERE migration_id = ? AND status IN (?, ?)
            ORDER BY id
            """,
            (migration_id, TRANSFORMED, NEEDS_REVIEW),
        ).fetchall()

        for row in rows:
            if row["id"] in skip_record_ids:
                continue
            payload = json.loads(row["payload_json"] or "{}")
            cleaning_failures = collect_record_cleaning_failures(
                connection,
                migration_id,
                row["id"],
                date_formats,
                active_mappings,
            )
            validated += 1
            if cleaning_failures:
                for failure in cleaning_failures:
                    escalated += 1
                    connection.execute(
                        "UPDATE normalized_records SET status = ? WHERE id = ?",
                        (NEEDS_REVIEW, row["id"]),
                    )
                    append_audit(
                        connection,
                        migration_id,
                        AGENT,
                        "cleaning escalation created",
                        row["employee_id"],
                        failure["review_reason"],
                    )
                    connection.execute(
                        """
                        INSERT INTO validation_escalations (
                            migration_id, normalized_record_id, employee_id,
                            issue_type, field_name, rule_fired, review_reason,
                            current_payload_json, status, updated_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            migration_id,
                            row["id"],
                            row["employee_id"],
                            failure["issue_type"],
                            failure["field_name"],
                            failure["rule_fired"],
                            failure["review_reason"],
                            json.dumps(payload),
                            NEEDS_REVIEW,
                            now,
                        ),
                    )
                continue

            result = assess_record(payload)
            if result["status"] == READY_TO_PUSH:
                connection.execute(
                    "UPDATE normalized_records SET status = ? WHERE id = ?",
                    (READY_TO_PUSH, row["id"]),
                )
                ready += 1
                continue

            escalated += 1
            connection.execute(
                "UPDATE normalized_records SET status = ? WHERE id = ?",
                (NEEDS_REVIEW, row["id"]),
            )
            append_audit(
                connection,
                migration_id,
                SYSTEM,
                "validation escalation created",
                row["employee_id"],
                result["review_reason"],
            )
            connection.execute(
                """
                INSERT INTO validation_escalations (
                    migration_id, normalized_record_id, employee_id,
                    issue_type, field_name, rule_fired, review_reason,
                    current_payload_json, status, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    migration_id,
                    row["id"],
                    row["employee_id"],
                    result["issue_type"],
                    result["field_name"],
                    result["rule_fired"],
                    result["review_reason"],
                    json.dumps(payload),
                    NEEDS_REVIEW,
                    now,
                ),
            )

        connection.execute(
            "UPDATE migrations SET status = 'VALIDATED' WHERE id = ?",
            (migration_id,),
        )

    return {
        "migration_id": migration_id,
        "records_validated": validated,
        "ready_to_push": ready,
        "validation_escalations": escalated,
    }


def list_validation_escalations_from_connection(connection, migration_id: int) -> dict:
    rows = connection.execute(
        """
        SELECT ve.*, rl.source_file, rl.source_row_number
        FROM validation_escalations ve
        LEFT JOIN record_lineage rl ON rl.normalized_record_id = ve.normalized_record_id
        WHERE ve.migration_id = ?
        ORDER BY ve.employee_id, ve.id
        """,
        (migration_id,),
    ).fetchall()

    grouped: dict[int, dict] = {}
    for row in rows:
        item = grouped.get(row["id"])
        if item is None:
            item = {
                "id": row["id"],
                "normalized_record_id": row["normalized_record_id"],
                "employee_id": row["employee_id"],
                "issue_type": row["issue_type"],
                "field_name": row["field_name"],
                "rule_fired": row["rule_fired"],
                "review_reason": row["review_reason"],
                "current_payload": json.loads(row["current_payload_json"]),
                "status": row["status"],
                "sources": [],
            }
            grouped[row["id"]] = item
        if row["source_file"]:
            item["sources"].append(
                {"source_file": row["source_file"], "source_row_number": row["source_row_number"]}
            )

    escalations = list(grouped.values())
    blocking = sum(1 for e in escalations if e["status"] == NEEDS_REVIEW)
    return {
        "migration_id": migration_id,
        "escalation_count": len(escalations),
        "blocking_count": blocking,
        "escalations": escalations,
    }


def list_validation_escalations(migration_id: int) -> dict:
    with db_session() as connection:
        require_migration(migration_id, connection)
        return list_validation_escalations_from_connection(connection, migration_id)


def resolve_validation_escalation(
    migration_id: int,
    escalation_id: int,
    *,
    action: str,
    field_name: str | None = None,
    value: str | None = None,
) -> dict:
    if action not in {"enter_value", "exclude"}:
        raise AppError("action must be 'enter_value' or 'exclude'.", 400)

    with db_session() as connection:
        row = connection.execute(
            """
            SELECT * FROM validation_escalations
            WHERE id = ? AND migration_id = ?
            """,
            (escalation_id, migration_id),
        ).fetchone()
        if row is None:
            raise AppError("Validation escalation not found.", 404)

        record_id = row["normalized_record_id"]
        if action == "exclude":
            append_audit(
                connection,
                migration_id,
                HUMAN,
                "record excluded",
                row["employee_id"],
                "Validation escalation excluded",
            )
            connection.execute(
                "UPDATE normalized_records SET status = ? WHERE id = ?",
                (EXCLUDED, record_id),
            )
            connection.execute(
                "UPDATE validation_escalations SET status = ?, updated_at = ? WHERE id = ?",
                (EXCLUDED, utcnow(), escalation_id),
            )
            return list_validation_escalations(migration_id)

        if not field_name:
            field_name = row["field_name"]
        payload = json.loads(row["current_payload_json"])
        if value is None:
            raise AppError("value is required for enter_value.", 400)
        payload[field_name] = value
        result = assess_record(payload)
        if result["status"] != READY_TO_PUSH:
            connection.execute(
                """
                UPDATE validation_escalations
                SET current_payload_json = ?, review_reason = ?, rule_fired = ?,
                    issue_type = ?, field_name = ?, status = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    json.dumps(payload),
                    result["review_reason"],
                    result["rule_fired"],
                    result["issue_type"],
                    result["field_name"],
                    NEEDS_REVIEW,
                    utcnow(),
                    escalation_id,
                ),
            )
            connection.execute(
                "UPDATE normalized_records SET payload_json = ?, status = ? WHERE id = ?",
                (json.dumps(payload), NEEDS_REVIEW, record_id),
            )
            return list_validation_escalations(migration_id)

        connection.execute(
            "UPDATE normalized_records SET payload_json = ?, status = ? WHERE id = ?",
            (json.dumps(payload), READY_TO_PUSH, record_id),
        )
        connection.execute(
            "UPDATE validation_escalations SET status = ?, current_payload_json = ?, updated_at = ? WHERE id = ?",
            (RESOLVED, json.dumps(payload), utcnow(), escalation_id),
        )
        append_audit(
            connection,
            migration_id,
            HUMAN,
            "human correction",
            row["employee_id"],
            f"Set {field_name} during validation review",
        )

    return list_validation_escalations(migration_id)
