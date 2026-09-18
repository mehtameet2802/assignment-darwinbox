from __future__ import annotations

from typing import Any

EMPLOYEE_TARGET_SCHEMA: dict[str, Any] = {
    "name": "Employee Target Schema",
    "entity": "employees",
    "fields": [
        {"name": "employee_id", "type": "string", "required": True},
        {"name": "first_name", "type": "string", "required": True},
        {"name": "last_name", "type": "string", "required": False},
        {"name": "email", "type": "email", "required": True},
        {"name": "joining_date", "type": "date", "required": False},
        {"name": "department", "type": "string", "required": False},
        {"name": "city", "type": "string", "required": False},
    ],
}


def target_schema_summary() -> dict[str, Any]:
    required = sum(1 for field in EMPLOYEE_TARGET_SCHEMA["fields"] if field["required"])
    optional = len(EMPLOYEE_TARGET_SCHEMA["fields"]) - required
    return {
        **EMPLOYEE_TARGET_SCHEMA,
        "required_count": required,
        "optional_count": optional,
    }
