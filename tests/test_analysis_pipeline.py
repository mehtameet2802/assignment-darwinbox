from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from flask_app import create_app

from app.database import init_db
from tests.test_duplicates import _ollama_side_effect, _run_demo_pipeline


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "migration.db"
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr("app.database.DATABASE_PATH", db_path)
    monkeypatch.setattr("app.services.ingestion.UPLOAD_DIR", upload_dir)
    init_db(db_path)
    return create_app().test_client()


def test_analysis_run_endpoint(client) -> None:
    created = client.post("/api/migrations", json={"name": "Analysis"})
    migration_id = created.get_json()["id"]
    client.post(f"/api/migrations/{migration_id}/demo-files")
    with patch("app.services.llm_client.LLMClient.infer_mapping", side_effect=_ollama_side_effect):
        client.post(f"/api/migrations/{migration_id}/mappings/generate?include_semantic=true")
    _run_demo_pipeline(client, migration_id)

    response = client.post(f"/api/migrations/{migration_id}/analysis/run")
    assert response.status_code == 201
    payload = response.get_json()
    assert "issues_requiring_review" in payload
    assert payload.get("last_run", {}).get("phase") in {"full_processing", "blocked_dates"}
