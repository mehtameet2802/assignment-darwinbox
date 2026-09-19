from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from app.database import init_db
from app.services.date_escalations import list_date_escalations, resolve_date_escalation, scan_date_columns
from app.services.dates import (
    FORMAT_DMY,
    FORMAT_MDY,
    analyze_date_column,
    parse_with_format,
    split_date_and_time,
)
from flask_app import create_app


def test_time_component_removed() -> None:
    _, t1 = split_date_and_time("12/05/2024 09:30")
    assert t1 is True
    result = parse_with_format("12/05/2024 09:30", FORMAT_DMY)
    assert result.ok and result.value == "2024-05-12" and result.time_removed

    result2 = parse_with_format("2024-05-12 14:22:31", FORMAT_DMY)
    assert result2.value == "2024-05-12" and result2.time_removed

    result3 = parse_with_format("2024-05-12T09:30:00+05:30", FORMAT_DMY)
    assert result3.value == "2024-05-12" and result3.time_removed


def test_dmy_parse_example() -> None:
    result = parse_with_format("12/05/2024", FORMAT_DMY)
    assert result.value == "2024-05-12"


def test_ambiguous_column_not_per_row() -> None:
    analysis = analyze_date_column(["03/04/2024", "05/06/2024", "07/08/2024"])
    assert analysis["ambiguous"] is True
    assert analysis["issue_type"] == "DATE_FORMAT_AMBIGUITY"
    assert len(analysis["sample_values"]) == 3


def test_unambiguous_dmy_from_day_gt_12() -> None:
    analysis = analyze_date_column(["18/08/2022", "03/04/2024"])
    assert analysis["ambiguous"] is False
    assert analysis["chosen_format"] == FORMAT_DMY


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "migration.db"
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr("app.database.DATABASE_PATH", db_path)
    monkeypatch.setattr("app.services.ingestion.UPLOAD_DIR", upload_dir)
    init_db(db_path)
    return create_app().test_client()


def test_scan_creates_one_column_escalation_for_extra_date(client) -> None:
    created = client.post("/api/migrations", json={"name": "Dates"})
    migration_id = created.get_json()["id"]
    client.post(f"/api/migrations/{migration_id}/demo-files")

    mock_semantic = {
        "target_field": "joining_date",
        "confidence": 0.9,
        "reason": "semantic",
        "alternatives": [],
        "method": "ollama",
        "success": True,
    }

    def fake_infer(column, source_type, samples):
        payload = {**mock_semantic, "source_column": column}
        if column in {"DOJ", "Joining Date", "Date"}:
            return payload
        return {
            "target_field": None,
            "confidence": None,
            "reason": None,
            "alternatives": [],
            "method": "ollama_failed",
            "success": False,
        }

    with patch("app.services.llm_client.LLMClient.infer_mapping", side_effect=fake_infer):
        client.post(f"/api/migrations/{migration_id}/mappings/generate?include_semantic=true")

    response = client.post(f"/api/migrations/{migration_id}/date-columns/scan")
    assert response.status_code == 201
    payload = response.get_json()
    extra_escalations = [
        e
        for e in payload["escalations"]
        if e["source_file"] == "employees_extra.csv" and e["source_column"] == "Date"
    ]
    assert len(extra_escalations) == 1
    # Demo file includes 13/09/2024, so the column auto-resolves to DD/MM/YYYY (one column decision).
    assert extra_escalations[0]["status"] == "RESOLVED"
    assert extra_escalations[0]["chosen_format"] == FORMAT_DMY

    listed = list_date_escalations(migration_id)
    assert listed["blocking_count"] == 0

    needs_review = [e for e in payload["escalations"] if e["status"] == "NEEDS_REVIEW"]
    assert all(e["source_column"] != "Date" or e["source_file"] != "employees_extra.csv" for e in needs_review)
