from __future__ import annotations

from pathlib import Path

import pytest
from flask_app import create_app

from app.database import init_db
from app.services.mapping import deterministic_mapping, normalize_header, resolve_alias
from app.services.type_inference import classify_value, infer_column_type


def test_normalize_header_is_case_insensitive() -> None:
    assert normalize_header("  Work Email ") == "work_email"
    assert normalize_header("Emp Code") == "emp_code"
    assert normalize_header("Employee_No") == "employee_no"


def test_alias_mapper_spec_examples() -> None:
    assert resolve_alias("emp_id") == "employee_id"
    assert resolve_alias("Emp Code") == "employee_id"
    assert resolve_alias("DOJ") == "joining_date"
    assert resolve_alias("Work Email") == "email"
    assert resolve_alias("Dept") == "department"
    assert resolve_alias("Office") == "city"
    assert resolve_alias("Employee Name") == "first_name"


def test_type_inference_spec_examples() -> None:
    assert classify_value("meet@example.com") == "email_like"
    assert classify_value("ravi@example.com") == "email_like"
    assert classify_value("12/05/2024") == "date_like"
    assert classify_value("18/08/2023") == "date_like"
    assert classify_value("42") == "number_like"
    assert classify_value("19.5") == "number_like"
    assert classify_value("yes") == "boolean_like"
    assert classify_value("no") == "boolean_like"

    kind, samples = infer_column_type(["meet@example.com", "ravi@example.com"])
    assert kind == "email_like"
    assert len(samples) == 2


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "migration.db"
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr("app.database.DATABASE_PATH", db_path)
    monkeypatch.setattr("app.services.ingestion.UPLOAD_DIR", upload_dir)
    init_db(db_path)
    return create_app().test_client()


def test_demo_files_obvious_deterministic_mappings(client) -> None:
    created = client.post("/api/migrations", json={"name": "Mapping analysis"})
    migration_id = created.get_json()["id"]
    client.post(f"/api/migrations/{migration_id}/demo-files")

    response = client.get(f"/api/migrations/{migration_id}/source-analysis")
    assert response.status_code == 200
    payload = response.get_json()
    by_key = {(item["source_file"], item["source_column"]): item for item in payload["columns"]}

    legacy_emp = by_key[("employees_legacy.csv", "Emp Code")]
    assert legacy_emp["proposed_target"] == "employee_id"
    assert legacy_emp["detected_source_type"] == "string_like"

    legacy_doj = by_key[("employees_legacy.csv", "DOJ")]
    assert legacy_doj["proposed_target"] == "joining_date"
    assert legacy_doj["detected_source_type"] == "date_like"

    legacy_mail = by_key[("employees_legacy.csv", "Mail")]
    assert legacy_mail["proposed_target"] == "email"
    assert legacy_mail["detected_source_type"] == "email_like"

    master_email = by_key[("employee_master.xlsx", "Work Email")]
    assert master_email["proposed_target"] == "email"
    assert master_email["detected_source_type"] == "email_like"

    master_office = by_key[("employee_master.xlsx", "Office")]
    assert master_office["proposed_target"] == "city"

    extra_no = by_key[("employees_extra.csv", "Employee_No")]
    assert extra_no["proposed_target"] == "employee_id"

    extra_date = by_key[("employees_extra.csv", "Date")]
    assert extra_date["proposed_target"] is None
    assert extra_date["detected_source_type"] == "date_like"

    mapping = deterministic_mapping("DOJ")
    assert mapping is not None
    assert mapping["target_field"] == "joining_date"
    assert mapping["confidence"] == 1.0
