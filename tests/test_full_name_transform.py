from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from flask_app import create_app

from app.database import db_session, init_db
from tests.test_duplicates import _ollama_side_effect


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "migration.db"
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr("app.database.DATABASE_PATH", db_path)
    monkeypatch.setattr("app.services.ingestion.UPLOAD_DIR", upload_dir)
    init_db(db_path)
    return create_app().test_client()


def test_transform_splits_employee_name_into_first_and_last(client) -> None:
    created = client.post("/api/migrations", json={"name": "Name split"})
    migration_id = created.get_json()["id"]
    client.post(f"/api/migrations/{migration_id}/demo-files")

    with patch("app.services.llm_client.LLMClient.infer_mapping", side_effect=_ollama_side_effect):
        client.post(f"/api/migrations/{migration_id}/mappings/generate?include_semantic=true")
    client.post(f"/api/migrations/{migration_id}/date-columns/scan")
    from tests.test_duplicates import _resolve_blocking_date_escalations

    _resolve_blocking_date_escalations(client, migration_id)
    client.post(f"/api/migrations/{migration_id}/transform")

    with db_session() as connection:
        rows = connection.execute(
            """
            SELECT nr.payload_json
            FROM normalized_records nr
            JOIN record_lineage rl ON rl.normalized_record_id = nr.id
            WHERE nr.migration_id = ? AND rl.source_file = 'employees_legacy.csv'
            ORDER BY rl.source_row_number
            LIMIT 1
            """,
            (migration_id,),
        ).fetchall()
    assert rows
    payload = json.loads(rows[0]["payload_json"])
    assert payload["first_name"] == "Meet"
    assert payload["last_name"] == "Mehta"
