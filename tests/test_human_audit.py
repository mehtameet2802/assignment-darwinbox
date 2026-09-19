from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from flask_app import create_app

from app.database import init_db
from app.services.duplicates import list_duplicate_conflicts
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


def _audit_actions(client, migration_id: int) -> set[str]:
    log = client.get(
        f"/api/migrations/{migration_id}/audit-log?limit=500&offset=0"
    ).get_json()
    return {entry["action"] for entry in log["entries"]}


def test_human_mapping_date_and_duplicate_actions_are_audited(client) -> None:
    created = client.post("/api/migrations", json={"name": "Human audit"})
    migration_id = created.get_json()["id"]
    client.post(f"/api/migrations/{migration_id}/demo-files")

    with patch("app.services.llm_client.LLMClient.infer_mapping", side_effect=_ollama_side_effect):
        mappings = client.post(
            f"/api/migrations/{migration_id}/mappings/generate?include_semantic=true"
        ).get_json()
    date_row = next(m for m in mappings["mappings"] if m["source_column"] == "Date")
    client.patch(
        f"/api/migrations/{migration_id}/mappings/{date_row['id']}",
        json={"action": "map", "target_field": "joining_date"},
    )

    scan = client.post(f"/api/migrations/{migration_id}/date-columns/scan").get_json()
    date_esc = next(
        (e for e in scan["escalations"] if e["status"] == "NEEDS_REVIEW"),
        scan["escalations"][0],
    )
    chosen = date_esc.get("chosen_format") or "DD/MM/YYYY"
    client.patch(
        f"/api/migrations/{migration_id}/date-escalations/{date_esc['id']}",
        json={"chosen_format": chosen},
    )

    assert client.post(f"/api/migrations/{migration_id}/transform").status_code == 201
    assert client.post(f"/api/migrations/{migration_id}/duplicates/analyze").status_code == 201

    conflicts = list_duplicate_conflicts(migration_id)
    e002 = next(c for c in conflicts["conflicts"] if c["employee_id"] == "E002")
    base = e002["members"][0]["payload"]
    client.patch(
        f"/api/migrations/{migration_id}/duplicate-conflicts/{e002['id']}",
        json={"action": "save", "final_payload": {**base, "email": "ravi@example.com"}},
    )

    actions = _audit_actions(client, migration_id)
    assert actions >= {"human correction"}
