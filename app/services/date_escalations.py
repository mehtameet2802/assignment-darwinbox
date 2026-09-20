from __future__ import annotations

import json

from app.database import db_session, utcnow
from app.errors import AppError
from app.services.audit import AGENT, HUMAN, append_audit
from app.services.date_format_llm import suggest_date_format
from app.services.dates import FORMAT_DMY, FORMAT_MDY, analyze_date_column
from app.services.mapping_store import list_mappings_from_connection
from app.services.migrations import require_migration
from app.status import NEEDS_REVIEW, RESOLVED


def _row_to_escalation(row) -> dict:
    return {
        "id": row["id"],
        "migration_id": row["migration_id"],
        "source_file_id": row["source_file_id"],
        "source_file": row["source_file"],
        "source_column": row["source_column"],
        "issue_type": row["issue_type"],
        "status": row["status"],
        "chosen_format": row["chosen_format"],
        "sample_values": json.loads(row["sample_values_json"]),
        "review_reason": row["review_reason"],
        "suggested_format": row["suggested_format"] if "suggested_format" in row.keys() else None,
        "suggestion_confidence": row["suggestion_confidence"]
        if "suggestion_confidence" in row.keys()
        else None,
        "updated_at": row["updated_at"],
    }


def _collect_column_values(migration_id: int, source_file_id: int, source_column: str) -> list[str]:
    with db_session() as connection:
        rows = connection.execute(
            """
            SELECT payload_json
            FROM source_rows
            WHERE source_file_id = ?
            ORDER BY source_row_number
            """,
            (source_file_id,),
        ).fetchall()
    values: list[str] = []
    for row in rows:
        payload = json.loads(row["payload_json"])
        values.append(str(payload.get(source_column, "")))
    return values


def scan_date_columns(migration_id: int) -> dict:
    with db_session() as connection:
        require_migration(migration_id, connection)
        mappings = list_mappings_from_connection(connection, migration_id)["mappings"]
        date_mappings = [
            m
            for m in mappings
            if not m["ignored"] and m.get("final_target") == "joining_date"
        ]
        if not date_mappings:
            raise AppError("No mapped joining_date columns to analyze.", 400)

        now = utcnow()
        for mapping in date_mappings:
            values = _collect_column_values(
                migration_id,
                mapping["source_file_id"],
                mapping["source_column"],
            )
            analysis = analyze_date_column(values)
            status = NEEDS_REVIEW if analysis["ambiguous"] else RESOLVED
            chosen = analysis["chosen_format"]
            issue_type = analysis["issue_type"] or "AUTO_RESOLVED"
            suggested_format = None
            suggestion_confidence = None
            review_reason = analysis["review_reason"]

            if analysis["ambiguous"]:
                suggestion = suggest_date_format(
                    mapping["source_column"],
                    mapping["source_file"],
                    analysis["sample_values"],
                )
                suggested_format = suggestion.get("suggested_format")
                suggestion_confidence = suggestion.get("confidence")
                status = NEEDS_REVIEW
                chosen = None
                issue_type = analysis["issue_type"] or "DATE_FORMAT_AMBIGUITY"
                review_reason = (
                    analysis["review_reason"]
                    or "Date format is ambiguous; confirm DD/MM/YYYY or MM/DD/YYYY."
                )
                if suggestion.get("reason"):
                    review_reason = (
                        f"{review_reason} Model suggestion (not auto-applied): {suggestion['reason']}"
                    )

            connection.execute(
                """
                INSERT INTO date_column_escalations (
                    migration_id, source_file_id, source_file, source_column,
                    issue_type, status, chosen_format, sample_values_json,
                    review_reason, suggested_format, suggestion_confidence, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(migration_id, source_file_id, source_column)
                DO UPDATE SET
                    issue_type = excluded.issue_type,
                    status = excluded.status,
                    chosen_format = excluded.chosen_format,
                    sample_values_json = excluded.sample_values_json,
                    review_reason = excluded.review_reason,
                    suggested_format = excluded.suggested_format,
                    suggestion_confidence = excluded.suggestion_confidence,
                    updated_at = excluded.updated_at
                """,
                (
                    migration_id,
                    mapping["source_file_id"],
                    mapping["source_file"],
                    mapping["source_column"],
                    issue_type,
                    status,
                    chosen,
                    json.dumps(analysis["sample_values"]),
                    review_reason,
                    suggested_format,
                    suggestion_confidence,
                    now,
                ),
            )
            entity = f"{mapping['source_file']}:{mapping['source_column']}"
            if status == RESOLVED and chosen:
                action = (
                    "date format auto-resolved"
                    if issue_type in {"AUTO_RESOLVED", "OLLAMA_AUTO_RESOLVED"}
                    else "date format resolved"
                )
                append_audit(
                    connection,
                    migration_id,
                    AGENT,
                    action,
                    entity,
                    review_reason or f"Using {chosen} for column '{mapping['source_column']}'.",
                )
            elif status == NEEDS_REVIEW:
                append_audit(
                    connection,
                    migration_id,
                    AGENT,
                    "date format escalated",
                    entity,
                    review_reason or "Ambiguous date format requires human confirmation.",
                )
        return list_date_escalations_from_connection(connection, migration_id)


def list_date_escalations_from_connection(connection, migration_id: int) -> dict:
    rows = connection.execute(
        """
        SELECT * FROM date_column_escalations
        WHERE migration_id = ?
        ORDER BY source_file, source_column
        """,
        (migration_id,),
    ).fetchall()
    escalations = [_row_to_escalation(row) for row in rows]
    blocking = sum(1 for item in escalations if item["status"] == NEEDS_REVIEW)
    return {
        "migration_id": migration_id,
        "escalation_count": len(escalations),
        "blocking_count": blocking,
        "escalations": escalations,
    }


def list_date_escalations(migration_id: int) -> dict:
    with db_session() as connection:
        require_migration(migration_id, connection)
        return list_date_escalations_from_connection(connection, migration_id)


def resolve_date_escalation(migration_id: int, escalation_id: int, chosen_format: str) -> dict:
    if chosen_format not in {FORMAT_DMY, FORMAT_MDY}:
        raise AppError("chosen_format must be DD/MM/YYYY or MM/DD/YYYY.", 400)
    with db_session() as connection:
        row = connection.execute(
            """
            SELECT * FROM date_column_escalations
            WHERE id = ? AND migration_id = ?
            """,
            (escalation_id, migration_id),
        ).fetchone()
        if row is None:
            raise AppError("Date escalation not found.", 404)
        connection.execute(
            """
            UPDATE date_column_escalations
            SET status = ?, chosen_format = ?, review_reason = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                RESOLVED,
                chosen_format,
                f"Human selected {chosen_format} for this column.",
                utcnow(),
                escalation_id,
            ),
        )
        append_audit(
            connection,
            migration_id,
            HUMAN,
            "human correction",
            row["source_column"],
            f"Set {chosen_format} for {row['source_file']} column '{row['source_column']}'",
        )
        updated = connection.execute(
            "SELECT * FROM date_column_escalations WHERE id = ?",
            (escalation_id,),
        ).fetchone()
    return _row_to_escalation(updated)


def get_column_date_format(
    migration_id: int,
    source_file_id: int,
    source_column: str,
) -> str | None:
    with db_session() as connection:
        row = connection.execute(
            """
            SELECT chosen_format, status
            FROM date_column_escalations
            WHERE migration_id = ? AND source_file_id = ? AND source_column = ?
            """,
            (migration_id, source_file_id, source_column),
        ).fetchone()
    if row is None or row["status"] != RESOLVED:
        return None
    return row["chosen_format"]
