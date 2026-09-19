from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.services.duplicates import (
    analyze_duplicates,
    get_record_lineage_summary,
    list_duplicate_conflicts,
    resolve_duplicate_conflict,
)
from app.services.transform import transform_migration

duplicates_bp = Blueprint("duplicates", __name__)


@duplicates_bp.post("/api/migrations/<int:migration_id>/transform")
def transform(migration_id: int):
    return jsonify(transform_migration(migration_id)), 201


@duplicates_bp.post("/api/migrations/<int:migration_id>/duplicates/analyze")
def analyze(migration_id: int):
    return jsonify(analyze_duplicates(migration_id)), 201


@duplicates_bp.get("/api/migrations/<int:migration_id>/duplicate-conflicts")
def conflicts(migration_id: int):
    return jsonify(list_duplicate_conflicts(migration_id))


@duplicates_bp.get("/api/migrations/<int:migration_id>/records/<employee_id>/lineage")
def lineage(migration_id: int, employee_id: str):
    return jsonify(get_record_lineage_summary(migration_id, employee_id))


@duplicates_bp.patch("/api/migrations/<int:migration_id>/duplicate-conflicts/<int:conflict_id>")
def resolve(migration_id: int, conflict_id: int):
    payload = request.get_json(silent=True) or {}
    return jsonify(
        resolve_duplicate_conflict(
            migration_id,
            conflict_id,
            action=payload.get("action"),
            final_payload=payload.get("final_payload"),
        )
    )
