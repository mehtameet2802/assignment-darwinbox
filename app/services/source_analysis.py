from __future__ import annotations

import json

from app.database import db_session
from app.services.ingestion import IngestionError, get_migration
from app.services.mapping import deterministic_mapping
from app.services.type_inference import infer_column_type

DEFAULT_SAMPLE_LIMIT = 8


def collect_column_samples(migration_id: int, sample_limit: int = DEFAULT_SAMPLE_LIMIT) -> list[dict]:
    get_migration(migration_id)
    columns: list[dict] = []
    with db_session() as connection:
        files = connection.execute(
            """
            SELECT id, original_filename, columns_json, status
            FROM source_files
            WHERE migration_id = ? AND status = 'READY'
            ORDER BY id
            """,
            (migration_id,),
        ).fetchall()
        for source_file in files:
            column_names = json.loads(source_file["columns_json"])
            for column_name in column_names:
                rows = connection.execute(
                    """
                    SELECT payload_json
                    FROM source_rows
                    WHERE source_file_id = ?
                    ORDER BY source_row_number
                    LIMIT ?
                    """,
                    (source_file["id"], max(sample_limit * 3, 20)),
                ).fetchall()
                raw_values: list[str] = []
                for row in rows:
                    payload = json.loads(row["payload_json"])
                    raw_values.append(str(payload.get(column_name, "")))
                source_type, samples = infer_column_type(raw_values, max_samples=sample_limit)
                mapping = deterministic_mapping(column_name)
                columns.append(
                    {
                        "source_file": source_file["original_filename"],
                        "source_file_id": source_file["id"],
                        "source_column": column_name,
                        "sample_values": samples[:sample_limit],
                        "detected_source_type": source_type,
                        "proposed_target": mapping["target_field"] if mapping else None,
                        "mapping_method": mapping["method"] if mapping else None,
                        "confidence": mapping["confidence"] if mapping else None,
                        "reason": mapping["reason"] if mapping else None,
                        "alternatives": mapping["alternatives"] if mapping else [],
                    }
                )
    return columns


def analyze_migration(migration_id: int, sample_limit: int = DEFAULT_SAMPLE_LIMIT) -> dict:
    migration = get_migration(migration_id)
    if migration["file_count"] == 0:
        raise IngestionError("Upload at least one source file before running analysis.", 400)
    columns = collect_column_samples(migration_id, sample_limit=sample_limit)
    mapped = sum(1 for item in columns if item["proposed_target"])
    return {
        "migration_id": migration_id,
        "column_count": len(columns),
        "deterministic_mappings": mapped,
        "columns": columns,
    }
