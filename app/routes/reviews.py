from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.errors import AppError
from app.services.analysis_pipeline import (
    build_analysis_snapshot,
    continue_after_date_resolution,
    continue_after_duplicate_resolution,
    continue_after_validation_resolution,
    run_analysis_pipeline,
)
from app.services.cleaning import clean_for_target_field
from app.services.date_escalations import (
    list_date_escalations,
    resolve_date_escalation,
    scan_date_columns,
)
from app.services.review_queue import get_unified_review_queue
from app.services.validation import (
    list_validation_escalations,
    resolve_validation_escalation,
    validate_migration,
)

reviews_bp = Blueprint("reviews", __name__)


def _error(exc: AppError):
    return jsonify({"error": exc.message}), exc.status_code


@reviews_bp.post("/api/migrations/<int:migration_id>/analysis/run")
def run_analysis(migration_id: int):
    try:
        return jsonify(run_analysis_pipeline(migration_id)), 201
    except AppError as exc:
        return _error(exc)


@reviews_bp.get("/api/migrations/<int:migration_id>/analysis/snapshot")
def analysis_snapshot(migration_id: int):
    try:
        return jsonify(build_analysis_snapshot(migration_id))
    except AppError as exc:
        return _error(exc)


@reviews_bp.post("/api/migrations/<int:migration_id>/analysis/continue")
def continue_analysis(migration_id: int):
    payload = request.get_json(silent=True) or {}
    after = payload.get("after") or "date"
    try:
        if after == "date":
            result = continue_after_date_resolution(migration_id)
        elif after == "duplicate":
            result = continue_after_duplicate_resolution(migration_id)
        elif after == "validation":
            result = continue_after_validation_resolution(migration_id)
        else:
            return jsonify({"error": "after must be date, duplicate, or validation."}), 400
        return jsonify(result), 201
    except AppError as exc:
        return _error(exc)


@reviews_bp.post("/api/clean/preview")
def clean_preview():
    payload = request.get_json(silent=True) or {}
    field = payload.get("target_field")
    raw = payload.get("raw_value")
    date_format = payload.get("date_format")
    if not field:
        return jsonify({"error": "target_field is required."}), 400
    result = clean_for_target_field(field, raw, date_format=date_format)
    return jsonify(
        {
            "target_field": field,
            "raw_value": raw,
            "cleaned_value": result.value,
            "ok": result.ok,
            "error": result.error,
            "date_format": date_format,
        }
    )


@reviews_bp.post("/api/migrations/<int:migration_id>/date-columns/scan")
def scan_dates(migration_id: int):
    return jsonify(scan_date_columns(migration_id)), 201


@reviews_bp.get("/api/migrations/<int:migration_id>/date-escalations")
def get_date_escalations(migration_id: int):
    return jsonify(list_date_escalations(migration_id))


@reviews_bp.post("/api/migrations/<int:migration_id>/validate")
def validate(migration_id: int):
    return jsonify(validate_migration(migration_id)), 201


@reviews_bp.get("/api/migrations/<int:migration_id>/validation-escalations")
def validation_escalations(migration_id: int):
    return jsonify(list_validation_escalations(migration_id))


@reviews_bp.patch("/api/migrations/<int:migration_id>/validation-escalations/<int:escalation_id>")
def patch_validation_escalation(migration_id: int, escalation_id: int):
    payload = request.get_json(silent=True) or {}
    return jsonify(
        resolve_validation_escalation(
            migration_id,
            escalation_id,
            action=payload.get("action"),
            field_name=payload.get("field_name"),
            value=payload.get("value"),
        )
    )


@reviews_bp.get("/api/migrations/<int:migration_id>/review-queue")
def review_queue(migration_id: int):
    return jsonify(get_unified_review_queue(migration_id))


@reviews_bp.patch("/api/migrations/<int:migration_id>/date-escalations/<int:escalation_id>")
def patch_date_escalation(migration_id: int, escalation_id: int):
    payload = request.get_json(silent=True) or {}
    return jsonify(
        resolve_date_escalation(migration_id, escalation_id, payload.get("chosen_format"))
    )
