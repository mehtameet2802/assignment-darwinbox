"""Deterministic Ollama stand-in for local E2E runs (set MOCK_OLLAMA_MAPPING=1)."""

from __future__ import annotations

from typing import Any


def mock_infer_mapping(
    source_column: str,
    source_type: str,
    sample_values: list[str],
) -> dict[str, Any]:
    base = {
        "source_column": source_column,
        "source_type": source_type,
        "target_field": None,
        "confidence": None,
        "reason": None,
        "alternatives": [],
        "method": "ollama",
        "success": False,
    }
    if source_column in {"Employee Name", "Full Name", "Name"}:
        return {
            **base,
            "target_field": "first_name",
            "confidence": 0.92,
            "reason": "name column (mock)",
            "success": True,
        }
    if source_column in {"DOJ", "Joining Date", "Date"}:
        return {
            **base,
            "target_field": "joining_date",
            "confidence": 0.9,
            "reason": "date column (mock)",
            "success": True,
        }
    base["method"] = "ollama_failed"
    base["reason"] = f"No mock mapping for column '{source_column}'."
    return base
