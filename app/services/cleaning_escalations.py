from __future__ import annotations

import json
import sqlite3
from typing import Any

from app.services.cleaning import (
    clean_for_target_field,
    clean_string,
    is_null_sentinel,
    target_field_type,
)
from app.services.mapping import is_full_name_source_column, split_full_name

CLEANING_FAILURE = "CLEANING_FAILURE"


def _append_failure(
    failures: list[dict[str, Any]],
    *,
    field_name: str,
    review_reason: str,
    source_file: str,
    source_column: str,
) -> None:
    if any(item["field_name"] == field_name for item in failures):
        return
    failures.append(
        {
            "field_name": field_name,
            "issue_type": CLEANING_FAILURE,
            "rule_fired": CLEANING_FAILURE,
            "review_reason": review_reason,
            "source_file": source_file,
            "source_column": source_column,
        }
    )


def collect_record_cleaning_failures(
    connection: sqlite3.Connection,
    migration_id: int,
    normalized_record_id: int,
    date_formats: dict[tuple[int, str], str],
    active_mappings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Detect source values that were supplied but could not be cleaned to the target field."""
    mapping_index = {
        (m["source_file_id"], m["source_column"]): m
        for m in active_mappings
        if not m["ignored"] and m["final_target"]
    }
    lineage_rows = connection.execute(
        """
        SELECT sr.source_file_id, sr.source_file, sr.payload_json
        FROM record_lineage rl
        JOIN source_rows sr ON sr.id = rl.source_row_id
        WHERE rl.normalized_record_id = ?
        """,
        (normalized_record_id,),
    ).fetchall()

    failures: list[dict[str, Any]] = []
    for line in lineage_rows:
        payload = json.loads(line["payload_json"] or "{}")
        source_file_id = line["source_file_id"]
        source_file = line["source_file"]
        for source_column, raw_value in payload.items():
            mapping = mapping_index.get((source_file_id, source_column))
            if not mapping:
                continue
            target = mapping["final_target"]
            date_format = date_formats.get((source_file_id, source_column))

            if target == "first_name" and is_full_name_source_column(source_column):
                first_raw, last_raw = split_full_name(raw_value)
                if first_raw is not None and not is_null_sentinel(first_raw):
                    first_clean = clean_string(first_raw)
                    if not first_clean.ok:
                        _append_failure(
                            failures,
                            field_name="first_name",
                            review_reason=(
                                f"Supplied name in '{source_column}' could not be cleaned for first_name: "
                                f"{first_clean.error or 'invalid value'}"
                            ),
                            source_file=source_file,
                            source_column=source_column,
                        )
                if last_raw is not None and not is_null_sentinel(last_raw):
                    last_clean = clean_string(last_raw)
                    if not last_clean.ok:
                        _append_failure(
                            failures,
                            field_name="last_name",
                            review_reason=(
                                f"Supplied name in '{source_column}' could not be cleaned for last_name: "
                                f"{last_clean.error or 'invalid value'}"
                            ),
                            source_file=source_file,
                            source_column=source_column,
                        )
                continue

            cleaned = clean_for_target_field(target, raw_value, date_format=date_format)
            if cleaned.ok:
                continue
            if target_field_type(target) == "email" and cleaned.value is not None:
                continue
            if is_null_sentinel(raw_value):
                continue
            _append_failure(
                failures,
                field_name=target,
                review_reason=(
                    f"Supplied value for '{target}' from column '{source_column}' could not be cleaned: "
                    f"{cleaned.error or 'invalid value'}"
                ),
                source_file=source_file,
                source_column=source_column,
            )
    return failures
