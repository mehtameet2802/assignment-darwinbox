from __future__ import annotations

import json
from pathlib import Path

import pytest
from flask_app import create_app

from app.database import db_session, init_db, utcnow
from app.services.cleaning_escalations import CLEANING_FAILURE
from app.services.validation import list_validation_escalations, validate_migration


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "migration.db"
    monkeypatch.setattr("app.database.DATABASE_PATH", db_path)
    init_db(db_path)
    return create_app().test_client()


def test_supplied_uncleanable_joining_date_escalates(client) -> None:
    created = client.post("/api/migrations", json={"name": "Cleaning"})
    migration_id = created.get_json()["id"]
    now = utcnow()

    with db_session() as connection:
        connection.execute(
            """
            INSERT INTO source_files (
                migration_id, original_filename, stored_path, format,
                row_count, column_count, columns_json, status, created_at
            )
            VALUES (?, 'bad_date.csv', '/tmp/bad_date.csv', 'csv', 1, 2, '[]', 'READY', ?)
            """,
            (migration_id, now),
        )
        file_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
        connection.execute(
            """
            INSERT INTO source_rows (source_file_id, source_file, source_row_number, payload_json)
            VALUES (?, 'bad_date.csv', 2, ?)
            """,
            (
                file_id,
                json.dumps(
                    {
                        "employee_id": "E099",
                        "first_name": "Test",
                        "email": "test@example.com",
                        "joining_date": "not-a-valid-date",
                    }
                ),
            ),
        )
        source_row_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
        connection.execute(
            """
            INSERT INTO column_mappings (
                migration_id, source_file_id, source_file, source_column,
                detected_source_type, sample_values_json, proposed_target, final_target,
                mapping_method, confidence, ai_reason, alternatives_json,
                status, review_required, review_rule_fired, review_reason, ignored, updated_at
            )
            VALUES (?, ?, 'bad_date.csv', 'joining_date', 'date_like', '[]', 'joining_date', 'joining_date',
                    'manual', 1.0, '', '[]', 'MANUALLY_APPROVED', 0, NULL, NULL, 0, ?)
            """,
            (migration_id, file_id, now),
        )
        connection.execute(
            """
            INSERT INTO date_column_escalations (
                migration_id, source_file_id, source_file, source_column,
                issue_type, status, chosen_format, sample_values_json, review_reason, updated_at
            )
            VALUES (?, ?, 'bad_date.csv', 'joining_date', 'DATE_FORMAT_AMBIGUITY', 'RESOLVED',
                    'DD/MM/YYYY', '[]', '', ?)
            """,
            (migration_id, file_id, now),
        )
        connection.execute(
            """
            INSERT INTO normalized_records (migration_id, employee_id, payload_json, status, created_at)
            VALUES (?, 'E099', ?, 'TRANSFORMED', ?)
            """,
            (
                migration_id,
                json.dumps(
                    {
                        "employee_id": "E099",
                        "first_name": "Test",
                        "last_name": None,
                        "email": "test@example.com",
                        "joining_date": "not-a-valid-date",
                        "department": None,
                        "city": None,
                    }
                ),
                now,
            ),
        )
        record_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
        connection.execute(
            """
            INSERT INTO record_lineage (
                normalized_record_id, source_row_id, source_file, source_row_number
            )
            VALUES (?, ?, 'bad_date.csv', 2)
            """,
            (record_id, source_row_id),
        )

    validate_migration(migration_id)
    payload = list_validation_escalations(migration_id)
    assert payload["blocking_count"] == 1
    issue = payload["escalations"][0]
    assert issue["rule_fired"] == CLEANING_FAILURE
    assert issue["field_name"] == "joining_date"
    assert "could not be cleaned" in issue["review_reason"].lower()
