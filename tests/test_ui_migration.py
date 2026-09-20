from __future__ import annotations

from ui.migration import is_pipeline_active, list_pipeline_migrations


def test_is_pipeline_active_excludes_completed() -> None:
    assert is_pipeline_active({"id": 1, "completed_at": None})
    assert not is_pipeline_active({"id": 1, "completed_at": "2026-01-01T00:00:00Z"})


def test_list_pipeline_migrations_filters_completed(monkeypatch) -> None:
    listing = [
        {"id": 1, "completed_at": None, "file_count": 1},
        {"id": 2, "completed_at": "2026-01-01", "file_count": 3},
    ]

    def fake_get(path: str, timeout: int = 10, **kwargs):
        class Response:
            status_code = 200

            @staticmethod
            def json():
                return {"migrations": listing}

        return Response()

    monkeypatch.setattr("ui.migration.api_get", fake_get)
    active = list_pipeline_migrations()
    assert [item["id"] for item in active] == [1]
