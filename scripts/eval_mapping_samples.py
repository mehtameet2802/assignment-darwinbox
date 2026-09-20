#!/usr/bin/env python3
"""
Golden-column evaluation for the configured OLLAMA_MODEL.
Scores semantic mapping quality before deciding to upgrade the model.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import OLLAMA_MODEL
from app.services.llm_client import LLMClient

# Cases that should be handled by Ollama (not deterministic aliases).
GOLDEN_CASES: list[dict[str, Any]] = [
    {
        "id": "extra_date_column",
        "source_column": "Date",
        "source_type": "date_like",
        "samples": ["03/04/2024", "05/06/2024", "07/08/2024"],
        "acceptable_targets": ["joining_date"],
    },
    {
        "id": "legacy_employee_name",
        "source_column": "Employee Name",
        "source_type": "string_like",
        "samples": ["Meet Mehta", "Ravi Shah", "Anita Rao"],
        "acceptable_targets": ["first_name"],
    },
    {
        "id": "master_full_name",
        "source_column": "Full Name",
        "source_type": "string_like",
        "samples": ["Meet Mehta", "John Patel", "Priya Desai"],
        "acceptable_targets": ["first_name"],
    },
    {
        "id": "extra_name_header",
        "source_column": "Name",
        "source_type": "string_like",
        "samples": ["Amit Kumar", "Neha Joshi", "Demo Fail"],
        "acceptable_targets": ["first_name"],
    },
]

# MVP smoke-test gate: with four cases, 75% requires at least three to pass.
# One miss is tolerated because suggestions still go through human review; two or
# more misses indicate that the model or prompt is not dependable enough to lock in.
PASS_THRESHOLD = 0.75


def score_case(client: LLMClient, case: dict[str, Any]) -> dict[str, Any]:
    result = client.infer_mapping(
        case["source_column"],
        case["source_type"],
        case["samples"],
    )
    target = result.get("target_field")
    acceptable = case["acceptable_targets"]
    passed = result.get("success") and target in acceptable
    return {
        "id": case["id"],
        "passed": passed,
        "target_field": target,
        "confidence": result.get("confidence"),
        "reason": result.get("reason"),
        "method": result.get("method"),
    }


def main() -> int:
    print(f"Evaluating model: {OLLAMA_MODEL}")
    print(f"Golden cases: {len(GOLDEN_CASES)} (pass threshold: {PASS_THRESHOLD:.0%})\n")

    client = LLMClient(timeout_seconds=180.0)
    results = [score_case(client, case) for case in GOLDEN_CASES]

    for row in results:
        status = "PASS" if row["passed"] else "FAIL"
        print(
            f"  [{status}] {row['id']}: target={row['target_field']!r} "
            f"confidence={row['confidence']} — {row['reason']}"
        )

    passed_count = sum(1 for r in results if r["passed"])
    rate = passed_count / len(results) if results else 0.0
    print(f"\nScore: {passed_count}/{len(results)} ({rate:.0%})")

    if rate >= PASS_THRESHOLD:
        print(f"Recommendation: KEEP {OLLAMA_MODEL} for MVP (≥ {PASS_THRESHOLD:.0%}).")
        print("Re-run after Phase 5 with full demo files (checklist in docs/OLLAMA.md).")
        return 0

    print(f"Recommendation: INVESTIGATE — below {PASS_THRESHOLD:.0%} on golden columns.")
    print("Options: re-run verify_ollama.py, tune prompt, or trial llama3.1:8b on stronger hardware.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
