from __future__ import annotations

import json
from collections import defaultdict

from app.database import db_session, utcnow
from app.errors import AppError
from app.services.audit import AGENT, HUMAN, append_audit
from app.services.migrations import get_migration, require_migration
from app.status import EXACT_DEDUPED, EXCLUDED, NEEDS_REVIEW, RESOLVED, TRANSFORMED

DUPLICATE_CONFLICT = "DUPLICATE_CONFLICT"


def open_duplicate_conflict_record_ids(connection, migration_id: int) -> set[int]:
    """Normalized record ids still tied to an unresolved duplicate conflict."""
    rows = connection.execute(
        """
        SELECT members_json FROM duplicate_conflicts
        WHERE migration_id = ? AND status = ?
        """,
        (migration_id, NEEDS_REVIEW),
    ).fetchall()
    record_ids: set[int] = set()
    for row in rows:
        for member in json.loads(row["members_json"] or "[]"):
            record_ids.add(int(member["normalized_record_id"]))
    return record_ids


def _payload_key(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, default=str)


def _load_records(migration_id: int) -> list[dict]:
    with db_session() as connection:
        rows = connection.execute(
            """
            SELECT id, employee_id, payload_json, status
            FROM normalized_records
            WHERE migration_id = ? AND status IN (?, ?)
            ORDER BY id
            """,
            (migration_id, TRANSFORMED, NEEDS_REVIEW),
        ).fetchall()
    records = []
    for row in rows:
        records.append(
            {
                "id": row["id"],
                "employee_id": row["employee_id"],
                "payload": json.loads(row["payload_json"] or "{}"),
                "status": row["status"],
            }
        )
    return records


def _lineage_for_record(connection, record_id: int) -> list[dict]:
    rows = connection.execute(
        """
        SELECT source_row_id, source_file, source_row_number
        FROM record_lineage
        WHERE normalized_record_id = ?
        ORDER BY source_file, source_row_number
        """,
        (record_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def _attach_lineage(connection, target_record_id: int, source_row_id: int, source_file: str, row_number: int) -> None:
    connection.execute(
        """
        INSERT OR IGNORE INTO record_lineage (
            normalized_record_id, source_row_id, source_file, source_row_number
        )
        VALUES (?, ?, ?, ?)
        """,
        (target_record_id, source_row_id, source_file, row_number),
    )


def _merge_lineage(connection, target_record_id: int, from_record_id: int) -> None:
    for item in _lineage_for_record(connection, from_record_id):
        _attach_lineage(
            connection,
            target_record_id,
            item["source_row_id"],
            item["source_file"],
            item["source_row_number"],
        )


def _differing_fields(payloads: list[dict]) -> list[str]:
    keys = set()
    for payload in payloads:
        keys.update(payload.keys())
    differing = []
    for key in sorted(keys):
        values = {json.dumps(payload.get(key), sort_keys=True, default=str) for payload in payloads}
        if len(values) > 1:
            differing.append(key)
    return differing


def analyze_duplicates(migration_id: int) -> dict:
    migration = get_migration(migration_id)
    auto_remove = migration["auto_remove_exact_duplicates"]
    records = _load_records(migration_id)
    groups: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        if not record["employee_id"]:
            continue
        groups[record["employee_id"]].append(record)

    exact_groups = 0
    conflicts_created = 0
    now = utcnow()

    with db_session() as connection:
        connection.execute("DELETE FROM duplicate_conflicts WHERE migration_id = ?", (migration_id,))

        for employee_id, members in groups.items():
            if len(members) < 2:
                continue
            payload_keys = {_payload_key(m["payload"]) for m in members}
            if len(payload_keys) == 1:
                exact_groups += 1
                if not auto_remove:
                    continue
                keeper = members[0]
                for duplicate in members[1:]:
                    _merge_lineage(connection, keeper["id"], duplicate["id"])
                    connection.execute(
                        "UPDATE normalized_records SET status = ? WHERE id = ?",
                        (EXACT_DEDUPED, duplicate["id"]),
                    )
                connection.execute(
                    "UPDATE normalized_records SET status = 'TRANSFORMED' WHERE id = ?",
                    (keeper["id"],),
                )
                keeper_sources = _lineage_for_record(connection, keeper["id"])
                source_summary = ", ".join(
                    f"{s['source_file']} row {s['source_row_number']}" for s in keeper_sources
                )
                append_audit(
                    connection,
                    migration_id,
                    AGENT,
                    "exact duplicate deduplicated",
                    employee_id,
                    (
                        f"Collapsed {len(members) - 1} exact duplicate(s); keeper record "
                        f"{keeper['id']} retains lineage ({source_summary})."
                    ),
                )
                continue

            differing = _differing_fields([m["payload"] for m in members])
            rule = f'Same employee_id but normalized field "{differing[0]}" differs.' if differing else (
                "Same employee_id but normalized values differ."
            )
            member_payload = []
            for member in members:
                lineage = _lineage_for_record(connection, member["id"])
                member_payload.append(
                    {
                        "normalized_record_id": member["id"],
                        "payload": member["payload"],
                        "sources": lineage,
                    }
                )
            connection.execute(
                """
                INSERT INTO duplicate_conflicts (
                    migration_id, employee_id, status, rule_fired, review_reason,
                    members_json, differing_fields_json, final_payload_json, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?)
                """,
                (
                    migration_id,
                    employee_id,
                    NEEDS_REVIEW,
                    "DUPLICATE_CONFLICT",
                    rule,
                    json.dumps(member_payload),
                    json.dumps(differing),
                    now,
                ),
            )
            for member in members:
                connection.execute(
                    "UPDATE normalized_records SET status = ? WHERE id = ?",
                    (NEEDS_REVIEW, member["id"]),
                )
            append_audit(
                connection,
                migration_id,
                AGENT,
                "duplicate conflict escalated",
                employee_id,
                rule,
            )
            conflicts_created += 1

        connection.execute(
            "UPDATE migrations SET status = 'DUPLICATES_ANALYZED' WHERE id = ?",
            (migration_id,),
        )
        append_audit(
            connection,
            migration_id,
            AGENT,
            "duplicate analysis completed",
            "employees",
            (
                f"{exact_groups if auto_remove else 0} exact duplicate group(s) collapsed, "
                f"{conflicts_created} conflict(s) escalated."
            ),
        )

    return {
        "migration_id": migration_id,
        "auto_remove_exact_duplicates": auto_remove,
        "exact_duplicate_groups_collapsed": exact_groups if auto_remove else 0,
        "duplicate_conflicts": conflicts_created,
    }


def list_duplicate_conflicts_from_connection(connection, migration_id: int) -> dict:
    rows = connection.execute(
        """
        SELECT * FROM duplicate_conflicts
        WHERE migration_id = ?
        ORDER BY employee_id
        """,
        (migration_id,),
    ).fetchall()
    conflicts = []
    for row in rows:
        conflicts.append(
            {
                "id": row["id"],
                "employee_id": row["employee_id"],
                "status": row["status"],
                "rule_fired": row["rule_fired"],
                "review_reason": row["review_reason"],
                "members": json.loads(row["members_json"]),
                "differing_fields": json.loads(row["differing_fields_json"]),
                "final_payload": json.loads(row["final_payload_json"]) if row["final_payload_json"] else None,
            }
        )
    blocking = sum(1 for item in conflicts if item["status"] == NEEDS_REVIEW)
    return {
        "migration_id": migration_id,
        "conflict_count": len(conflicts),
        "blocking_count": blocking,
        "conflicts": conflicts,
    }


def list_duplicate_conflicts(migration_id: int) -> dict:
    with db_session() as connection:
        require_migration(migration_id, connection)
        return list_duplicate_conflicts_from_connection(connection, migration_id)


def get_record_lineage_summary(migration_id: int, employee_id: str) -> dict:
    with db_session() as connection:
        require_migration(migration_id, connection)
        row = connection.execute(
            """
            SELECT id, payload_json, status
            FROM normalized_records
            WHERE migration_id = ? AND employee_id = ? AND status NOT IN ('EXACT_DEDUPED', 'EXCLUDED')
            ORDER BY id
            LIMIT 1
            """,
            (migration_id, employee_id),
        ).fetchone()
        if row is None:
            raise AppError(f"No active record found for {employee_id}.", 404)
        lineage = _lineage_for_record(connection, row["id"])
    return {
        "employee_id": employee_id,
        "normalized_record_id": row["id"],
        "status": row["status"],
        "payload": json.loads(row["payload_json"] or "{}"),
        "sources": lineage,
    }


def resolve_duplicate_conflict(
    migration_id: int,
    conflict_id: int,
    *,
    action: str,
    final_payload: dict | None = None,
) -> dict:
    if action not in {"save", "exclude"}:
        raise AppError("action must be 'save' or 'exclude'.", 400)

    with db_session() as connection:
        conflict = connection.execute(
            """
            SELECT * FROM duplicate_conflicts
            WHERE id = ? AND migration_id = ?
            """,
            (conflict_id, migration_id),
        ).fetchone()
        if conflict is None:
            raise AppError("Duplicate conflict not found.", 404)

        members = json.loads(conflict["members_json"])
        member_ids = [m["normalized_record_id"] for m in members]

        if action == "exclude":
            for record_id in member_ids:
                connection.execute(
                    "UPDATE normalized_records SET status = ? WHERE id = ?",
                    (EXCLUDED, record_id),
                )
            connection.execute(
                """
                UPDATE duplicate_conflicts
                SET status = ?, final_payload_json = NULL, updated_at = ?
                WHERE id = ?
                """,
                (EXCLUDED, utcnow(), conflict_id),
            )
            append_audit(
                connection,
                migration_id,
                HUMAN,
                "record excluded",
                conflict["employee_id"],
                "Duplicate conflict excluded",
            )
            return list_duplicate_conflicts(migration_id)

        if not final_payload:
            raise AppError("final_payload is required when action is save.", 400)

        keeper_id = member_ids[0]
        for record_id in member_ids[1:]:
            _merge_lineage(connection, keeper_id, record_id)
            connection.execute(
                "UPDATE normalized_records SET status = ? WHERE id = ?",
                (EXACT_DEDUPED, record_id),
            )
        connection.execute(
            """
            UPDATE normalized_records
            SET payload_json = ?, status = ?, employee_id = ?
            WHERE id = ?
            """,
            (json.dumps(final_payload), TRANSFORMED, final_payload.get("employee_id"), keeper_id),
        )
        connection.execute(
            """
            UPDATE duplicate_conflicts
            SET status = ?, final_payload_json = ?, updated_at = ?
            WHERE id = ?
            """,
            (RESOLVED, json.dumps(final_payload), utcnow(), conflict_id),
        )
        append_audit(
            connection,
            migration_id,
            HUMAN,
            "human correction",
            conflict["employee_id"],
            f"Resolved duplicate conflict for {conflict['employee_id']}",
        )

    return list_duplicate_conflicts(migration_id)
