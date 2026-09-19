from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.services.mapping_store import generate_mappings, list_mappings, update_mapping
from app.services.source_analysis import analyze_migration

mappings_bp = Blueprint("mappings", __name__)


@mappings_bp.get("/api/migrations/<int:migration_id>/source-analysis")
def source_analysis(migration_id: int):
    sample_limit = request.args.get("sample_limit", default=8, type=int)
    include_semantic = request.args.get("include_semantic", default="false").lower() in {
        "1",
        "true",
        "yes",
    }
    return jsonify(
        analyze_migration(
            migration_id,
            sample_limit=sample_limit,
            include_semantic=include_semantic,
        )
    )


@mappings_bp.post("/api/migrations/<int:migration_id>/mappings/generate")
def generate(migration_id: int):
    include_semantic = request.args.get("include_semantic", default="true").lower() in {
        "1",
        "true",
        "yes",
    }
    return jsonify(generate_mappings(migration_id, include_semantic=include_semantic)), 201


@mappings_bp.get("/api/migrations/<int:migration_id>/mappings")
def get_mappings(migration_id: int):
    return jsonify(list_mappings(migration_id))


@mappings_bp.patch("/api/migrations/<int:migration_id>/mappings/<int:mapping_id>")
def patch_mapping(migration_id: int, mapping_id: int):
    payload = request.get_json(silent=True) or {}
    return jsonify(
        update_mapping(
            migration_id,
            mapping_id,
            action=payload.get("action"),
            target_field=payload.get("target_field"),
        )
    )
