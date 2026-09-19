from __future__ import annotations

import sqlite3
from typing import Any

from app.database import db_session, utcnow
from app.services.ingestion import get_migration

AGENT = "AGENT"
SYSTEM = "SYSTEM"
HUMAN = "HUMAN"


def append_audit(
    connection: sqlite3.Connection,
    migration_id: int | None,
    actor: str,
    action: str,
    entity: str | None = None,
    reason: str | None = None,
) -> None:
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
    with db_session() as connection:
        append_audit(connection, migration_id, actor, action, entity, reason)


def list_audit_log(migration_id: int) -> dict[str, Any]:
    get_migration(migration_id)
    with db_session() as connection:
        rows = connection.execute(
            """
            SELECT timestamp, actor, action, entity, reason
            FROM audit_log
            WHERE migration_id = ?
            ORDER BY id ASC
            """,
            (migration_id,),
        ).fetchall()
    return {
        "migration_id": migration_id,
        "entries": [dict(row) for row in rows],
    }
