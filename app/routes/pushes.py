from __future__ import annotations

from flask import Blueprint, jsonify

from app.services.ingestion import IngestionError
from app.services.push import list_push_attempts, push_migration, retry_failed_push, rollback_latest_push

pushes_bp = Blueprint("pushes", __name__)


def _error(exc: IngestionError):
    return jsonify({"error": exc.message}), exc.status_code


@pushes_bp.post("/api/migrations/<int:migration_id>/push")
def push(migration_id: int):
    try:
        return jsonify(push_migration(migration_id)), 201
    except IngestionError as exc:
        return _error(exc)


@pushes_bp.post("/api/migrations/<int:migration_id>/push/retry")
def retry_push(migration_id: int):
    try:
        return jsonify(retry_failed_push(migration_id)), 201
    except IngestionError as exc:
        return _error(exc)


@pushes_bp.post("/api/migrations/<int:migration_id>/push/rollback")
def rollback_push(migration_id: int):
    try:
        return jsonify(rollback_latest_push(migration_id)), 200
    except IngestionError as exc:
        return _error(exc)


@pushes_bp.get("/api/migrations/<int:migration_id>/push/attempts")
def push_attempts(migration_id: int):
    try:
        return jsonify(list_push_attempts(migration_id))
    except IngestionError as exc:
        return _error(exc)
