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
                    {"id": 1, "name": "Alpha", "file_count": 1, "status": "CREATED", "completed_at": None},
                    {"id": 2, "name": "Beta", "file_count": 2, "status": "CREATED", "completed_at": None},
                ]
            }
        elif path == "/api/migrations/1":
            response.json.return_value = {
                "id": 1,
                "name": "Alpha",
                "file_count": 1,
                "total_source_rows": 1,
                "status": "CREATED",
                "completed_at": None,
                "files": [],
                "entity": "employees",
                "auto_remove_exact_duplicates": True,
                "created_at": "2026-01-01",
            }
        elif path == "/api/migrations/2":
            response.json.return_value = {
                "id": 2,
                "name": "Beta",
                "file_count": 2,
                "total_source_rows": 2,
                "status": "CREATED",
                "completed_at": None,
                "files": [],
                "entity": "employees",
                "auto_remove_exact_duplicates": True,
                "created_at": "2026-01-01",
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
    # ui.migration imports api_get directly, so patch its bound reference too.
    # This keeps AppTest hermetic even when another test imported ui.migration
    # before this fixture ran.
    monkeypatch.setattr("ui.migration.api_get", fake_get)


def test_streamlit_entrypoint_loads(mock_backend: None) -> None:
    at = AppTest.from_file(PROJECT_ROOT / "streamlit_app.py", default_timeout=15).run()
    assert not at.exception
    assert at.title[0].value == "New migration"


def test_settings_page_loads(mock_backend: None) -> None:
    at = AppTest.from_file(PROJECT_ROOT / "streamlit_app.py", default_timeout=15).run()
    at.switch_page("app_pages/settings.py").run()
    assert not at.exception


def test_migration_switch_updates_session_migration_id() -> None:
    """Bound picker updates session migration_id when the user switches."""
    script = """
import streamlit as st
from ui.migration_picker import render_bound_migration_selectbox

labels = {
    "MIG-1 • Alpha (1 files)": 1,
    "MIG-2 • Beta (2 files)": 2,
}
options = ["(none)"] + list(labels.keys())
render_bound_migration_selectbox(
    label="Active migration",
    session_key="new_migration_active_pick",
    option_labels=options,
    label_to_id=labels,
)
"""
    label_one = "MIG-1 • Alpha (1 files)"
    label_two = "MIG-2 • Beta (2 files)"
    at = AppTest.from_string(script, default_timeout=15).run()
    at.selectbox(key="new_migration_active_pick").select(label_one).run()
    assert at.session_state["migration_id"] == 1
    at.selectbox(key="new_migration_active_pick").select(label_two).run()
    assert at.session_state["migration_id"] == 2


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
    monkeypatch.setattr("ui.migration.api_get", fake_get)
    at = AppTest.from_file(PROJECT_ROOT / "streamlit_app.py", default_timeout=15).run()
    at.session_state["migration_id"] = 1
    at.switch_page("app_pages/audit.py").run()
    assert not at.exception


def test_push_page_shows_mixed_workflow_state(mock_backend: None, monkeypatch: pytest.MonkeyPatch) -> None:
    push_overview = {
        "migration_id": 1,
        "record_counts": {"ready_to_push": 9, "pushed": 0, "push_failed": 1},
        "migration_state": {
            "summary": "9 ready, 0 pushed, 1 failed.",
            "failed_employee_ids": ["E009"],
        },
        "workflow": {
            "phase": "ready_and_failed",
            "title": "Rolled-back records are ready; earlier failures remain",
            "summary": "9 record(s) are ready to push again. 1 record(s) remain failed.",
            "next_step": "Push the ready records and retry the failed records.",
            "can_complete": False,
        },
        "latest_operation": None,
        "failed_records": [{"employee_id": "E009", "reason": "Simulated target failure", "http_status": 500}],
        "target_record_count": 0,
        "target_records": [],
        "attempt_history": [],
    }

    def fake_get(path: str, timeout: int = 10, **kwargs):
        response = MagicMock()
        response.status_code = 200
        if path == "/health":
            response.json.return_value = {"status": "ok", "sqlite": {"initialized": "true"}}
        elif path == "/api/migrations":
            response.json.return_value = {
                "migrations": [
                    {
                        "id": 1,
                        "name": "Demo",
                        "file_count": 3,
                        "status": "VALIDATED",
                        "completed_at": None,
                    }
                ]
            }
        elif path == "/api/migrations/1/mappings":
            response.json.return_value = {
                "mapping_count": 5,
                "blocking_review_count": 0,
                "mappings": [],
            }
        elif path == "/api/migrations/1/analysis/snapshot":
            response.json.return_value = {"issues_requiring_review": 0}
        elif path == "/api/migrations/1/push/overview":
            response.json.return_value = push_overview
        elif path == "/api/migrations/1":
            response.json.return_value = {
                "id": 1,
                "name": "Demo",
                "file_count": 3,
                "total_source_rows": 10,
                "status": "VALIDATED",
                "completed_at": None,
                "files": [],
                "entity": "employees",
                "auto_remove_exact_duplicates": True,
                "created_at": "2026-01-01",
            }
        else:
            response.status_code = 404
            response.json.return_value = {"error": "not found"}
        return response

    demo_migration = {
        "id": 1,
        "name": "Demo",
        "file_count": 3,
        "status": "VALIDATED",
        "completed_at": None,
        "files": [],
        "entity": "employees",
        "auto_remove_exact_duplicates": True,
        "created_at": "2026-01-01",
        "total_source_rows": 10,
    }
    monkeypatch.setattr("ui.api.api_get", fake_get)
    monkeypatch.setattr("ui.migration.require_migration_push_ready", lambda _msg: demo_migration)
    at = AppTest.from_file(PROJECT_ROOT / "streamlit_app.py", default_timeout=15).run()
    at.session_state["migration_id"] = 1
    at.switch_page("app_pages/push.py").run()
    assert not at.exception
    button_labels = [btn.label for btn in at.button]
    assert "Push ready records (9)" in button_labels
    assert "Retry failed records (1)" in button_labels
    titles = [m.value for m in at.markdown if m.value]
    assert any("Rolled-back records are ready" in t for t in titles)
