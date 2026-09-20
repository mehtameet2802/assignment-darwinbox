from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from flask_app import create_app

from app.database import init_db
from app.services.duplicates import list_duplicate_conflicts


def _ollama_side_effect(column, source_type, samples):
    if column in {"Employee Name", "Full Name", "Name"}:
        return {
            "source_column": column,
            "source_type": source_type,
            "target_field": "first_name",
            "confidence": 0.92,
            "reason": "name column",
            "alternatives": [],
            "method": "ollama",
            "success": True,
        }
    if column == "Date":
        return {
            "source_column": column,
            "source_type": source_type,
            "target_field": "joining_date",
            "confidence": 0.9,
            "reason": "date column",
            "alternatives": [],
            "method": "ollama",
            "success": True,
        }
    return {
        "source_column": column,
        "source_type": source_type,
        "target_field": None,
        "confidence": None,
        "reason": None,
        "alternatives": [],
        "method": "ollama_failed",
        "success": False,
    }


def _resolve_blocking_date_escalations(client, migration_id: int) -> None:
    listed = client.get(f"/api/migrations/{migration_id}/date-escalations").get_json()
    for esc in listed.get("escalations", []):
        if esc.get("status") == "NEEDS_REVIEW":
            client.patch(
                f"/api/migrations/{migration_id}/date-escalations/{esc['id']}",
                json={"chosen_format": "DD/MM/YYYY"},
            )


def _run_demo_pipeline(client, migration_id: int) -> None:
    with patch("app.services.llm_client.LLMClient.infer_mapping", side_effect=_ollama_side_effect):
        gen = client.post(f"/api/migrations/{migration_id}/mappings/generate?include_semantic=true")
        assert gen.status_code == 201
    scan = client.post(f"/api/migrations/{migration_id}/date-columns/scan")
    assert scan.status_code == 201
    _resolve_blocking_date_escalations(client, migration_id)
    transform = client.post(f"/api/migrations/{migration_id}/transform")
    assert transform.status_code == 201
    analyze = client.post(f"/api/migrations/{migration_id}/duplicates/analyze")
    assert analyze.status_code == 201


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "migration.db"
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr("app.database.DATABASE_PATH", db_path)
    monkeypatch.setattr("app.services.ingestion.UPLOAD_DIR", upload_dir)
    init_db(db_path)
    return create_app().test_client()


def test_e001_exact_duplicate_retains_both_source_rows(client) -> None:
    created = client.post("/api/migrations", json={"name": "Dupes"})
    migration_id = created.get_json()["id"]
    client.post(f"/api/migrations/{migration_id}/demo-files")
    _run_demo_pipeline(client, migration_id)

    summary = client.get(f"/api/migrations/{migration_id}/records/E001/lineage").get_json()
    sources = {(s["source_file"], s["source_row_number"]) for s in summary["sources"]}
    assert sources == {
        ("employees_legacy.csv", 2),
        ("employee_master.xlsx", 2),
    }


def test_e002_duplicate_conflict_created(client) -> None:
    created = client.post("/api/migrations", json={"name": "Dupes"})
    migration_id = created.get_json()["id"]
    client.post(f"/api/migrations/{migration_id}/demo-files")
    _run_demo_pipeline(client, migration_id)

    payload = list_duplicate_conflicts(migration_id)
    e002 = next((c for c in payload["conflicts"] if c["employee_id"] == "E002"), None)
    assert e002 is not None
    assert e002["rule_fired"] == "DUPLICATE_CONFLICT"
    assert "email" in e002["review_reason"]
    assert len(e002["members"]) == 2


def test_resolve_e002_keeps_dual_lineage(client) -> None:
    created = client.post("/api/migrations", json={"name": "Dupes"})
    migration_id = created.get_json()["id"]
    client.post(f"/api/migrations/{migration_id}/demo-files")
    _run_demo_pipeline(client, migration_id)

    payload = list_duplicate_conflicts(migration_id)
    e002 = next(c for c in payload["conflicts"] if c["employee_id"] == "E002")
    base = e002["members"][0]["payload"]
    final_payload = {**base, "email": "ravi@example.com"}
    resolved = client.patch(
        f"/api/migrations/{migration_id}/duplicate-conflicts/{e002['id']}",
        json={"action": "save", "final_payload": final_payload},
    )
    assert resolved.status_code == 200

    summary = client.get(f"/api/migrations/{migration_id}/records/E002/lineage").get_json()
    sources = {(s["source_file"], s["source_row_number"]) for s in summary["sources"]}
    assert ("employees_legacy.csv", 3) in sources
    assert ("employee_master.xlsx", 3) in sources
