from __future__ import annotations

from pathlib import Path

import pytest
from flask_app import create_app

from app.database import db_session, init_db, utcnow
from app.services.mapping import split_full_name
from app.services.mapping_policy import RULE_TARGET_FIELD_COLLISION
from app.services.mapping_store import list_mappings, refresh_target_field_collisions


def test_split_full_name_spec_examples() -> None:
    assert split_full_name("Meet Mehta") == ("Meet", "Mehta")
    assert split_full_name("Meet Gopal Mehta") == ("Meet", "Gopal Mehta")
    assert split_full_name("Madonna") == ("Madonna", None)
    assert split_full_name("") == (None, None)


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "migration.db"
    monkeypatch.setattr("app.database.DATABASE_PATH", db_path)
    init_db(db_path)
    return create_app().test_client()


def test_target_field_collision_blocks_mapping_review(client) -> None:
    created = client.post("/api/migrations", json={"name": "Collision"})
    migration_id = created.get_json()["id"]
    now = utcnow()
    with db_session() as connection:
        connection.execute(
            """
            INSERT INTO source_files (
                migration_id, original_filename, stored_path, format,
                row_count, column_count, columns_json, status, created_at
            )
            VALUES (?, 'dup.csv', '/tmp/dup.csv', 'csv', 1, 2, '[]', 'READY', ?)
            """,
            (migration_id, now),
        )
        file_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
        for column, target in (("Work Email", "email"), ("Mail", "email")):
            connection.execute(
                """
                INSERT INTO column_mappings (
                    migration_id, source_file_id, source_file, source_column,
                    detected_source_type, sample_values_json, proposed_target, final_target,
                    mapping_method, confidence, ai_reason, alternatives_json,
                    status, review_required, review_rule_fired, review_reason, ignored, updated_at
                )
                VALUES (?, ?, 'dup.csv', ?, 'email_like', '[]', 'email', 'email',
                        'deterministic_alias', 1.0, '', '[]',
                        'AUTO_APPROVED', 0, NULL, NULL, 0, ?)
                """,
                (migration_id, file_id, column, now),
            )
        blocked = refresh_target_field_collisions(connection, migration_id)
        assert blocked == 2

    payload = list_mappings(migration_id)
    assert payload["blocking_review_count"] == 2
    for item in payload["mappings"]:
        assert item["review_rule_fired"] == RULE_TARGET_FIELD_COLLISION

    transform = client.post(f"/api/migrations/{migration_id}/transform")
    assert transform.status_code == 400
