from __future__ import annotations

from flask import Blueprint, jsonify

from app.errors import AppError
from app.services.push import (
    complete_push_workflow,
    get_push_overview,
    list_push_attempts,
    push_migration,
    retry_failed_push,
    rollback_latest_push,
)

pushes_bp = Blueprint("pushes", __name__)


@pushes_bp.post("/api/migrations/<int:migration_id>/push")
def push(migration_id: int):
    return jsonify(push_migration(migration_id)), 201


@pushes_bp.post("/api/migrations/<int:migration_id>/push/retry")
def retry_push(migration_id: int):
    return jsonify(retry_failed_push(migration_id)), 201


@pushes_bp.post("/api/migrations/<int:migration_id>/push/rollback")
def rollback_push(migration_id: int):
    return jsonify(rollback_latest_push(migration_id)), 200


@pushes_bp.get("/api/migrations/<int:migration_id>/push/attempts")
def push_attempts(migration_id: int):
    return jsonify(list_push_attempts(migration_id))


@pushes_bp.get("/api/migrations/<int:migration_id>/push/overview")
def push_overview(migration_id: int):
    return jsonify(get_push_overview(migration_id))


@pushes_bp.post("/api/migrations/<int:migration_id>/push/complete")
def complete_push(migration_id: int):
    try:
        return jsonify(complete_push_workflow(migration_id)), 200
    except AppError as exc:
        return jsonify({"error": exc.message}), exc.status_code
