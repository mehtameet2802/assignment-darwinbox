from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest

from app.config import DEMO_DIR, PROJECT_ROOT
from app.database import init_db
from app.services.ingestion import attach_lineage, find_source_rows
from flask_app import create_app


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "migration.db"
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr("app.database.DATABASE_PATH", db_path)
    monkeypatch.setattr("app.services.ingestion.UPLOAD_DIR", upload_dir)
    init_db(db_path)
    return create_app().test_client()


def test_upload_rejects_unsupported_format(client) -> None:
    created = client.post("/api/migrations", json={"name": "Reject test"})
    migration_id = created.get_json()["id"]
    response = client.post(
        f"/api/migrations/{migration_id}/files",
        data={"files": (BytesIO(b"not a spreadsheet"), "employees.txt")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 400
    assert "Unsupported file format" in response.get_json()["error"]


def test_demo_files_ingest_row_counts_columns_and_lineage(client) -> None:
    created = client.post("/api/migrations", json={"name": "Demo ingest"})
    migration_id = created.get_json()["id"]
    response = client.post(f"/api/migrations/{migration_id}/demo-files")
    assert response.status_code == 201, response.get_json()
    payload = response.get_json()

    files = {item["filename"]: item for item in payload["files"]}
    assert set(files) == {
        "employees_legacy.csv",
        "employee_master.xlsx",
        "employees_extra.csv",
    }
    assert files["employees_legacy.csv"]["row_count"] == 4
    assert files["employees_legacy.csv"]["column_count"] == 6
    assert files["employees_legacy.csv"]["columns"] == [
        "Emp Code",
        "Employee Name",
        "DOJ",
        "Mail",
        "Dept",
        "City",
    ]
    assert files["employee_master.xlsx"]["row_count"] == 4
    assert files["employee_master.xlsx"]["columns"] == [
        "Employee ID",
        "Full Name",
        "Joining Date",
        "Work Email",
        "Department",
        "Office",
    ]
    assert files["employees_extra.csv"]["row_count"] == 5
    assert payload["total_source_rows"] == 13

    legacy_preview = client.get(
        f"/api/migrations/{migration_id}/files/{files['employees_legacy.csv']['id']}/preview"
    ).get_json()
    first = legacy_preview["rows"][0]
    assert first["source_file"] == "employees_legacy.csv"
    assert first["source_row_number"] == 2
    assert first["Emp Code"] == "E001"

    master_preview = client.get(
        f"/api/migrations/{migration_id}/files/{files['employee_master.xlsx']['id']}/preview"
    ).get_json()
    assert master_preview["rows"][0]["source_row_number"] == 2
    assert master_preview["rows"][0]["Employee ID"] == "E001"

    extra_preview = client.get(
        f"/api/migrations/{migration_id}/files/{files['employees_extra.csv']['id']}/preview"
    ).get_json()
    e011 = extra_preview["rows"][-1]
    assert e011["Employee_No"] == "E011"
    assert e011["source_row_number"] == 6
    assert e011["Email"] == ""

    legacy_e001 = find_source_rows(migration_id, "employees_legacy.csv", 2)[0]
    master_e001 = find_source_rows(migration_id, "employee_master.xlsx", 2)[0]
    lineage = attach_lineage(
        migration_id,
        [legacy_e001["id"], master_e001["id"]],
        employee_id="E001",
    )
    sources = {(item["source_file"], item["source_row_number"]) for item in lineage["sources"]}
    assert sources == {
        ("employees_legacy.csv", 2),
        ("employee_master.xlsx", 2),
    }


def test_demo_files_exist_on_disk() -> None:
    assert (DEMO_DIR / "employees_legacy.csv").exists()
    assert (DEMO_DIR / "employee_master.xlsx").exists()
    assert (DEMO_DIR / "employees_extra.csv").exists()
    assert PROJECT_ROOT.joinpath("data", "demo").exists()
