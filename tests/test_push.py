from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from flask_app import create_app

from app.database import init_db
from app.services.mock_target import list_batch_records, list_target_records_for_migration
from app.status import PUSH_FAILED, PUSHED, READY_TO_PUSH
from tests.test_duplicates import _ollama_side_effect, _resolve_blocking_date_escalations


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "migration.db"
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr("app.database.DATABASE_PATH", db_path)
    monkeypatch.setattr("app.services.ingestion.UPLOAD_DIR", upload_dir)
    init_db(db_path)
    return create_app().test_client()


def _prepare_ready_records(client, migration_id: int) -> None:
    with patch("app.services.llm_client.LLMClient.infer_mapping", side_effect=_ollama_side_effect):
        client.post(f"/api/migrations/{migration_id}/mappings/generate?include_semantic=true")
    client.post(f"/api/migrations/{migration_id}/date-columns/scan")
    _resolve_blocking_date_escalations(client, migration_id)
    client.post(f"/api/migrations/{migration_id}/transform")
    client.post(f"/api/migrations/{migration_id}/duplicates/analyze")
    dup = client.get(f"/api/migrations/{migration_id}/duplicate-conflicts").get_json()
    e002 = next((c for c in dup["conflicts"] if c["employee_id"] == "E002"), None)
    if e002 and e002["status"] == "NEEDS_REVIEW":
        base = e002["members"][0]["payload"]
        client.patch(
            f"/api/migrations/{migration_id}/duplicate-conflicts/{e002['id']}",
            json={"action": "save", "final_payload": {**base, "email": "ravi@example.com"}},
        )
    client.post(f"/api/migrations/{migration_id}/validate")
    val_list = client.get(f"/api/migrations/{migration_id}/validation-escalations").get_json()
    for employee_id, action in (
        ("E011", {"action": "enter_value", "field_name": "email", "value": "anjali@example.com"}),
        ("E010", {"action": "exclude"}),
    ):
        esc = next(e for e in val_list["escalations"] if e["employee_id"] == employee_id)
        if esc.get("status") == "NEEDS_REVIEW":
            client.patch(
                f"/api/migrations/{migration_id}/validation-escalations/{esc['id']}",
                json=action,
            )


def test_e009_push_then_retry(client) -> None:
    created = client.post("/api/migrations", json={"name": "Push"})
    migration_id = created.get_json()["id"]
    client.post(f"/api/migrations/{migration_id}/demo-files")
    _prepare_ready_records(client, migration_id)

    first = client.post(f"/api/migrations/{migration_id}/push")
    assert first.status_code == 201
    first_payload = first.get_json()
    e009_first = next(r for r in first_payload["results"] if r["employee_id"] == "E009")
    assert e009_first["http_status"] == 500
    assert e009_first["result"] == "failure"

    succeeded = [r for r in first_payload["results"] if r["result"] == "success"]
    assert succeeded
    batch_key = first_payload["batch_key"]
    assert list_batch_records(batch_key)

    retry = client.post(f"/api/migrations/{migration_id}/push/retry")
    assert retry.status_code == 201
    retry_payload = retry.get_json()
    assert retry_payload["records_attempted"] == 1
    e009_retry = retry_payload["results"][0]
    assert e009_retry["employee_id"] == "E009"
    assert e009_retry["http_status"] == 201
    assert e009_retry["attempt_number"] == 2

    attempts = client.get(f"/api/migrations/{migration_id}/push/attempts").get_json()["attempts"]
    e009_attempts = [a for a in attempts if a["employee_id"] == "E009"]
    assert len(e009_attempts) == 2
    assert e009_attempts[0]["http_status"] == 500
    assert e009_attempts[1]["http_status"] == 201

    e007_attempts = [a for a in attempts if a["employee_id"] == "E007"]
    assert len(e007_attempts) == 1


def test_rollback_removes_target_batch_records(client) -> None:
    created = client.post("/api/migrations", json={"name": "Rollback"})
    migration_id = created.get_json()["id"]
    client.post(f"/api/migrations/{migration_id}/demo-files")
    _prepare_ready_records(client, migration_id)

    push = client.post(f"/api/migrations/{migration_id}/push").get_json()
    batch_key = push["batch_key"]
    before = list_batch_records(batch_key)

    rollback = client.post(f"/api/migrations/{migration_id}/push/rollback")
    assert rollback.status_code == 200
    assert list_batch_records(batch_key) == []

    from app.database import db_session

    with db_session() as connection:
        row = connection.execute(
            "SELECT status FROM normalized_records WHERE migration_id = ? AND employee_id = ?",
            (migration_id, before[0]["employee_id"]),
        ).fetchone()
    assert row["status"] == READY_TO_PUSH


def test_push_rollback_retry_full_sequence(client) -> None:
    """Push partial failure → rollback → re-push ready → retry E009 → complete target."""
    created = client.post("/api/migrations", json={"name": "Rollback sequence"})
    migration_id = created.get_json()["id"]
    client.post(f"/api/migrations/{migration_id}/demo-files")
    _prepare_ready_records(client, migration_id)

    first = client.post(f"/api/migrations/{migration_id}/push")
    assert first.status_code == 201
    first_body = first.get_json()
    successes = [r for r in first_body["results"] if r["result"] == "success"]
    failures = [r for r in first_body["results"] if r["result"] == "failure"]
    assert failures and failures[0]["employee_id"] == "E009"
    ready_total = len(first_body["results"])
    assert ready_total == 13
    assert len(successes) + len(failures) == ready_total
    assert len(failures) == 1
    success_count = len(successes)
    assert success_count == 12

    rollback = client.post(f"/api/migrations/{migration_id}/push/rollback")
    assert rollback.status_code == 200
    rollback_body = rollback.get_json()
    assert rollback_body["operation"] == "rollback"
    assert rollback_body["removed_from_target"] == success_count
    assert rollback_body["returned_to_ready"] == success_count
    assert rollback_body["unchanged_failed"] == 1
    assert rollback_body["unchanged_failed_employee_ids"] == ["E009"]
    assert rollback_body["post_operation_state"]["ready_to_push"] == success_count
    assert rollback_body["post_operation_state"]["push_failed"] == 1
    assert rollback_body["post_operation_state"]["target_records"] == 0

    overview = client.get(f"/api/migrations/{migration_id}/push/overview").get_json()
    assert overview["workflow"]["phase"] == "ready_and_failed"
    assert overview["workflow"]["can_complete"] is False
    assert overview["record_counts"]["ready_to_push"] == success_count
    assert overview["record_counts"]["push_failed"] == 1
    assert list_target_records_for_migration(migration_id) == []

    from app.database import db_session

    with db_session() as connection:
        e009 = connection.execute(
            "SELECT status FROM normalized_records WHERE migration_id = ? AND employee_id = ?",
            (migration_id, "E009"),
        ).fetchone()
    assert e009["status"] == PUSH_FAILED

    second = client.post(f"/api/migrations/{migration_id}/push")
    assert second.status_code == 201
    second_body = second.get_json()
    assert second_body["records_attempted"] == success_count
    assert all(r["employee_id"] != "E009" for r in second_body["results"])
    assert second_body["summary"]["successful"] == success_count

    overview2 = client.get(f"/api/migrations/{migration_id}/push/overview").get_json()
    assert overview2["record_counts"]["push_failed"] == 1
    assert [f["employee_id"] for f in overview2["failed_records"]] == ["E009"]
    assert overview2["record_counts"]["pushed"] == success_count

    retry = client.post(f"/api/migrations/{migration_id}/push/retry")
    assert retry.status_code == 201
    retry_body = retry.get_json()
    assert retry_body["records_attempted"] == 1
    assert retry_body["results"][0]["employee_id"] == "E009"
    assert retry_body["results"][0]["http_status"] == 201
    assert retry_body["results"][0]["attempt_number"] == 2

    target = list_target_records_for_migration(migration_id)
    assert len(target) == success_count + 1
    assert len({row["employee_id"] for row in target}) == success_count + 1

    with db_session() as connection:
        counts = connection.execute(
            """
            SELECT status, COUNT(*) AS n FROM normalized_records
            WHERE migration_id = ? AND status IN (?, ?, ?)
            GROUP BY status
            """,
            (migration_id, PUSHED, PUSH_FAILED, READY_TO_PUSH),
        ).fetchall()
    status_map = {row["status"]: row["n"] for row in counts}
    assert status_map.get(PUSH_FAILED, 0) == 0
    assert status_map.get(PUSHED, 0) == success_count + 1

    audit = client.get(f"/api/migrations/{migration_id}/audit-log?limit=500&offset=0").get_json()
    actions = [entry["action"] for entry in audit["entries"]]
    assert "push attempted" in actions
    assert "rollback completed" in actions
    assert "retry requested" in actions
    rollback_entries = [e for e in audit["entries"] if e["action"] == "rollback completed"]
    assert any("E009" in (e.get("reason") or "") for e in rollback_entries)
    assert any("never existed in the target" in (e.get("reason") or "") for e in rollback_entries)


def test_push_overview_separates_failed_and_history(client) -> None:
    created = client.post("/api/migrations", json={"name": "Overview"})
    migration_id = created.get_json()["id"]
    client.post(f"/api/migrations/{migration_id}/demo-files")
    _prepare_ready_records(client, migration_id)

    client.post(f"/api/migrations/{migration_id}/push")
    overview = client.get(f"/api/migrations/{migration_id}/push/overview").get_json()
    assert overview["record_counts"]["push_failed"] >= 1
    assert overview["failed_records"]
    assert overview["latest_operation"]["operation"] == "push"
    history = overview["attempt_history"]
    assert history[0]["operation_label"] == "Push"
    assert "batch_status" not in history[0]
