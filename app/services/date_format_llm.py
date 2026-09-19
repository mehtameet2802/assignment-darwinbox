from __future__ import annotations

from typing import Any

from app.config import MOCK_OLLAMA_MAPPING
from app.services.dates import FORMAT_DMY, FORMAT_MDY
from app.services.llm_client import LLMClient, parse_mapping_json

AUTO_RESOLVE_CONFIDENCE = 0.85
ALLOWED_FORMATS = {FORMAT_DMY, FORMAT_MDY}


def suggest_date_format(
    source_column: str,
    source_file: str,
    sample_values: list[str],
    *,
    llm_client: LLMClient | None = None,
) -> dict[str, Any]:
    base = {
        "suggested_format": None,
        "confidence": None,
        "reason": None,
        "success": False,
        "method": "ollama",
    }
    if MOCK_OLLAMA_MAPPING:
        return _mock_suggest(source_column, source_file, sample_values)

    client = llm_client or LLMClient()
    _ = llm_client
    samples = ", ".join(repr(v) for v in sample_values[:8])
    prompt = f"""You help resolve ambiguous date column formats for HR data migration.

Source file: {source_file}
Source column: {source_column}
Sample values: {samples}

The column may be DD/MM/YYYY (day first) or MM/DD/YYYY (month first). Both can parse some samples.

Respond with JSON only:
{{
  "suggested_format": "DD/MM/YYYY" or "MM/DD/YYYY",
  "confidence": number between 0 and 1,
  "reason": "short explanation citing column name, file context, or sample patterns"
}}

Use confidence >= 0.85 only when evidence is strong (e.g. day > 12 in several samples, or column named DOJ with UK file). Use low confidence when truly ambiguous."""

    try:
        import requests

        from app.config import OLLAMA_BASE_URL, OLLAMA_MODEL

        response = requests.post(
            f"{OLLAMA_BASE_URL.rstrip('/')}/api/generate",
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False, "format": "json"},
            timeout=client.timeout_seconds,
        )
        response.raise_for_status()
        parsed = parse_mapping_json(str(response.json().get("response", "")))
        if parsed is None:
            base["reason"] = "Ollama returned unparseable date-format JSON."
            return base
        fmt = parsed.get("suggested_format")
        if fmt not in ALLOWED_FORMATS:
            base["reason"] = f"Ollama proposed invalid format '{fmt}'."
            return base
        confidence = parsed.get("confidence")
        try:
            confidence = max(0.0, min(1.0, float(confidence)))
        except (TypeError, ValueError):
            confidence = None
        base.update(
            {
                "suggested_format": fmt,
                "confidence": confidence,
                "reason": str(parsed.get("reason") or "").strip() or None,
                "success": confidence is not None,
            }
        )
        return base
    except Exception as exc:  # noqa: BLE001
        base["method"] = "ollama_failed"
        base["reason"] = f"Date format suggestion failed: {exc}"
        return base


def _mock_suggest(source_column: str, source_file: str, sample_values: list[str]) -> dict[str, Any]:
    # Demo extra file Date column — low confidence so human confirms in UI tests without Ollama.
    if source_file.endswith("employees_extra.csv") and source_column == "Date":
        return {
            "suggested_format": FORMAT_DMY,
            "confidence": 0.62,
            "reason": "Mock: samples are ambiguous; slight lean to DD/MM from file name context.",
            "success": True,
            "method": "ollama_mock",
        }
    return {
        "suggested_format": None,
        "confidence": None,
        "reason": "Mock: no suggestion for this column.",
        "success": False,
        "method": "ollama_mock",
    }
