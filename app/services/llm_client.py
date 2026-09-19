from __future__ import annotations

import json
import re
from typing import Any

import requests

from app.config import MOCK_OLLAMA_MAPPING, OLLAMA_BASE_URL, OLLAMA_MODEL
from app.schema import EMPLOYEE_TARGET_SCHEMA

TARGET_FIELD_NAMES = [field["name"] for field in EMPLOYEE_TARGET_SCHEMA["fields"]]


class LLMClient:
    """Isolated Ollama client for semantic column mapping. No review-policy logic here."""

    def __init__(
        self,
        base_url: str = OLLAMA_BASE_URL,
        model: str = OLLAMA_MODEL,
        timeout_seconds: float = 120.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds

    def infer_mapping(
        self,
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
        if MOCK_OLLAMA_MAPPING:
            from app.testing.llm_mock import mock_infer_mapping

            return mock_infer_mapping(source_column, source_type, sample_values)
        try:
            raw = self._call_ollama(source_column, source_type, sample_values)
            parsed = parse_mapping_json(raw)
            if parsed is None:
                base["method"] = "ollama_failed"
                base["reason"] = "Ollama returned output that could not be parsed as mapping JSON."
                return base
            return normalize_mapping_result(parsed, base)
        except (requests.RequestException, ConnectionError, TimeoutError) as exc:
            base["method"] = "ollama_failed"
            base["reason"] = f"Ollama request failed: {exc}"
            return base
        except Exception as exc:  # noqa: BLE001 — must not crash migration on model errors
            base["method"] = "ollama_failed"
            base["reason"] = f"Ollama mapping error: {exc}"
            return base

    def _call_ollama(self, source_column: str, source_type: str, sample_values: list[str]) -> str:
        samples = ", ".join(repr(value) for value in sample_values[:8])
        target_list = ", ".join(TARGET_FIELD_NAMES)
        prompt = f"""You map HR employee export columns to a fixed target schema.

Target fields (use only these names): {target_list}

Source column: {source_column}
Detected value type: {source_type}
Sample values: {samples}

Respond with JSON only, no markdown, using this shape:
{{
  "source_column": "{source_column}",
  "source_type": "{source_type}",
  "target_field": "<one target field name or null if unsure>",
  "confidence": <number between 0 and 1>,
  "reason": "<short explanation>",
  "alternatives": [<other plausible target field names, or empty array>]
}}

Do not invent alternatives unless genuinely plausible. Use null target_field if unsure."""
        response = requests.post(
            f"{self.base_url}/api/generate",
            json={
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "format": "json",
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        return str(payload.get("response", ""))


def parse_mapping_json(raw: str) -> dict[str, Any] | None:
    text = raw.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            return None
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None


def normalize_mapping_result(parsed: dict[str, Any], base: dict[str, Any]) -> dict[str, Any]:
    target = parsed.get("target_field")
    if target is not None and target not in TARGET_FIELD_NAMES:
        base["method"] = "ollama_failed"
        base["reason"] = f"Model proposed invalid target field '{target}'."
        return base

    confidence = parsed.get("confidence")
    if confidence is not None:
        try:
            confidence = float(confidence)
            confidence = max(0.0, min(1.0, confidence))
        except (TypeError, ValueError):
            confidence = None

    alternatives = parsed.get("alternatives") or []
    if not isinstance(alternatives, list):
        alternatives = []
    alternatives = [alt for alt in alternatives if alt in TARGET_FIELD_NAMES and alt != target]

    base.update(
        {
            "target_field": target,
            "confidence": confidence,
            "reason": str(parsed.get("reason") or "").strip() or None,
            "alternatives": alternatives,
            "success": target is not None and confidence is not None,
            "method": "ollama" if target is not None else "ollama_failed",
        }
    )
    if not base["success"] and not base["reason"]:
        base["reason"] = "Model did not return a usable target field and confidence."
    return base
