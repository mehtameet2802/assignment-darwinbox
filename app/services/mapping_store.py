from __future__ import annotations

import json

from app.database import db_session, utcnow
from app.services.ingestion import IngestionError, get_migration
from app.services.mapping_policy import (
    AUTO_APPROVED,
    IGNORED,
    MANUALLY_APPROVED,
    NEEDS_REVIEW,
    evaluate_mapping_policy,
)
from app.services.source_analysis import analyze_migration
from app.schema import EMPLOYEE_TARGET_SCHEMA

TARGET_FIELD_NAMES = [field["name"] for field in EMPLOYEE_TARGET_SCHEMA["fields"]]


def _row_to_mapping(row) -> dict:
    return {
        "id": row["id"],
        "migration_id": row["migration_id"],
        "source_file_id": row["source_file_id"],
        "source_file": row["source_file"],
        "source_column": row["source_column"],
        "detected_source_type": row["detected_source_type"],
        "sample_values": json.loads(row["sample_values_json"]),
        "proposed_target": row["proposed_target"],
        "final_target": row["final_target"],
        "mapping_method": row["mapping_method"],
        "confidence": row["confidence"],
        "ai_reason": row["ai_reason"],
        "alternatives": json.loads(row["alternatives_json"] or "[]"),
        "status": row["status"],
        "review_required": bool(row["review_required"]),
        "review_rule_fired": row["review_rule_fired"],
        "review_reason": row["review_reason"],
        "ignored": bool(row["ignored"]),
        "updated_at": row["updated_at"],
    }


def generate_mappings(migration_id: int, include_semantic: bool = True) -> dict:
    analysis = analyze_migration(migration_id, include_semantic=include_semantic)
    now = utcnow()
    with db_session() as connection:
        connection.execute("DELETE FROM column_mappings WHERE migration_id = ?", (migration_id,))
        for column in analysis["columns"]:
            policy = evaluate_mapping_policy(
                source_type=column["detected_source_type"],
                proposed_target=column.get("proposed_target"),
                confidence=column.get("confidence"),
            )
            connection.execute(
                """
                INSERT INTO column_mappings (
                    migration_id, source_file_id, source_file, source_column,
                    detected_source_type, sample_values_json, proposed_target, final_target,
                    mapping_method, confidence, ai_reason, alternatives_json,
                    status, review_required, review_rule_fired, review_reason, ignored, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
                """,
                (
                    migration_id,
                    column["source_file_id"],
                    column["source_file"],
                    column["source_column"],
                    column["detected_source_type"],
                    json.dumps(column["sample_values"]),
                    column.get("proposed_target"),
                    policy["final_target"],
                    column.get("mapping_method"),
                    column.get("confidence"),
                    column.get("reason"),
                    json.dumps(column.get("alternatives") or []),
                    policy["status"],
                    1 if policy["review_required"] else 0,
                    policy["review_rule_fired"],
                    policy["review_reason"],
                    now,
                ),
            )
        connection.execute(
            "UPDATE migrations SET status = 'MAPPINGS_GENERATED' WHERE id = ?",
            (migration_id,),
        )
        from app.services.audit import AGENT, append_audit

        append_audit(
            connection,
            migration_id,
            AGENT,
            "mapping generated",
            "employees",
            f"{len(analysis['columns'])} source columns analyzed",
        )
    return list_mappings(migration_id)


def list_mappings(migration_id: int) -> dict:
    get_migration(migration_id)
    with db_session() as connection:
        rows = connection.execute(
            """
            SELECT * FROM column_mappings
            WHERE migration_id = ?
            ORDER BY source_file, source_column
            """,
            (migration_id,),
        ).fetchall()
    mappings = [_row_to_mapping(row) for row in rows]
    blocking = sum(1 for item in mappings if item["review_required"])
    return {
        "migration_id": migration_id,
        "mapping_count": len(mappings),
        "blocking_review_count": blocking,
        "ready_for_transform": blocking == 0 and len(mappings) > 0,
        "mappings": mappings,
    }


def update_mapping(migration_id: int, mapping_id: int, action: str, target_field: str | None = None) -> dict:
    """Update mapping within a single session (fix closure bug)."""
    if action not in {"map", "ignore"}:
        raise IngestionError("Invalid mapping action. Use 'map' or 'ignore'.", 400)

    with db_session() as connection:
        row = connection.execute(
            "SELECT * FROM column_mappings WHERE id = ? AND migration_id = ?",
            (mapping_id, migration_id),
        ).fetchone()
        if row is None:
            raise IngestionError("Mapping not found for this migration.", 404)

        if action == "ignore":
            policy = evaluate_mapping_policy(
                source_type=row["detected_source_type"],
                proposed_target=row["proposed_target"],
                confidence=row["confidence"],
                ignored=True,
            )
            ignored_flag = 1
        else:
            if not target_field or target_field not in TARGET_FIELD_NAMES:
                raise IngestionError(
                    f"target_field must be one of: {', '.join(TARGET_FIELD_NAMES)}",
                    400,
                )
            policy = evaluate_mapping_policy(
                source_type=row["detected_source_type"],
                proposed_target=row["proposed_target"],
                confidence=row["confidence"],
                manual_target=target_field,
            )
            ignored_flag = 0

        connection.execute(
            """
            UPDATE column_mappings
            SET final_target = ?, status = ?, review_required = ?,
                review_rule_fired = ?, review_reason = ?, ignored = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                policy["final_target"],
                policy["status"],
                1 if policy["review_required"] else 0,
                policy["review_rule_fired"],
                policy["review_reason"],
                ignored_flag,
                utcnow(),
                mapping_id,
            ),
        )
        updated = connection.execute(
            "SELECT * FROM column_mappings WHERE id = ?",
            (mapping_id,),
        ).fetchone()
    return _row_to_mapping(updated)
