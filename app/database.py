from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from app.config import DATABASE_PATH, UPLOAD_DIR

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS app_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS migrations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    entity TEXT NOT NULL DEFAULT 'employees',
    status TEXT NOT NULL DEFAULT 'CREATED',
    auto_remove_exact_duplicates INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    migration_id INTEGER NOT NULL,
    original_filename TEXT NOT NULL,
    stored_path TEXT NOT NULL,
    format TEXT NOT NULL,
    row_count INTEGER NOT NULL DEFAULT 0,
    column_count INTEGER NOT NULL DEFAULT 0,
    columns_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL,
    error_message TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (migration_id) REFERENCES migrations(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS source_rows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file_id INTEGER NOT NULL,
    source_file TEXT NOT NULL,
    source_row_number INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    FOREIGN KEY (source_file_id) REFERENCES source_files(id) ON DELETE CASCADE,
    UNIQUE (source_file_id, source_row_number)
);

CREATE TABLE IF NOT EXISTS normalized_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    migration_id INTEGER NOT NULL,
    employee_id TEXT,
    payload_json TEXT,
    status TEXT NOT NULL DEFAULT 'PENDING_TRANSFORM',
    created_at TEXT NOT NULL,
    FOREIGN KEY (migration_id) REFERENCES migrations(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS record_lineage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    normalized_record_id INTEGER NOT NULL,
    source_row_id INTEGER NOT NULL,
    source_file TEXT NOT NULL,
    source_row_number INTEGER NOT NULL,
    FOREIGN KEY (normalized_record_id) REFERENCES normalized_records(id) ON DELETE CASCADE,
    FOREIGN KEY (source_row_id) REFERENCES source_rows(id) ON DELETE CASCADE,
    UNIQUE (normalized_record_id, source_row_id)
);

CREATE TABLE IF NOT EXISTS column_mappings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    migration_id INTEGER NOT NULL,
    source_file_id INTEGER NOT NULL,
    source_file TEXT NOT NULL,
    source_column TEXT NOT NULL,
    detected_source_type TEXT NOT NULL,
    sample_values_json TEXT NOT NULL,
    proposed_target TEXT,
    final_target TEXT,
    mapping_method TEXT,
    confidence REAL,
    ai_reason TEXT,
    alternatives_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL,
    review_required INTEGER NOT NULL DEFAULT 0,
    review_rule_fired TEXT,
    review_reason TEXT,
    ignored INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (migration_id) REFERENCES migrations(id) ON DELETE CASCADE,
    FOREIGN KEY (source_file_id) REFERENCES source_files(id) ON DELETE CASCADE,
    UNIQUE (migration_id, source_file_id, source_column)
);

CREATE TABLE IF NOT EXISTS date_column_escalations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    migration_id INTEGER NOT NULL,
    source_file_id INTEGER NOT NULL,
    source_file TEXT NOT NULL,
    source_column TEXT NOT NULL,
    issue_type TEXT NOT NULL,
    status TEXT NOT NULL,
    chosen_format TEXT,
    sample_values_json TEXT NOT NULL,
    review_reason TEXT,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (migration_id) REFERENCES migrations(id) ON DELETE CASCADE,
    FOREIGN KEY (source_file_id) REFERENCES source_files(id) ON DELETE CASCADE,
    UNIQUE (migration_id, source_file_id, source_column)
);

CREATE TABLE IF NOT EXISTS duplicate_conflicts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    migration_id INTEGER NOT NULL,
    employee_id TEXT NOT NULL,
    status TEXT NOT NULL,
    rule_fired TEXT NOT NULL,
    review_reason TEXT NOT NULL,
    members_json TEXT NOT NULL,
    differing_fields_json TEXT NOT NULL,
    final_payload_json TEXT,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (migration_id) REFERENCES migrations(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS validation_escalations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    migration_id INTEGER NOT NULL,
    normalized_record_id INTEGER NOT NULL,
    employee_id TEXT,
    issue_type TEXT NOT NULL,
    field_name TEXT,
    rule_fired TEXT NOT NULL,
    review_reason TEXT NOT NULL,
    current_payload_json TEXT NOT NULL,
    status TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (migration_id) REFERENCES migrations(id) ON DELETE CASCADE,
    FOREIGN KEY (normalized_record_id) REFERENCES normalized_records(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS mock_target_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id TEXT NOT NULL,
    employee_id TEXT NOT NULL UNIQUE,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS mock_target_e009_state (
    employee_id TEXT PRIMARY KEY,
    push_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS push_batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    migration_id INTEGER NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    rolled_back_at TEXT,
    FOREIGN KEY (migration_id) REFERENCES migrations(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS push_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    push_batch_id INTEGER NOT NULL,
    migration_id INTEGER NOT NULL,
    normalized_record_id INTEGER NOT NULL,
    employee_id TEXT NOT NULL,
    attempt_number INTEGER NOT NULL,
    endpoint TEXT NOT NULL,
    method TEXT NOT NULL,
    http_status INTEGER,
    result TEXT NOT NULL,
    error_message TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (push_batch_id) REFERENCES push_batches(id) ON DELETE CASCADE,
    FOREIGN KEY (migration_id) REFERENCES migrations(id) ON DELETE CASCADE,
    FOREIGN KEY (normalized_record_id) REFERENCES normalized_records(id) ON DELETE CASCADE
);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def ensure_directories() -> None:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or DATABASE_PATH
    ensure_directories()
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


@contextmanager
def db_session(db_path: Path | None = None) -> Generator[sqlite3.Connection, None, None]:
    connection = get_connection(db_path)
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_db(db_path: Path | None = None) -> None:
    with db_session(db_path) as connection:
        connection.executescript(SCHEMA_SQL)
        connection.execute(
            "INSERT OR IGNORE INTO app_meta (key, value) VALUES (?, ?)",
            ("initialized", "true"),
        )


def ping_db(db_path: Path | None = None) -> dict[str, str]:
    with db_session(db_path) as connection:
        row = connection.execute("SELECT sqlite_version() AS version").fetchone()
        meta = connection.execute(
            "SELECT value FROM app_meta WHERE key = ?",
            ("initialized",),
        ).fetchone()
    return {
        "sqlite_version": row["version"] if row else "unknown",
        "initialized": meta["value"] if meta else "false",
    }
