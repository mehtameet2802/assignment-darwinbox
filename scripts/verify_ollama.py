#!/usr/bin/env python3
"""Smoke test: Ollama API up, configured model present, one live mapping call."""

from __future__ import annotations

import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import OLLAMA_BASE_URL, OLLAMA_MODEL
from app.services.llm_client import LLMClient


def main() -> int:
    base = OLLAMA_BASE_URL.rstrip("/")
    print(f"Ollama base URL: {base}")
    print(f"Configured model: {OLLAMA_MODEL}")

    try:
        tags = requests.get(f"{base}/api/tags", timeout=5).json()
    except requests.RequestException as exc:
        print(f"FAIL: Cannot reach Ollama ({exc}). Run: ollama serve")
        return 1

    model_names = [m.get("name", "") for m in tags.get("models", [])]
    if not any(name == OLLAMA_MODEL or name.startswith(f"{OLLAMA_MODEL}:") for name in model_names):
        print(f"FAIL: Model '{OLLAMA_MODEL}' not in ollama list: {model_names or '(empty)'}")
        print(f"Run: ollama pull {OLLAMA_MODEL}")
        return 1
    print("OK: Model is available")

    client = LLMClient(timeout_seconds=180.0)
    result = client.infer_mapping(
        "Date",
        "date_like",
        ["03/04/2024", "05/06/2024", "07/08/2024"],
    )
    if not result.get("success"):
        print(f"FAIL: Live mapping call did not succeed: {result.get('reason')}")
        return 1

    print(
        "OK: Live mapping —",
        f"target={result.get('target_field')}",
        f"confidence={result.get('confidence')}",
    )
    print("verify_ollama: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
