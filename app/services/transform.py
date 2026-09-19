from __future__ import annotations

import json

from app.database import db_session, utcnow
from app.errors import AppError
from app.schema import EMPLOYEE_TARGET_SCHEMA
from app.services.cleaning import (
    clean_for_target_field,
    clean_string,
    is_null_sentinel,
    target_field_type,
)
from app.services.date_escalations import list_date_escalations
from app.services.mapping import is_full_name_source_column, split_full_name
from app.services.mapping_store import list_mappings, refresh_target_field_collisions
from app.services.migrations import require_migration
from app.status import TRANSFORMED

TARGET_FIELDS = [field["name"] for field in EMPLOYEE_TARGET_SCHEMA["fields"]]


def _date_format_lookup(migration_id: int) -> dict[tuple[int, str], str]:
    payload = list_date_escalations(migration_id)
    lookup: dict[tuple[int, str], str] = {}
    for item in payload["escalations"]:
        if item["chosen_format"]:
            lookup[(item["source_file_id"], item["source_column"])] = item["chosen_format"]
    return lookup


def transform_migration(migration_id: int) -> dict:
    mappings_payload = list_mappings(migration_id)
    if mappings_payload["blocking_review_count"] > 0:
        raise AppError("Resolve all mapping reviews before transforming.", 400)
    dates_payload = list_date_escalations(migration_id)
    if dates_payload["blocking_count"] > 0:
        raise AppError("Resolve all date-format escalations before transforming.", 400)

    active_mappings = [
        m for m in mappings_payload["mappings"] if not m["ignored"] and m["final_target"]
    ]
    date_formats = _date_format_lookup(migration_id)
    created = 0
    now = utcnow()

    with db_session() as connection:
        require_migration(migration_id, connection)
        if refresh_target_field_collisions(connection, migration_id):
            raise AppError(
                "Resolve TARGET_FIELD_COLLISION mapping reviews before transforming.",
                400,
            )
        connection.execute(
            """
            DELETE FROM record_lineage
            WHERE normalized_record_id IN (
                SELECT id FROM normalized_records WHERE migration_id = ?
            )
            """,
            (migration_id,),
        )
        connection.execute("DELETE FROM normalized_records WHERE migration_id = ?", (migration_id,))
        connection.execute("DELETE FROM duplicate_conflicts WHERE migration_id = ?", (migration_id,))

        rows = connection.execute(
            """
            SELECT sr.id AS source_row_id, sr.source_file, sr.source_row_number,
                   sr.source_file_id, sr.payload_json
            FROM source_rows sr
            JOIN source_files sf ON sf.id = sr.source_file_id
            WHERE sf.migration_id = ? AND sf.status = 'READY'
            ORDER BY sr.id
            """,
            (migration_id,),
        ).fetchall()

        mapping_index = {
            (m["source_file_id"], m["source_column"]): m for m in active_mappings
        }

        for row in rows:
            payload = json.loads(row["payload_json"])
            normalized = {field: None for field in TARGET_FIELDS}
            for source_column, raw_value in payload.items():
                mapping = mapping_index.get((row["source_file_id"], source_column))
                if not mapping:
                    continue
                target = mapping["final_target"]
                date_format = date_formats.get((row["source_file_id"], source_column))

                if target == "first_name" and is_full_name_source_column(source_column):
                    first_raw, last_raw = split_full_name(raw_value)
                    first_clean = clean_string(first_raw) if first_raw is not None else clean_string(None)
                    if first_clean.ok:
                        normalized["first_name"] = first_clean.value
                    if last_raw is not None:
                        last_clean = clean_string(last_raw)
                        if last_clean.ok and normalized.get("last_name") is None:
                            normalized["last_name"] = last_clean.value
                    continue

                cleaned = clean_for_target_field(target, raw_value, date_format=date_format)
                if cleaned.ok:
                    normalized[target] = cleaned.value
                elif target_field_type(target) == "email" and cleaned.value is not None:
                    # Keep malformed emails for Phase 9 validation (E010).
                    normalized[target] = cleaned.value
                elif is_null_sentinel(raw_value):
                    normalized[target] = None
                else:
                    # Preserve supplied value for cleaning-failure escalation (do not silently drop).
                    text = str(raw_value).strip()
                    normalized[target] = text if text else None

            cursor = connection.execute(
                """
                INSERT INTO normalized_records (migration_id, employee_id, payload_json, status, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    migration_id,
                    normalized.get("employee_id"),
                    json.dumps(normalized),
                    TRANSFORMED,
                    now,
                ),
            )
            record_id = cursor.lastrowid
            connection.execute(
                """
                INSERT INTO record_lineage (
                    normalized_record_id, source_row_id, source_file, source_row_number
                )
                VALUES (?, ?, ?, ?)
                """,
                (record_id, row["source_row_id"], row["source_file"], row["source_row_number"]),
            )
            created += 1

        connection.execute(
            "UPDATE migrations SET status = ? WHERE id = ?",
            (TRANSFORMED, migration_id),
        )

    return {"migration_id": migration_id, "records_created": created}
