from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.services.ingestion import IngestionError
from app.services.source_analysis import analyze_migration

mappings_bp = Blueprint("mappings", __name__)


def _error(exc: IngestionError):
    return jsonify({"error": exc.message}), exc.status_code


@mappings_bp.get("/api/migrations/<int:migration_id>/source-analysis")
def source_analysis(migration_id: int):
    sample_limit = request.args.get("sample_limit", default=8, type=int)
    try:
        return jsonify(analyze_migration(migration_id, sample_limit=sample_limit))
    except IngestionError as exc:
        return _error(exc)
