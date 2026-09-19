from __future__ import annotations

from app.services.compatibility import is_structurally_compatible
from app.status import NEEDS_REVIEW

CONFIDENCE_THRESHOLD = 0.85

AUTO_APPROVED = "AUTO_APPROVED"
IGNORED = "IGNORED"
MANUALLY_APPROVED = "MANUALLY_APPROVED"
UNMAPPED = "UNMAPPED"

RULE_CONFIDENCE = "confidence_below_threshold"
RULE_STRUCTURAL = "structural_incompatibility"
RULE_NO_MAPPING = "mapping_not_produced_safely"
RULE_HUMAN_RESOLVED = "human_resolved"
RULE_TARGET_FIELD_COLLISION = "TARGET_FIELD_COLLISION"


def evaluate_mapping_policy(
    *,
    source_type: str,
    proposed_target: str | None,
    confidence: float | None,
    ignored: bool = False,
    manual_target: str | None = None,
) -> dict:
    if ignored:
        return {
            "status": IGNORED,
            "final_target": None,
            "review_required": False,
            "review_rule_fired": None,
            "review_reason": None,
        }

    if manual_target:
        compatible, structural_reason = is_structurally_compatible(source_type, manual_target)
        if not compatible:
            return {
                "status": NEEDS_REVIEW,
                "final_target": manual_target,
                "review_required": True,
                "review_rule_fired": RULE_STRUCTURAL,
                "review_reason": structural_reason,
            }
        return {
            "status": MANUALLY_APPROVED,
            "final_target": manual_target,
            "review_required": False,
            "review_rule_fired": RULE_HUMAN_RESOLVED,
            "review_reason": "Human selected the target mapping.",
        }

    if not proposed_target:
        return {
            "status": UNMAPPED if confidence is None else NEEDS_REVIEW,
            "final_target": None,
            "review_required": True,
            "review_rule_fired": RULE_NO_MAPPING,
            "review_reason": "No safe automatic mapping could be produced for this source column.",
        }

    compatible, structural_reason = is_structurally_compatible(source_type, proposed_target)
    if not compatible:
        return {
            "status": NEEDS_REVIEW,
            "final_target": proposed_target,
            "review_required": True,
            "review_rule_fired": RULE_STRUCTURAL,
            "review_reason": structural_reason,
        }

    if confidence is None or confidence < CONFIDENCE_THRESHOLD:
        conf_text = f"{confidence:.2f}" if confidence is not None else "n/a"
        return {
            "status": NEEDS_REVIEW,
            "final_target": proposed_target,
            "review_required": True,
            "review_rule_fired": RULE_CONFIDENCE,
            "review_reason": f"Confidence {conf_text} < required threshold {CONFIDENCE_THRESHOLD:.2f}",
        }

    return {
        "status": AUTO_APPROVED,
        "final_target": proposed_target,
        "review_required": False,
        "review_rule_fired": None,
        "review_reason": None,
    }
