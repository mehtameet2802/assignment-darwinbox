from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.services.ingestion import (
    IngestionError,
    attach_lineage,
    create_migration,
    delete_source_file,
    get_migration,
    ingest_bytes,
    list_migrations,
    load_demo_files,
    preview_source_file,
    update_migration_options,
)

migrations_bp = Blueprint("migrations", __name__)


def _error(exc: IngestionError):
    return jsonify({"error": exc.message}), exc.status_code


@migrations_bp.post("/api/migrations")
def create():
    payload = request.get_json(silent=True) or {}
    name = payload.get("name") or "Employee Migration"
    return jsonify(create_migration(name)), 201


@migrations_bp.get("/api/migrations")
def list_all():
    return jsonify({"migrations": list_migrations()})


@migrations_bp.get("/api/migrations/<int:migration_id>")
def detail(migration_id: int):
    try:
        return jsonify(get_migration(migration_id))
    except IngestionError as exc:
        return _error(exc)


@migrations_bp.patch("/api/migrations/<int:migration_id>")
def patch(migration_id: int):
    payload = request.get_json(silent=True) or {}
    try:
        if "auto_remove_exact_duplicates" in payload:
            return jsonify(
                update_migration_options(
                    migration_id,
                    bool(payload["auto_remove_exact_duplicates"]),
                )
            )
        return jsonify(get_migration(migration_id))
    except IngestionError as exc:
        return _error(exc)


@migrations_bp.post("/api/migrations/<int:migration_id>/files")
def upload(migration_id: int):
    uploads = request.files.getlist("files") or request.files.getlist("file")
    if not uploads:
        return jsonify({"error": "No files were uploaded."}), 400
    ingested = []
    try:
        for upload in uploads:
            filename = upload.filename or ""
            ingested.append(ingest_bytes(migration_id, filename, upload.read()))
        migration = get_migration(migration_id)
        migration["ingested"] = ingested
        return jsonify(migration), 201
    except IngestionError as exc:
        return _error(exc)


@migrations_bp.post("/api/migrations/<int:migration_id>/demo-files")
def demo_files(migration_id: int):
    try:
        return jsonify(load_demo_files(migration_id)), 201
    except IngestionError as exc:
        return _error(exc)


@migrations_bp.get("/api/migrations/<int:migration_id>/files/<int:source_file_id>/preview")
def preview(migration_id: int, source_file_id: int):
    limit = request.args.get("limit", default=20, type=int)
    try:
        return jsonify(preview_source_file(migration_id, source_file_id, limit=limit))
    except IngestionError as exc:
        return _error(exc)


@migrations_bp.delete("/api/migrations/<int:migration_id>/files/<int:source_file_id>")
def delete_file(migration_id: int, source_file_id: int):
    try:
        return jsonify(delete_source_file(migration_id, source_file_id))
    except IngestionError as exc:
        return _error(exc)


@migrations_bp.post("/api/migrations/<int:migration_id>/lineage")
def lineage(migration_id: int):
    payload = request.get_json(silent=True) or {}
    source_row_ids = payload.get("source_row_ids") or []
    employee_id = payload.get("employee_id")
    try:
        return jsonify(attach_lineage(migration_id, source_row_ids, employee_id)), 201
    except IngestionError as exc:
        return _error(exc)
