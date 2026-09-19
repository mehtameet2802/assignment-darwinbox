from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.schema import EMPLOYEE_TARGET_SCHEMA

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
WHITESPACE_RE = re.compile(r"\s+")

NULL_LITERALS = {
    "",
    " ",
    "NULL",
    "null",
    "N/A",
    "NA",
    "None",
    "none",
    "-",
}

BOOLEAN_TRUE = {"true", "yes", "y", "1"}
BOOLEAN_FALSE = {"false", "no", "n", "0"}


@dataclass
class CleanResult:
    value: Any
    ok: bool
    error: str | None = None


def is_null_sentinel(raw: Any) -> bool:
    if raw is None:
        return True
    if not isinstance(raw, str):
        return False
    if raw in NULL_LITERALS:
        return True
    stripped = raw.strip()
    if stripped == "" or stripped in NULL_LITERALS:
        return True
    upper = stripped.upper()
    return upper in {"NULL", "N/A", "NA", "NONE", "-"}


def normalize_null(raw: Any) -> Any | None:
    if is_null_sentinel(raw):
        return None
    return raw


def clean_string(raw: Any) -> CleanResult:
    if is_null_sentinel(raw):
        return CleanResult(value=None, ok=True)
    text = str(raw)
    cleaned = WHITESPACE_RE.sub(" ", text.strip())
    return CleanResult(value=cleaned, ok=True)


def clean_email(raw: Any) -> CleanResult:
    if is_null_sentinel(raw):
        return CleanResult(value=None, ok=True)
    text = str(raw).strip().lower()
    if not EMAIL_RE.match(text):
        return CleanResult(value=text, ok=False, error="Invalid email format.")
    return CleanResult(value=text, ok=True)


def clean_employee_id(raw: Any) -> CleanResult:
    if is_null_sentinel(raw):
        return CleanResult(value=None, ok=True)
    text = str(raw).strip()
    return CleanResult(value=text, ok=True)


def clean_number(raw: Any) -> CleanResult:
    if is_null_sentinel(raw):
        return CleanResult(value=None, ok=True)
    text = str(raw).strip()
    if any(symbol in text for symbol in ("₹", "€", "$", "£")):
        return CleanResult(value=None, ok=False, error="Unsupported currency or non-numeric text.")
    if re.search(r"[a-zA-Z]", text):
        return CleanResult(value=None, ok=False, error="Non-numeric text cannot be parsed as number.")
    if re.match(r"^\d{1,3}(\.\d{3})+,\d+$", text):
        return CleanResult(value=None, ok=False, error="Ambiguous numeric format.")
    normalized = text.replace(",", "")
    try:
        if "." in normalized:
            number = float(normalized)
            if number.is_integer():
                return CleanResult(value=int(number), ok=True)
            return CleanResult(value=number, ok=True)
        return CleanResult(value=int(normalized), ok=True)
    except ValueError:
        return CleanResult(value=None, ok=False, error="Could not parse number.")


def clean_boolean(raw: Any) -> CleanResult:
    if is_null_sentinel(raw):
        return CleanResult(value=None, ok=True)
    token = str(raw).strip().lower()
    if token in BOOLEAN_TRUE:
        return CleanResult(value=True, ok=True)
    if token in BOOLEAN_FALSE:
        return CleanResult(value=False, ok=True)
    return CleanResult(value=None, ok=False, error="Value is not a recognized boolean.")


def target_field_type(field_name: str) -> str | None:
    for field in EMPLOYEE_TARGET_SCHEMA["fields"]:
        if field["name"] == field_name:
            return field["type"]
    return None


def clean_for_target_field(field_name: str, raw: Any) -> CleanResult:
    """Apply Tier-1 cleaning for a target schema field (dates handled in Phase 7)."""
    if field_name == "employee_id":
        return clean_employee_id(raw)
    field_type = target_field_type(field_name)
    if field_type == "email":
        return clean_email(raw)
    if field_type == "string":
        return clean_string(raw)
    if field_type == "date":
        if is_null_sentinel(raw):
            return CleanResult(value=None, ok=True)
        return clean_string(raw)
    if field_type == "number":
        return clean_number(raw)
    if field_type == "boolean":
        return clean_boolean(raw)
    return clean_string(raw)
