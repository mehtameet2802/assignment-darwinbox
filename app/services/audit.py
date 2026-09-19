from __future__ import annotations

import sqlite3
from typing import Any

from app.database import db_session, utcnow
from app.errors import AppError

AGENT = "AGENT"
SYSTEM = "SYSTEM"
HUMAN = "HUMAN"

DEFAULT_AUDIT_LOG_LIMIT = 25
MAX_AUDIT_LOG_LIMIT = 500


def append_audit(
    connection: sqlite3.Connection,
    migration_id: int | None,
    actor: str,
    action: str,
    entity: str | None = None,
    reason: str | None = None,
) -> None:
    """Insert one audit row on an open database connection."""
    connection.execute(
        """
        INSERT INTO audit_log (migration_id, timestamp, actor, action, entity, reason)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (migration_id, utcnow(), actor, action, entity, reason),
    )


def log_audit(
    migration_id: int | None,
    actor: str,
    action: str,
    entity: str | None = None,
    reason: str | None = None,
) -> None:
    """Persist an audit event in its own transaction."""
    with db_session() as connection:
        append_audit(connection, migration_id, actor, action, entity, reason)


def list_audit_log(
    migration_id: int,
    limit: int = DEFAULT_AUDIT_LOG_LIMIT,
    offset: int = 0,
) -> dict[str, Any]:
    """Return paginated audit events for a migration, newest first."""
    bounded_limit = min(max(limit, 1), MAX_AUDIT_LOG_LIMIT)
    bounded_offset = max(offset, 0)
    with db_session() as connection:
        exists = connection.execute(
            "SELECT id FROM migrations WHERE id = ?",
            (migration_id,),
        ).fetchone()
        if exists is None:
            raise AppError(f"Migration {migration_id} was not found.", 404)
        total = connection.execute(
            "SELECT COUNT(*) AS n FROM audit_log WHERE migration_id = ?",
            (migration_id,),
        ).fetchone()["n"]
        rows = connection.execute(
            """
            SELECT timestamp, actor, action, entity, reason
            FROM audit_log
            WHERE migration_id = ?
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            (migration_id, bounded_limit, bounded_offset),
        ).fetchall()
    return {
        "migration_id": migration_id,
        "limit": bounded_limit,
        "offset": bounded_offset,
        "total": total,
        "entries": [dict(row) for row in rows],
    }
