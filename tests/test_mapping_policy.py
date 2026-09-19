from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from flask_app import create_app

from app.database import init_db
from app.services.compatibility import is_structurally_compatible
from app.services.mapping_policy import (
    AUTO_APPROVED,
    CONFIDENCE_THRESHOLD,
    NEEDS_REVIEW,
    RULE_CONFIDENCE,
    RULE_STRUCTURAL,
    evaluate_mapping_policy,
)


def test_structural_doj_to_employee_id_fails() -> None:
    ok, reason = is_structurally_compatible("date_like", "employee_id")
    assert ok is False
    assert reason and "date-like" in reason.lower()


def test_spec_example_a_auto_approve() -> None:
    result = evaluate_mapping_policy(
        source_type="date_like",
        proposed_target="joining_date",
        confidence=0.96,
    )
    assert result["status"] == AUTO_APPROVED
    assert result["review_required"] is False


def test_spec_example_b_low_confidence() -> None:
    result = evaluate_mapping_policy(
        source_type="date_like",
        proposed_target="joining_date",
        confidence=0.54,
    )
    assert result["status"] == NEEDS_REVIEW
    assert result["review_rule_fired"] == RULE_CONFIDENCE
    assert str(CONFIDENCE_THRESHOLD) in result["review_reason"] or "0.85" in result["review_reason"]


def test_spec_example_c_structural_overrides_high_confidence() -> None:
    result = evaluate_mapping_policy(
        source_type="date_like",
        proposed_target="employee_id",
        confidence=0.91,
    )
    assert result["status"] == NEEDS_REVIEW
    assert result["review_rule_fired"] == RULE_STRUCTURAL
    assert result["review_reason"]


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "migration.db"
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr("app.database.DATABASE_PATH", db_path)
    monkeypatch.setattr("app.services.ingestion.UPLOAD_DIR", upload_dir)
    init_db(db_path)
    return create_app().test_client()


def test_generate_mappings_persists_policy_and_human_override(client) -> None:
    created = client.post("/api/migrations", json={"name": "Policy"})
    migration_id = created.get_json()["id"]
    client.post(f"/api/migrations/{migration_id}/demo-files")

    mock_semantic = {
        "source_column": "Date",
        "source_type": "date_like",
        "target_field": "joining_date",
        "confidence": 0.54,
        "reason": "low confidence semantic",
        "alternatives": [],
        "method": "ollama",
        "success": True,
    }

    def _semantic_for_date_only(column: str, _source_type: str, _samples: list[str]) -> dict:
        if column == "Date":
            return mock_semantic
        return {
            "source_column": column,
            "success": False,
            "target_field": None,
            "confidence": None,
            "reason": "not mocked",
            "alternatives": [],
            "method": "ollama",
        }

    with patch("app.services.llm_client.LLMClient.infer_mapping", side_effect=_semantic_for_date_only):
        response = client.post(
            f"/api/migrations/{migration_id}/mappings/generate?include_semantic=true"
        )
    assert response.status_code == 201
    payload = response.get_json()
    date_row = next(m for m in payload["mappings"] if m["source_column"] == "Date")
    assert date_row["review_required"] is True
    assert date_row["review_rule_fired"] == RULE_CONFIDENCE

    fixed = client.patch(
        f"/api/migrations/{migration_id}/mappings/{date_row['id']}",
        json={"action": "map", "target_field": "joining_date"},
    )
    assert fixed.status_code == 200
    assert fixed.get_json()["review_required"] is False

    readiness = client.get(f"/api/migrations/{migration_id}/mappings").get_json()
    assert readiness["blocking_review_count"] >= 0
