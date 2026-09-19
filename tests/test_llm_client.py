from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.database import init_db
from app.services.llm_client import LLMClient, normalize_mapping_result, parse_mapping_json
from app.services.source_analysis import analyze_migration
from flask_app import create_app


def test_parse_mapping_json_from_plain_and_embedded() -> None:
    payload = '{"target_field":"joining_date","confidence":0.96,"reason":"ok","alternatives":[]}'
    assert parse_mapping_json(payload)["target_field"] == "joining_date"
    wrapped = f"Here is the result:\n```json\n{payload}\n```"
    # brace extraction should still work without fences in our simple parser - use embedded
    embedded = f"noise {payload} trailing"
    assert parse_mapping_json(embedded)["confidence"] == 0.96
    assert parse_mapping_json("not json at all") is None


def test_infer_mapping_success() -> None:
    client = LLMClient(base_url="http://ollama.test", model="test-model")
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = {
        "response": (
            '{"source_column":"Date","source_type":"date_like",'
            '"target_field":"joining_date","confidence":0.91,'
            '"reason":"Date column holds joining dates.","alternatives":[]}'
        )
    }
    with patch("app.services.llm_client.requests.post", return_value=response) as post:
        result = client.infer_mapping("Date", "date_like", ["03/04/2024", "05/06/2024"])
    assert post.called
    assert result["success"] is True
    assert result["target_field"] == "joining_date"
    assert result["confidence"] == 0.91
    assert result["method"] == "ollama"


def test_infer_mapping_malformed_does_not_raise() -> None:
    client = LLMClient(base_url="http://ollama.test", model="test-model")
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = {"response": "Sure! The answer is definitely joining_date."}
    with patch("app.services.llm_client.requests.post", return_value=response):
        result = client.infer_mapping("Date", "date_like", ["03/04/2024"])
    assert result["success"] is False
    assert result["method"] == "ollama_failed"
    assert result["target_field"] is None


def test_infer_mapping_connection_failure_does_not_raise() -> None:
    client = LLMClient(base_url="http://ollama.test", model="test-model")
    with patch("app.services.llm_client.requests.post", side_effect=ConnectionError("refused")):
        result = client.infer_mapping("Employee Name", "string_like", ["Meet Mehta"])
    assert result["success"] is False
    assert "failed" in (result["reason"] or "").lower()


def test_normalize_mapping_rejects_invalid_target() -> None:
    base = {
        "source_column": "X",
        "source_type": "string_like",
        "target_field": None,
        "confidence": None,
        "reason": None,
        "alternatives": [],
        "method": "ollama",
        "success": False,
    }
    out = normalize_mapping_result(
        {"target_field": "not_a_field", "confidence": 0.9, "reason": "bad", "alternatives": []},
        base,
    )
    assert out["method"] == "ollama_failed"


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "migration.db"
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr("app.database.DATABASE_PATH", db_path)
    monkeypatch.setattr("app.services.ingestion.UPLOAD_DIR", upload_dir)
    init_db(db_path)
    return create_app().test_client()


def test_source_analysis_semantic_uses_mocked_ollama(client) -> None:
    created = client.post("/api/migrations", json={"name": "Semantic"})
    migration_id = created.get_json()["id"]
    client.post(f"/api/migrations/{migration_id}/demo-files")

    mock_client = MagicMock()
    mock_client.infer_mapping.return_value = {
        "source_column": "Date",
        "source_type": "date_like",
        "target_field": "joining_date",
        "confidence": 0.88,
        "reason": "Semantic match for date of join.",
        "alternatives": [],
        "method": "ollama",
        "success": True,
    }

    with patch("app.services.source_analysis.LLMClient", return_value=mock_client):
        response = client.get(
            f"/api/migrations/{migration_id}/source-analysis?include_semantic=true"
        )
    assert response.status_code == 200
    payload = response.get_json()
    date_col = next(
        c for c in payload["columns"] if c["source_column"] == "Date" and c["source_file"].endswith(".csv")
    )
    assert date_col["proposed_target"] == "joining_date"
    assert date_col["mapping_method"] == "ollama"
    assert payload["semantic_mappings"] >= 1
