"""End-to-end API flow aligned with the take-home acceptance criteria."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from flask_app import create_app

from app.database import init_db
from app.services.mock_target import list_batch_records
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


def test_take_home_acceptance_pipeline(client) -> None:
    """Multi-file ingest → autonomous mapping/cleanup → escalations → push/retry/audit."""

    # 1. Multi-file ingestion (same entity, different column layouts)
    created = client.post("/api/migrations", json={"name": "Acceptance E2E"})
    assert created.status_code == 201
    migration_id = created.get_json()["id"]
    ingest = client.post(f"/api/migrations/{migration_id}/demo-files")
    assert ingest.status_code == 201
    ingest_body = ingest.get_json()
    filenames = {f["filename"] for f in ingest_body["files"]}
    assert filenames == {
        "employees_legacy.csv",
        "employee_master.xlsx",
        "employees_extra.csv",
    }
    assert ingest_body["total_source_rows"] == 13

    # 2. Autonomous mapping (aliases + mocked semantic for ambiguous columns)
    with patch("app.services.llm_client.LLMClient.infer_mapping", side_effect=_ollama_side_effect):
        mappings = client.post(
            f"/api/migrations/{migration_id}/mappings/generate?include_semantic=true"
        )
    assert mappings.status_code == 201
    mapping_body = mappings.get_json()
    assert mapping_body["mapping_count"] > 0
    auto = [m for m in mapping_body["mappings"] if m["status"] == "AUTO_APPROVED"]
    assert auto, "expected deterministic alias auto-approvals without human input"

    # 3. Escalation boundary — date ambiguity is column-level, not per-row
    date_scan = client.post(f"/api/migrations/{migration_id}/date-columns/scan")
    assert date_scan.status_code == 201
    date_body = date_scan.get_json()
    extra_date = next(
        e
        for e in date_body["escalations"]
        if e["source_file"] == "employees_extra.csv" and e["source_column"] == "Date"
    )
    if extra_date["status"] == "NEEDS_REVIEW":
        assert extra_date["issue_type"] == "DATE_FORMAT_AMBIGUITY"
        client.patch(
            f"/api/migrations/{migration_id}/date-escalations/{extra_date['id']}",
            json={"chosen_format": "DD/MM/YYYY"},
        )
    else:
        assert extra_date["status"] in {"RESOLVED", "AUTO_RESOLVED"}
        assert extra_date.get("chosen_format")

    assert client.post(f"/api/migrations/{migration_id}/transform").status_code == 201
    assert client.post(f"/api/migrations/{migration_id}/duplicates/analyze").status_code == 201
    dup = client.get(f"/api/migrations/{migration_id}/duplicate-conflicts")
    assert dup.status_code == 200
    e002 = next(c for c in dup.get_json()["conflicts"] if c["employee_id"] == "E002")
    assert e002["status"] == "NEEDS_REVIEW"

    # 4. Human resolves duplicate conflict (simulates consultant action in UI)
    base = e002["members"][0]["payload"]
    client.patch(
        f"/api/migrations/{migration_id}/duplicate-conflicts/{e002['id']}",
        json={"action": "save", "final_payload": {**base, "email": "ravi@example.com"}},
    )

    assert client.post(f"/api/migrations/{migration_id}/validate").status_code == 201

    val_list = client.get(f"/api/migrations/{migration_id}/validation-escalations").get_json()
    e011 = next(e for e in val_list["escalations"] if e["employee_id"] == "E011")
    client.patch(
        f"/api/migrations/{migration_id}/validation-escalations/{e011['id']}",
        json={"action": "enter_value", "field_name": "email", "value": "anjali@example.com"},
    )
    e010 = next(e for e in val_list["escalations"] if e["employee_id"] == "E010")
    client.patch(
        f"/api/migrations/{migration_id}/validation-escalations/{e010['id']}",
        json={"action": "exclude"},
    )

    queue = client.get(f"/api/migrations/{migration_id}/review-queue").get_json()
    assert queue.get("blocking_count", 0) == 0

    # 5. Mock target push, per-record results, retry on transient failure
    push = client.post(f"/api/migrations/{migration_id}/push")
    assert push.status_code == 201
    push_body = push.get_json()
    e009 = next(r for r in push_body["results"] if r["employee_id"] == "E009")
    assert e009["result"] == "failure"
    batch_key = push_body["batch_key"]
    assert list_batch_records(batch_key)

    retry = client.post(f"/api/migrations/{migration_id}/push/retry")
    assert retry.status_code == 201
    assert retry.get_json()["results"][0]["employee_id"] == "E009"
    assert retry.get_json()["results"][0]["result"] == "success"

    # 6. Audit trail documents human correction and push attempts
    audit = client.get(f"/api/migrations/{migration_id}/audit-log?limit=200&offset=0").get_json()
    actions = {entry["action"] for entry in audit["entries"]}
    assert "human correction" in actions
    assert any("push" in a.lower() for a in actions)

    lineage = client.get(f"/api/migrations/{migration_id}/records/E001/lineage").get_json()
    source_files = {s["source_file"] for s in lineage["sources"]}
    assert source_files >= {"employees_legacy.csv", "employee_master.xlsx"}
