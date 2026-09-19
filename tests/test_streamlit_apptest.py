from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from streamlit.testing.v1 import AppTest

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def mock_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    health = {"status": "ok", "sqlite": {"initialized": "true"}}

    def fake_get(path: str, timeout: int = 10, **kwargs):
        response = MagicMock()
        response.status_code = 200
        if path == "/health":
            response.json.return_value = health
        elif path == "/api/migrations":
            response.json.return_value = {
                "migrations": [
                    {"id": 1, "name": "Demo", "file_count": 0, "status": "CREATED", "completed_at": None}
                ]
            }
        elif path == "/api/migrations/1":
            response.json.return_value = {
                "id": 1,
                "name": "Demo",
                "file_count": 0,
                "total_source_rows": 0,
                "status": "CREATED",
                "completed_at": None,
                "files": [],
            }
        elif path.startswith("/api/migrations/1/"):
            response.json.return_value = {}
        elif path.endswith("/mappings"):
            response.json.return_value = {
                "mapping_count": 0,
                "blocking_review_count": 0,
                "mappings": [],
            }
        else:
            response.status_code = 404
            response.json.return_value = {"error": "not found"}
        return response

    def fake_post(path: str, **kwargs):
        response = MagicMock()
        response.status_code = 201
        response.json.return_value = {"id": 1}
        return response

    monkeypatch.setattr("ui.api.fetch_backend_health", lambda: (True, health))
    monkeypatch.setattr("ui.api.api_get", fake_get)
    monkeypatch.setattr("ui.api.api_post", fake_post)


def test_streamlit_entrypoint_loads(mock_backend: None) -> None:
    at = AppTest.from_file(PROJECT_ROOT / "streamlit_app.py", default_timeout=15).run()
    assert not at.exception
    assert at.title[0].value == "New migration"


def test_settings_page_loads(mock_backend: None) -> None:
    at = AppTest.from_file(PROJECT_ROOT / "streamlit_app.py", default_timeout=15).run()
    at.switch_page("app_pages/settings.py").run()
    assert not at.exception


def test_audit_page_loads(mock_backend: None, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get(path: str, timeout: int = 10, **kwargs):
        response = MagicMock()
        response.status_code = 200
        if path == "/health":
            response.json.return_value = {"status": "ok", "sqlite": {"initialized": "true"}}
        elif path == "/api/migrations":
            response.json.return_value = {
                "migrations": [
                    {"id": 1, "name": "Demo", "file_count": 0, "status": "PUSHED", "completed_at": None}
                ]
            }
        elif "/audit-log" in path:
            response.json.return_value = {
                "migration_id": 1,
                "total": 1,
                "limit": 25,
                "offset": 0,
                "entries": [
                    {
                        "timestamp": "2026-01-01T00:00:00Z",
                        "actor": "AGENT",
                        "action": "push succeeded",
                        "entity": "E009",
                        "reason": "HTTP 201",
                    }
                ],
            }
        elif path == "/api/migrations/1":
            response.json.return_value = {
                "id": 1,
                "name": "Demo",
                "file_count": 0,
                "total_source_rows": 0,
                "status": "PUSHED",
                "completed_at": None,
                "files": [],
            }
        else:
            response.status_code = 404
            response.json.return_value = {"error": "not found"}
        return response

    monkeypatch.setattr("ui.api.api_get", fake_get)
    at = AppTest.from_file(PROJECT_ROOT / "streamlit_app.py", default_timeout=15).run()
    at.session_state["migration_id"] = 1
    at.switch_page("app_pages/audit.py").run()
    assert not at.exception
