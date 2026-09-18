from __future__ import annotations

import json
import uuid
from pathlib import Path

import pandas as pd

from app.config import DEMO_DIR, UPLOAD_DIR
from app.database import db_session, utcnow

ALLOWED_EXTENSIONS = {".csv", ".xlsx"}
HEADER_ROW_NUMBER = 1
FIRST_DATA_ROW_NUMBER = 2


class IngestionError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _extension(filename: str) -> str:
    return Path(filename).suffix.lower()


def _format_label(filename: str) -> str:
    ext = _extension(filename)
    return ext.lstrip(".").upper()


def _safe_name(filename: str) -> str:
    return Path(filename).name.replace("..", "")


def _read_table(path: Path, filename: str) -> pd.DataFrame:
    ext = _extension(filename)
    if ext == ".csv":
        return pd.read_csv(path, dtype=str, keep_default_na=False)
    if ext == ".xlsx":
        return pd.read_excel(path, dtype=str, keep_default_na=False, engine="openpyxl")
    raise IngestionError(
        f"Unsupported file format '{ext or filename}'. Upload .csv or .xlsx only."
    )


def create_migration(name: str = "Employee Migration") -> dict:
    with db_session() as connection:
        cursor = connection.execute(
            """
            INSERT INTO migrations (name, entity, status, auto_remove_exact_duplicates, created_at)
            VALUES (?, 'employees', 'CREATED', 1, ?)
            """,
            (name, utcnow()),
        )
        migration_id = cursor.lastrowid
    return get_migration(migration_id)


def list_migrations() -> list[dict]:
    with db_session() as connection:
        rows = connection.execute(
            "SELECT * FROM migrations ORDER BY id DESC"
        ).fetchall()
    return [get_migration(row["id"]) for row in rows]


def get_migration(migration_id: int) -> dict:
    with db_session() as connection:
        migration = connection.execute(
            "SELECT * FROM migrations WHERE id = ?",
            (migration_id,),
        ).fetchone()
        if migration is None:
            raise IngestionError(f"Migration {migration_id} was not found.", 404)
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
    file_payloads = []
    total_rows = 0
    for source_file in files:
        columns = json.loads(source_file["columns_json"])
        row_count = source_file["row_count"]
        total_rows += row_count
        file_payloads.append(
            {
                "id": source_file["id"],
                "filename": source_file["original_filename"],
                "format": source_file["format"],
                "row_count": row_count,
                "column_count": source_file["column_count"],
                "columns": columns,
                "status": source_file["status"],
                "error_message": source_file["error_message"],
                "created_at": source_file["created_at"],
            }
        )
    return {
        "id": migration["id"],
        "name": migration["name"],
        "entity": migration["entity"],
        "status": migration["status"],
        "auto_remove_exact_duplicates": bool(migration["auto_remove_exact_duplicates"]),
        "created_at": migration["created_at"],
        "files": file_payloads,
        "file_count": len(file_payloads),
        "total_source_rows": total_rows,
    }


def update_migration_options(migration_id: int, auto_remove_exact_duplicates: bool) -> dict:
    get_migration(migration_id)
    with db_session() as connection:
        connection.execute(
            "UPDATE migrations SET auto_remove_exact_duplicates = ? WHERE id = ?",
            (1 if auto_remove_exact_duplicates else 0, migration_id),
        )
    return get_migration(migration_id)


def ingest_bytes(migration_id: int, filename: str, content: bytes) -> dict:
    get_migration(migration_id)
    original = _safe_name(filename)
    ext = _extension(original)
    if ext not in ALLOWED_EXTENSIONS:
        raise IngestionError(
            f"Unsupported file format '{ext or original}'. Upload .csv or .xlsx only."
        )

    stored_name = f"{migration_id}_{uuid.uuid4().hex}_{original}"
    stored_path = UPLOAD_DIR / stored_name
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    stored_path.write_bytes(content)

    format_label = _format_label(original)
    created_at = utcnow()
    try:
        frame = _read_table(stored_path, original)
        columns = [str(column) for column in frame.columns]
        with db_session() as connection:
            cursor = connection.execute(
                """
                INSERT INTO source_files (
                    migration_id, original_filename, stored_path, format,
                    row_count, column_count, columns_json, status, error_message, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 'READY', NULL, ?)
                """,
                (
                    migration_id,
                    original,
                    str(stored_path),
                    format_label,
                    len(frame),
                    len(columns),
                    json.dumps(columns),
                    created_at,
                ),
            )
            source_file_id = cursor.lastrowid
            for offset, record in enumerate(frame.to_dict(orient="records")):
                source_row_number = FIRST_DATA_ROW_NUMBER + offset
                connection.execute(
                    """
                    INSERT INTO source_rows (
                        source_file_id, source_file, source_row_number, payload_json
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        source_file_id,
                        original,
                        source_row_number,
                        json.dumps(record, ensure_ascii=True),
                    ),
                )
            connection.execute(
                "UPDATE migrations SET status = 'FILES_STAGED' WHERE id = ?",
                (migration_id,),
            )
        return {
            "id": source_file_id,
            "filename": original,
            "format": format_label,
            "row_count": len(frame),
            "column_count": len(columns),
            "columns": columns,
            "status": "READY",
            "error_message": None,
        }
    except IngestionError:
        stored_path.unlink(missing_ok=True)
        raise
    except Exception as exc:
        with db_session() as connection:
            connection.execute(
                """
                INSERT INTO source_files (
                    migration_id, original_filename, stored_path, format,
                    row_count, column_count, columns_json, status, error_message, created_at
                )
                VALUES (?, ?, ?, ?, 0, 0, '[]', 'FAILED', ?, ?)
                """,
                (migration_id, original, str(stored_path), format_label, str(exc), created_at),
            )
        raise IngestionError(
            f"Could not read '{original}'. The file was rejected and not skipped silently.",
            400,
        ) from exc


def ingest_path(migration_id: int, path: Path) -> dict:
    return ingest_bytes(migration_id, path.name, path.read_bytes())


def load_demo_files(migration_id: int) -> dict:
    demo_files = [
        DEMO_DIR / "employees_legacy.csv",
        DEMO_DIR / "employee_master.xlsx",
        DEMO_DIR / "employees_extra.csv",
    ]
    missing = [str(path.name) for path in demo_files if not path.exists()]
    if missing:
        raise IngestionError(
            f"Demo files missing: {', '.join(missing)}. Generate employee_master.xlsx first.",
            500,
        )
    ingested = []
    existing = {item["filename"] for item in get_migration(migration_id)["files"]}
    for path in demo_files:
        if path.name in existing:
            continue
        ingested.append(ingest_path(migration_id, path))
    migration = get_migration(migration_id)
    migration["ingested"] = ingested
    return migration


def preview_source_file(migration_id: int, source_file_id: int, limit: int = 20) -> dict:
    with db_session() as connection:
        source_file = connection.execute(
            """
            SELECT * FROM source_files
            WHERE id = ? AND migration_id = ?
            """,
            (source_file_id, migration_id),
        ).fetchone()
        if source_file is None:
            raise IngestionError("Source file was not found for this migration.", 404)
        rows = connection.execute(
            """
            SELECT source_file, source_row_number, payload_json
            FROM source_rows
            WHERE source_file_id = ?
            ORDER BY source_row_number
            LIMIT ?
            """,
            (source_file_id, limit),
        ).fetchall()
        total = connection.execute(
            "SELECT COUNT(*) AS n FROM source_rows WHERE source_file_id = ?",
            (source_file_id,),
        ).fetchone()["n"]
    preview_rows = []
    for row in rows:
        payload = json.loads(row["payload_json"])
        preview_rows.append(
            {
                "source_file": row["source_file"],
                "source_row_number": row["source_row_number"],
                **payload,
            }
        )
    return {
        "id": source_file["id"],
        "filename": source_file["original_filename"],
        "format": source_file["format"],
        "status": source_file["status"],
        "error_message": source_file["error_message"],
        "columns": json.loads(source_file["columns_json"]),
        "row_count": source_file["row_count"],
        "header_row_number": HEADER_ROW_NUMBER,
        "preview_limit": limit,
        "preview_row_count": len(preview_rows),
        "total_source_rows": total,
        "rows": preview_rows,
    }


def delete_source_file(migration_id: int, source_file_id: int) -> dict:
    with db_session() as connection:
        source_file = connection.execute(
            """
            SELECT * FROM source_files
            WHERE id = ? AND migration_id = ?
            """,
            (source_file_id, migration_id),
        ).fetchone()
        if source_file is None:
            raise IngestionError("Source file was not found for this migration.", 404)
        stored_path = Path(source_file["stored_path"])
        connection.execute("DELETE FROM source_rows WHERE source_file_id = ?", (source_file_id,))
        connection.execute("DELETE FROM source_files WHERE id = ?", (source_file_id,))
        remaining = connection.execute(
            "SELECT COUNT(*) AS n FROM source_files WHERE migration_id = ?",
            (migration_id,),
        ).fetchone()["n"]
        if remaining == 0:
            connection.execute(
                "UPDATE migrations SET status = 'CREATED' WHERE id = ?",
                (migration_id,),
            )
    stored_path.unlink(missing_ok=True)
    return get_migration(migration_id)


def attach_lineage(migration_id: int, source_row_ids: list[int], employee_id: str | None = None) -> dict:
    """Store multiple source-row references on one normalized record."""
    if not source_row_ids:
        raise IngestionError("At least one source row is required for lineage.")
    with db_session() as connection:
        cursor = connection.execute(
            """
            INSERT INTO normalized_records (migration_id, employee_id, payload_json, status, created_at)
            VALUES (?, ?, NULL, 'PENDING_TRANSFORM', ?)
            """,
            (migration_id, employee_id, utcnow()),
        )
        normalized_id = cursor.lastrowid
        references = []
        for source_row_id in source_row_ids:
            row = connection.execute(
                """
                SELECT sr.id, sr.source_file, sr.source_row_number
                FROM source_rows sr
                JOIN source_files sf ON sf.id = sr.source_file_id
                WHERE sr.id = ? AND sf.migration_id = ?
                """,
                (source_row_id, migration_id),
            ).fetchone()
            if row is None:
                raise IngestionError(f"Source row {source_row_id} was not found in this migration.", 404)
            connection.execute(
                """
                INSERT INTO record_lineage (
                    normalized_record_id, source_row_id, source_file, source_row_number
                )
                VALUES (?, ?, ?, ?)
                """,
                (normalized_id, row["id"], row["source_file"], row["source_row_number"]),
            )
            references.append(
                {
                    "source_file": row["source_file"],
                    "source_row_number": row["source_row_number"],
                    "source_row_id": row["id"],
                }
            )
    return {
        "normalized_record_id": normalized_id,
        "employee_id": employee_id,
        "sources": references,
    }


def find_source_rows(migration_id: int, filename: str, source_row_number: int) -> list[dict]:
    with db_session() as connection:
        rows = connection.execute(
            """
            SELECT sr.id, sr.source_file, sr.source_row_number, sr.payload_json
            FROM source_rows sr
            JOIN source_files sf ON sf.id = sr.source_file_id
            WHERE sf.migration_id = ? AND sr.source_file = ? AND sr.source_row_number = ?
            """,
            (migration_id, filename, source_row_number),
        ).fetchall()
    return [
        {
            "id": row["id"],
            "source_file": row["source_file"],
            "source_row_number": row["source_row_number"],
            "payload": json.loads(row["payload_json"]),
        }
        for row in rows
    ]
