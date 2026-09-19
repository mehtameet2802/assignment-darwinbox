from __future__ import annotations

from app.schema import EMPLOYEE_TARGET_SCHEMA

FIELD_TYPES = {field["name"]: field["type"] for field in EMPLOYEE_TARGET_SCHEMA["fields"]}


def target_field_type(target_field: str) -> str | None:
    return FIELD_TYPES.get(target_field)


def is_structurally_compatible(source_type: str, target_field: str) -> tuple[bool, str | None]:
    """Return (compatible, review_reason_if_incompatible)."""
    target_type = target_field_type(target_field)
    if target_type is None:
        return False, f"Unknown target field '{target_field}'."

    if source_type in {"unknown", "mixed"}:
        return True, None

    if target_type == "email":
        if source_type in {"email_like", "string_like"}:
            return True, None
        return (
            False,
            f"Structural incompatibility — source values are {source_type.replace('_', ' ')} "
            f"but target field is email.",
        )

    if target_type == "date":
        if source_type in {"date_like", "string_like"}:
            return True, None
        return (
            False,
            f"Structural incompatibility — source values are {source_type.replace('_', ' ')} "
            f"but target field is date.",
        )

    # string / identifier fields
    if target_type == "string":
        if source_type in {"string_like", "number_like"}:
            return True, None
        if source_type == "date_like":
            return (
                False,
                f"Structural incompatibility — source values are date-like but target field is {target_field}.",
            )
        if source_type == "email_like":
            return (
                False,
                f"Structural incompatibility — source values are email-like but target field is {target_field}.",
            )
        if source_type == "boolean_like":
            return (
                False,
                f"Structural incompatibility — source values are boolean-like but target field is {target_field}.",
            )
        return True, None

    return True, None
