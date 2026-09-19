from __future__ import annotations

from app.services.date_escalations import list_date_escalations
from app.services.duplicates import list_duplicate_conflicts
from app.services.ingestion import get_migration
from app.services.mapping_store import list_mappings
from app.services.validation import list_validation_escalations


def get_unified_review_queue(migration_id: int) -> dict:
    get_migration(migration_id)
    mappings = list_mappings(migration_id)
    dates = list_date_escalations(migration_id)
    duplicates = list_duplicate_conflicts(migration_id)
    validation = list_validation_escalations(migration_id)

    items: list[dict] = []

    for mapping in mappings["mappings"]:
        if mapping["review_required"]:
            items.append(
                {
                    "category": "MAPPING_AMBIGUITY",
                    "issue_type": "MAPPING_AMBIGUITY",
                    "rule_fired": mapping["review_rule_fired"],
                    "review_reason": mapping["review_reason"],
                    "source_file": mapping["source_file"],
                    "source_column": mapping["source_column"],
                    "entity_id": f"mapping:{mapping['id']}",
                    "blocking": True,
                }
            )

    for escalation in dates["escalations"]:
        if escalation["status"] == "NEEDS_REVIEW":
            items.append(
                {
                    "category": "DATE_FORMAT_AMBIGUITY",
                    "issue_type": escalation["issue_type"],
                    "rule_fired": escalation["issue_type"],
                    "review_reason": escalation["review_reason"],
                    "source_file": escalation["source_file"],
                    "source_column": escalation["source_column"],
                    "entity_id": f"date:{escalation['id']}",
                    "blocking": True,
                }
            )

    for conflict in duplicates["conflicts"]:
        if conflict["status"] == "NEEDS_REVIEW":
            items.append(
                {
                    "category": "DUPLICATE_CONFLICT",
                    "issue_type": conflict["rule_fired"],
                    "rule_fired": conflict["rule_fired"],
                    "review_reason": conflict["review_reason"],
                    "employee_id": conflict["employee_id"],
                    "entity_id": f"duplicate:{conflict['id']}",
                    "blocking": True,
                }
            )

    for escalation in validation["escalations"]:
        if escalation["status"] == "NEEDS_REVIEW":
            items.append(
                {
                    "category": escalation["issue_type"],
                    "issue_type": escalation["issue_type"],
                    "rule_fired": escalation["rule_fired"],
                    "review_reason": escalation["review_reason"],
                    "employee_id": escalation["employee_id"],
                    "field_name": escalation["field_name"],
                    "entity_id": f"validation:{escalation['id']}",
                    "sources": escalation.get("sources", []),
                    "blocking": True,
                }
            )

    blocking_count = len(items)
    return {
        "migration_id": migration_id,
        "blocking_count": blocking_count,
        "mapping_blocking": mappings["blocking_review_count"],
        "date_blocking": dates["blocking_count"],
        "duplicate_blocking": duplicates["blocking_count"],
        "validation_blocking": validation["blocking_count"],
        "items": items,
    }
