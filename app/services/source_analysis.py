from __future__ import annotations

import json

from app.database import db_session
from app.errors import AppError
from app.services.llm_client import LLMClient
from app.services.mapping import deterministic_mapping
from app.services.migrations import get_migration, require_migration
from app.services.type_inference import infer_column_type

DEFAULT_SAMPLE_LIMIT = 8


def _apply_column_mapping(
    column_name: str,
    source_type: str,
    samples: list[str],
    include_semantic: bool,
    llm_client: LLMClient | None,
) -> dict:
    mapping = deterministic_mapping(column_name)
    if mapping:
        return {
            "proposed_target": mapping["target_field"],
            "mapping_method": mapping["method"],
            "confidence": mapping["confidence"],
            "reason": mapping["reason"],
            "alternatives": mapping["alternatives"],
            "ollama_success": None,
        }
    if not include_semantic:
        return {
            "proposed_target": None,
            "mapping_method": None,
            "confidence": None,
            "reason": None,
            "alternatives": [],
            "ollama_success": None,
        }
    client = llm_client or LLMClient()
    semantic = client.infer_mapping(column_name, source_type, samples)
    return {
        "proposed_target": semantic.get("target_field"),
        "mapping_method": semantic.get("method"),
        "confidence": semantic.get("confidence"),
        "reason": semantic.get("reason"),
        "alternatives": semantic.get("alternatives") or [],
        "ollama_success": semantic.get("success"),
    }


def collect_column_samples(
    migration_id: int,
    sample_limit: int = DEFAULT_SAMPLE_LIMIT,
    include_semantic: bool = False,
    llm_client: LLMClient | None = None,
) -> list[dict]:
    require_migration(migration_id)
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
                proposal = _apply_column_mapping(
                    column_name,
                    source_type,
                    samples[:sample_limit],
                    include_semantic,
                    llm_client,
                )
                columns.append(
                    {
                        "source_file": source_file["original_filename"],
                        "source_file_id": source_file["id"],
                        "source_column": column_name,
                        "sample_values": samples[:sample_limit],
                        "detected_source_type": source_type,
                        **proposal,
                    }
                )
    return columns


def analyze_migration(
    migration_id: int,
    sample_limit: int = DEFAULT_SAMPLE_LIMIT,
    include_semantic: bool = False,
    llm_client: LLMClient | None = None,
) -> dict:
    migration = get_migration(migration_id)
    if migration["file_count"] == 0:
        raise AppError("Upload at least one source file before running analysis.", 400)
    columns = collect_column_samples(
        migration_id,
        sample_limit=sample_limit,
        include_semantic=include_semantic,
        llm_client=llm_client,
    )
    deterministic = sum(1 for item in columns if item["mapping_method"] == "deterministic_alias")
    semantic = sum(1 for item in columns if item["mapping_method"] == "ollama" and item["proposed_target"])
    mapped = sum(1 for item in columns if item["proposed_target"])
    return {
        "migration_id": migration_id,
        "column_count": len(columns),
        "deterministic_mappings": deterministic,
        "semantic_mappings": semantic,
        "mapped_columns": mapped,
        "include_semantic": include_semantic,
        "columns": columns,
    }
