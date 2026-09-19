from __future__ import annotations

import json
import sqlite3

from app.database import db_session, utcnow
from app.errors import AppError
from app.services.audit import AGENT, append_audit

CREATED = "CREATED"


def require_migration(migration_id: int, connection: sqlite3.Connection | None = None) -> sqlite3.Row:
    if connection is not None:
        row = connection.execute(
            "SELECT * FROM migrations WHERE id = ?",
            (migration_id,),
        ).fetchone()
        if row is None:
            raise AppError(f"Migration {migration_id} was not found.", 404)
        return row

    with db_session() as session:
        return require_migration(migration_id, session)


def _file_payload(source_file: sqlite3.Row) -> dict:
    return {
        "id": source_file["id"],
        "filename": source_file["original_filename"],
        "format": source_file["format"],
        "row_count": source_file["row_count"],
        "column_count": source_file["column_count"],
        "columns": json.loads(source_file["columns_json"]),
        "status": source_file["status"],
        "error_message": source_file["error_message"],
        "created_at": source_file["created_at"],
    }


def _serialize_migration(migration: sqlite3.Row, files: list[sqlite3.Row]) -> dict:
    file_payloads = [_file_payload(source_file) for source_file in files]
    keys = set(migration.keys())
    return {
        "id": migration["id"],
        "name": migration["name"],
        "entity": migration["entity"],
        "status": migration["status"],
        "auto_remove_exact_duplicates": bool(migration["auto_remove_exact_duplicates"]),
        "created_at": migration["created_at"],
        "completed_at": migration["completed_at"] if "completed_at" in keys else None,
        "files": file_payloads,
        "file_count": len(file_payloads),
        "total_source_rows": sum(item["row_count"] for item in file_payloads),
    }


def get_migration(migration_id: int) -> dict:
    with db_session() as connection:
        migration = require_migration(migration_id, connection)
        files = connection.execute(
            """
            SELECT id, original_filename, format, row_count, column_count,
                   columns_json, status, error_message, created_at
            FROM source_files
            WHERE migration_id = ?
            ORDER BY id
            """,
            (migration_id,),
        ).fetchall()
    return _serialize_migration(migration, files)


def list_migrations() -> list[dict]:
    with db_session() as connection:
        migrations = connection.execute(
            "SELECT * FROM migrations ORDER BY id DESC"
        ).fetchall()
        files = connection.execute(
            """
            SELECT id, migration_id, original_filename, format, row_count, column_count,
                   columns_json, status, error_message, created_at
            FROM source_files
            ORDER BY id
            """
        ).fetchall()
    files_by_migration: dict[int, list[sqlite3.Row]] = {}
    for source_file in files:
        files_by_migration.setdefault(source_file["migration_id"], []).append(source_file)
    return [
        _serialize_migration(migration, files_by_migration.get(migration["id"], []))
        for migration in migrations
    ]


def create_migration(name: str = "Employee Migration") -> dict:
    with db_session() as connection:
        cursor = connection.execute(
            """
            INSERT INTO migrations (name, entity, status, auto_remove_exact_duplicates, created_at)
            VALUES (?, 'employees', ?, 1, ?)
            """,
            (name, CREATED, utcnow()),
        )
        migration_id = cursor.lastrowid
        append_audit(connection, migration_id, AGENT, "migration created", name, "New migration session")
    return get_migration(migration_id)


def update_migration_options(migration_id: int, auto_remove_exact_duplicates: bool) -> dict:
    require_migration(migration_id)
    with db_session() as connection:
        connection.execute(
            "UPDATE migrations SET auto_remove_exact_duplicates = ? WHERE id = ?",
            (1 if auto_remove_exact_duplicates else 0, migration_id),
        )
    return get_migration(migration_id)
