from __future__ import annotations

import json

from app.database import db_session, utcnow
from app.services.dates import DATE_FORMAT_AMBIGUITY, FORMAT_DMY, FORMAT_MDY, analyze_date_column
from app.services.ingestion import IngestionError, get_migration
from app.services.mapping_store import list_mappings


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
    get_migration(migration_id)
    mappings = list_mappings(migration_id)["mappings"]
    date_mappings = [
        m
        for m in mappings
        if not m["ignored"] and m.get("final_target") == "joining_date"
    ]
    if not date_mappings:
        raise IngestionError("No mapped joining_date columns to analyze.", 400)

    now = utcnow()
    escalations: list[dict] = []
    with db_session() as connection:
        for mapping in date_mappings:
            values = _collect_column_values(
                migration_id,
                mapping["source_file_id"],
                mapping["source_column"],
            )
            analysis = analyze_date_column(values)
            status = "NEEDS_REVIEW" if analysis["ambiguous"] else "RESOLVED"
            chosen = analysis["chosen_format"]
            issue_type = analysis["issue_type"] or "AUTO_RESOLVED"
            connection.execute(
                """
                INSERT INTO date_column_escalations (
                    migration_id, source_file_id, source_file, source_column,
                    issue_type, status, chosen_format, sample_values_json,
                    review_reason, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(migration_id, source_file_id, source_column)
                DO UPDATE SET
                    issue_type = excluded.issue_type,
                    status = excluded.status,
                    chosen_format = excluded.chosen_format,
                    sample_values_json = excluded.sample_values_json,
                    review_reason = excluded.review_reason,
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
                    analysis["review_reason"],
                    now,
                ),
            )
        rows = connection.execute(
            """
            SELECT * FROM date_column_escalations
            WHERE migration_id = ?
            ORDER BY source_file, source_column
            """,
            (migration_id,),
        ).fetchall()
    escalations = [_row_to_escalation(row) for row in rows]
    blocking = sum(1 for item in escalations if item["status"] == "NEEDS_REVIEW")
    return {
        "migration_id": migration_id,
        "escalation_count": len(escalations),
        "blocking_count": blocking,
        "escalations": escalations,
    }


def list_date_escalations(migration_id: int) -> dict:
    get_migration(migration_id)
    with db_session() as connection:
        rows = connection.execute(
            """
            SELECT * FROM date_column_escalations
            WHERE migration_id = ?
            ORDER BY source_file, source_column
            """,
            (migration_id,),
        ).fetchall()
    escalations = [_row_to_escalation(row) for row in rows]
    blocking = sum(1 for item in escalations if item["status"] == "NEEDS_REVIEW")
    return {
        "migration_id": migration_id,
        "escalation_count": len(escalations),
        "blocking_count": blocking,
        "escalations": escalations,
    }


def resolve_date_escalation(migration_id: int, escalation_id: int, chosen_format: str) -> dict:
    if chosen_format not in {FORMAT_DMY, FORMAT_MDY}:
        raise IngestionError("chosen_format must be DD/MM/YYYY or MM/DD/YYYY.", 400)
    with db_session() as connection:
        row = connection.execute(
            """
            SELECT * FROM date_column_escalations
            WHERE id = ? AND migration_id = ?
            """,
            (escalation_id, migration_id),
        ).fetchone()
        if row is None:
            raise IngestionError("Date escalation not found.", 404)
        connection.execute(
            """
            UPDATE date_column_escalations
            SET status = 'RESOLVED', chosen_format = ?, review_reason = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                chosen_format,
                f"Human selected {chosen_format} for this column.",
                utcnow(),
                escalation_id,
            ),
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
    if row is None or row["status"] != "RESOLVED":
        return None
    return row["chosen_format"]
