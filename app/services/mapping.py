from __future__ import annotations

import re

from app.schema import EMPLOYEE_TARGET_SCHEMA

TARGET_FIELDS = {field["name"] for field in EMPLOYEE_TARGET_SCHEMA["fields"]}

# Normalized header token -> target field (case-insensitive after normalize_header).
ALIAS_TO_TARGET: dict[str, str] = {
    "employee_id": "employee_id",
    "emp_id": "employee_id",
    "employee_code": "employee_id",
    "emp_code": "employee_id",
    "employee_no": "employee_id",
    "email": "email",
    "mail": "email",
    "work_email": "email",
    "doj": "joining_date",
    "joining_date": "joining_date",
    "dept": "department",
    "department": "department",
    "city": "city",
    "office": "city",
    "employee_name": "first_name",
    "full_name": "first_name",
    "name": "first_name",
}


def normalize_header(name: str) -> str:
    text = name.strip().lower()
    text = re.sub(r"[\s\-]+", "_", text)
    text = re.sub(r"[^a-z0-9_]", "", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text


def resolve_alias(source_column: str) -> str | None:
    key = normalize_header(source_column)
    if key in ALIAS_TO_TARGET:
        return ALIAS_TO_TARGET[key]
    if key in TARGET_FIELDS:
        return key
    return None


def deterministic_mapping(source_column: str) -> dict | None:
    target = resolve_alias(source_column)
    if target is None:
        return None
    return {
        "source_column": source_column,
        "target_field": target,
        "method": "deterministic_alias",
        "confidence": 1.0,
        "reason": f"Header '{source_column}' matches known alias for '{target}'.",
        "alternatives": [],
    }
