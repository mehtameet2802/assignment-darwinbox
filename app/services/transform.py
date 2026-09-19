from __future__ import annotations

import json

from app.database import db_session, utcnow
from app.schema import EMPLOYEE_TARGET_SCHEMA
from app.services.cleaning import clean_for_target_field
from app.services.date_escalations import list_date_escalations
from app.services.ingestion import IngestionError, get_migration
from app.services.mapping_store import list_mappings

TARGET_FIELDS = [field["name"] for field in EMPLOYEE_TARGET_SCHEMA["fields"]]


def _date_format_lookup(migration_id: int) -> dict[tuple[int, str], str]:
    payload = list_date_escalations(migration_id)
    lookup: dict[tuple[int, str], str] = {}
    for item in payload["escalations"]:
        if item["chosen_format"]:
            lookup[(item["source_file_id"], item["source_column"])] = item["chosen_format"]
    return lookup


def transform_migration(migration_id: int) -> dict:
    migration = get_migration(migration_id)
    mappings_payload = list_mappings(migration_id)
    if mappings_payload["blocking_review_count"] > 0:
        raise IngestionError("Resolve all mapping reviews before transforming.", 400)
    dates_payload = list_date_escalations(migration_id)
    if dates_payload["blocking_count"] > 0:
        raise IngestionError("Resolve all date-format escalations before transforming.", 400)

    active_mappings = [
        m for m in mappings_payload["mappings"] if not m["ignored"] and m["final_target"]
    ]
    date_formats = _date_format_lookup(migration_id)
    created = 0
    now = utcnow()

    with db_session() as connection:
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
            (m["source_file_id"], m["source_column"]): m["final_target"] for m in active_mappings
        }

        for row in rows:
            payload = json.loads(row["payload_json"])
            normalized = {field: None for field in TARGET_FIELDS}
            for source_column, raw_value in payload.items():
                target = mapping_index.get((row["source_file_id"], source_column))
                if not target:
                    continue
                date_format = date_formats.get((row["source_file_id"], source_column))
                cleaned = clean_for_target_field(target, raw_value, date_format=date_format)
                if cleaned.ok:
                    normalized[target] = cleaned.value
                else:
                    normalized[target] = None

            cursor = connection.execute(
                """
                INSERT INTO normalized_records (migration_id, employee_id, payload_json, status, created_at)
                VALUES (?, ?, ?, 'TRANSFORMED', ?)
                """,
                (
                    migration_id,
                    normalized.get("employee_id"),
                    json.dumps(normalized),
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
            "UPDATE migrations SET status = 'TRANSFORMED' WHERE id = ?",
            (migration_id,),
        )

    return {"migration_id": migration_id, "records_created": created}
