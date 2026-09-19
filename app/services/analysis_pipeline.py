from __future__ import annotations

from app.database import db_session
from app.errors import AppError
from app.services.audit import AGENT, append_audit
from app.services.date_escalations import list_date_escalations, scan_date_columns
from app.services.duplicates import analyze_duplicates, list_duplicate_conflicts
from app.services.migrations import get_migration
from app.services.transform import transform_migration
from app.services.validation import list_validation_escalations, validate_migration


def _blocking_counts(migration_id: int) -> dict:
    dates = list_date_escalations(migration_id)
    dupes = list_duplicate_conflicts(migration_id)
    validation = list_validation_escalations(migration_id)
    return {
        "date_blocking": dates["blocking_count"],
        "duplicate_blocking": dupes["blocking_count"],
        "validation_blocking": validation["blocking_count"],
        "dates": dates,
        "duplicates": dupes,
        "validation": validation,
    }


def build_analysis_snapshot(migration_id: int) -> dict:
    get_migration(migration_id)
    blocks = _blocking_counts(migration_id)
    total_review = (
        blocks["date_blocking"] + blocks["duplicate_blocking"] + blocks["validation_blocking"]
    )
    return {
        "migration_id": migration_id,
        "status": "complete" if total_review == 0 else "needs_review",
        "issues_requiring_review": total_review,
        "date_blocking": blocks["date_blocking"],
        "duplicate_blocking": blocks["duplicate_blocking"],
        "validation_blocking": blocks["validation_blocking"],
        "dates": blocks["dates"],
        "duplicates": blocks["duplicates"],
        "validation": blocks["validation"],
        "last_run": None,
    }


def _run_processing_stages(migration_id: int) -> dict:
    transform_result = transform_migration(migration_id)
    duplicate_result = analyze_duplicates(migration_id)
    validation_result = validate_migration(migration_id)
    snapshot = build_analysis_snapshot(migration_id)
    snapshot["last_run"] = {
        "phase": "full_processing",
        "records_transformed": transform_result.get("records_created", 0),
        "exact_duplicate_groups_handled": duplicate_result.get(
            "exact_duplicate_groups_collapsed", 0
        ),
        "duplicate_conflicts_created": duplicate_result.get("duplicate_conflicts", 0),
        "records_validated": validation_result.get("records_validated", 0),
        "ready_to_push": validation_result.get("ready_to_push", 0),
        "validation_escalations": validation_result.get("validation_escalations", 0),
    }
    with db_session() as connection:
        append_audit(
            connection,
            migration_id,
            AGENT,
            "analysis pipeline completed",
            "employees",
            (
                f"Transformed {snapshot['last_run']['records_transformed']} record(s); "
                f"{snapshot['last_run']['ready_to_push']} ready; "
                f"{snapshot['last_run']['validation_escalations']} validation escalation(s)."
            ),
        )
    return snapshot


def run_analysis_pipeline(migration_id: int) -> dict:
    """Scan dates, then transform → duplicates → validate when dates are clear."""
    get_migration(migration_id)
    try:
        scan_date_columns(migration_id)
    except AppError as exc:
        if exc.status_code == 400 and "No mapped joining_date" in exc.message:
            return _run_processing_stages(migration_id)
        raise

    blocks = _blocking_counts(migration_id)
    if blocks["date_blocking"] > 0:
        snapshot = build_analysis_snapshot(migration_id)
        snapshot["last_run"] = {
            "phase": "blocked_dates",
            "message": "Date format must be confirmed before processing continues.",
        }
        snapshot["status"] = "needs_review"
        return snapshot

    return _run_processing_stages(migration_id)


def continue_after_date_resolution(migration_id: int) -> dict:
    blocks = _blocking_counts(migration_id)
    if blocks["date_blocking"] > 0:
        snapshot = build_analysis_snapshot(migration_id)
        snapshot["last_run"] = {"phase": "blocked_dates"}
        snapshot["status"] = "needs_review"
        return snapshot
    return _run_processing_stages(migration_id)


def continue_after_duplicate_resolution(migration_id: int) -> dict:
    validate_migration(migration_id)
    snapshot = build_analysis_snapshot(migration_id)
    snapshot["last_run"] = {"phase": "revalidated_after_duplicate"}
    return snapshot


def continue_after_validation_resolution(migration_id: int) -> dict:
    validate_migration(migration_id)
    snapshot = build_analysis_snapshot(migration_id)
    snapshot["last_run"] = {"phase": "revalidated_after_validation"}
    return snapshot
