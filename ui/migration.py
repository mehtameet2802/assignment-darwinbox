from __future__ import annotations

import streamlit as st

from ui.api import api_get
from ui.migration_picker import render_bound_migration_selectbox

__all__ = [
    "analysis_review_complete",
    "clear_pipeline_migration_if_completed",
    "current_migration",
    "is_pipeline_active",
    "list_all_migrations",
    "list_migrations_mappings_ready",
    "list_migrations_push_ready",
    "list_migrations_with_staged_files",
    "list_pipeline_migrations",
    "mappings_review_complete",
    "push_phase_complete",
    "require_migration",
    "require_migration_mappings_ready",
    "require_migration_push_ready",
    "require_migration_staged_files",
    "render_audit_migration_picker",
    "render_migration_picker",
    "render_migration_picker_mappings_ready",
    "render_migration_picker_push_ready",
    "render_migration_picker_staged_files",
]


def _fetch_migrations() -> list[dict]:
    return api_get("/api/migrations").json().get("migrations", [])


def is_pipeline_active(item: dict) -> bool:
    """Migrations closed via **Complete migration** are read-only in the audit log only."""
    return not item.get("completed_at")


def list_pipeline_migrations() -> list[dict]:
    return [item for item in _fetch_migrations() if is_pipeline_active(item)]


def list_all_migrations() -> list[dict]:
    return _fetch_migrations()


def clear_pipeline_migration_if_completed() -> None:
    """Drop session selection when the user finished the push workflow."""
    migration_id = st.session_state.get("migration_id")
    if not migration_id:
        return
    response = api_get(f"/api/migrations/{migration_id}")
    if response.status_code != 200:
        st.session_state.migration_id = None
        return
    if response.json().get("completed_at"):
        st.session_state.migration_id = None


def mappings_review_complete(migration_id: int) -> bool:
    response = api_get(f"/api/migrations/{migration_id}/mappings")
    if response.status_code != 200:
        return False
    payload = response.json()
    if payload.get("mapping_count", 0) == 0:
        return False
    return payload.get("blocking_review_count", 0) == 0


def list_migrations_mappings_ready() -> list[dict]:
    return [
        item
        for item in list_pipeline_migrations()
        if mappings_review_complete(item["id"])
    ]


def list_migrations_with_staged_files() -> list[dict]:
    return [
        item
        for item in list_pipeline_migrations()
        if item.get("file_count", 0) > 0
    ]


def analysis_review_complete(migration_id: int) -> bool:
    if not mappings_review_complete(migration_id):
        return False
    response = api_get(f"/api/migrations/{migration_id}/analysis/snapshot")
    if response.status_code != 200:
        return False
    payload = response.json()
    return payload.get("issues_requiring_review", 1) == 0


def push_phase_complete(migration_id: int) -> bool:
    """Mappings and analysis complete with no open review items."""
    if not analysis_review_complete(migration_id):
        return False
    response = api_get(f"/api/migrations/{migration_id}")
    if response.status_code != 200:
        return False
    status = response.json().get("status", "")
    return status in {"VALIDATED", "PUSHED"}


def list_migrations_push_ready() -> list[dict]:
    """Analysis complete, push workflow not yet closed (still on Push page)."""
    return [
        item
        for item in list_pipeline_migrations()
        if push_phase_complete(item["id"])
    ]


def _migration_label(item: dict) -> str:
    return f"MIG-{item['id']} • {item['name']} ({item['file_count']} files)"


def _audit_migration_label(item: dict) -> str:
    label = _migration_label(item)
    if item.get("completed_at"):
        return f"{label} • finished"
    return label


def _render_migration_picker_from_list(
    items: list[dict],
    *,
    label: str,
    session_key: str,
    empty_hint: str | None = None,
) -> None:
    if empty_hint and not items:
        st.caption(empty_hint)
    labels = {_migration_label(item): item["id"] for item in items}
    option_labels = ["(none)"] + list(labels.keys())
    render_bound_migration_selectbox(
        label=label,
        session_key=session_key,
        option_labels=option_labels,
        label_to_id=labels,
    )


def render_audit_migration_picker() -> None:
    """All migrations (including finished) for audit history."""
    listing = list_all_migrations()
    if not listing:
        st.caption("No migrations yet.")
        return
    labels = {_audit_migration_label(item): item["id"] for item in listing}
    option_labels = ["(none)"] + list(labels.keys())
    render_bound_migration_selectbox(
        label="Migration",
        session_key="audit_migration_pick",
        option_labels=option_labels,
        label_to_id=labels,
    )


def current_migration() -> dict | None:
    if not st.session_state.migration_id:
        return None
    response = api_get(f"/api/migrations/{st.session_state.migration_id}")
    if response.status_code != 200:
        st.session_state.migration_id = None
        return None
    return response.json()


def require_migration(empty_message: str) -> dict | None:
    render_audit_migration_picker()
    migration = current_migration()
    if migration is None:
        st.info(empty_message)
        return None
    return migration


def render_migration_picker_staged_files() -> None:
    clear_pipeline_migration_if_completed()
    staged = list_migrations_with_staged_files()
    if st.session_state.get("migration_id"):
        current = current_migration()
        if current is None or current.get("file_count", 0) == 0:
            st.session_state.migration_id = None
    _render_migration_picker_from_list(
        staged,
        label="Active migration (files staged)",
        session_key="active_migration_pick_staged",
        empty_hint="No migrations with staged files yet. Create one on **New migration**.",
    )


def render_migration_picker_mappings_ready() -> None:
    clear_pipeline_migration_if_completed()
    ready = list_migrations_mappings_ready()
    if st.session_state.get("migration_id") and not mappings_review_complete(st.session_state.migration_id):
        st.session_state.migration_id = None

    _render_migration_picker_from_list(
        ready,
        label="Active migration (mappings complete)",
        session_key="active_migration_pick_mappings_ready",
        empty_hint="No migrations have finished **Mappings & review** yet.",
    )


def render_migration_picker_push_ready() -> None:
    clear_pipeline_migration_if_completed()
    ready = list_migrations_push_ready()
    if st.session_state.get("migration_id") and not push_phase_complete(st.session_state.migration_id):
        st.session_state.migration_id = None
    _render_migration_picker_from_list(
        ready,
        label="Active migration (ready to push)",
        session_key="active_migration_pick_push_ready",
        empty_hint="No migrations have completed **Analysis & review** with zero open issues.",
    )


def require_migration_mappings_ready(empty_message: str) -> dict | None:
    ready = list_migrations_mappings_ready()
    if not ready:
        st.info(
            "No migrations have finished **Mappings & review** yet. "
            "Complete column mapping there, then return to this page."
        )
        return None

    render_migration_picker_mappings_ready()
    migration = current_migration()
    if migration is None:
        st.info(empty_message)
        return None
    if not mappings_review_complete(migration["id"]):
        st.warning("This migration still has mapping reviews pending. Finish them on **Mappings & review**.")
        st.session_state.migration_id = None
        return None
    return migration


def require_migration_staged_files(empty_message: str) -> dict | None:
    staged = list_migrations_with_staged_files()
    if not staged:
        st.info("No migrations have staged source files yet. Start on **New migration**.")
        return None

    render_migration_picker_staged_files()
    migration = current_migration()
    if migration is None:
        st.info(empty_message)
        return None
    if migration.get("file_count", 0) == 0:
        st.warning("Stage source files on **New migration** before mapping.")
        st.session_state.migration_id = None
        return None
    return migration


def require_migration_push_ready(empty_message: str) -> dict | None:
    ready = list_migrations_push_ready()
    if not ready:
        st.info(
            "No migrations are ready to push. Finish **Analysis & review** "
            "(run analysis and resolve any date, duplicate, or validation items)."
        )
        return None

    render_migration_picker_push_ready()
    migration = current_migration()
    if migration is None:
        st.info(empty_message)
        return None
    if not push_phase_complete(migration["id"]):
        st.warning(
            "This migration is not ready to push. Complete analysis with no items left in **Needs review**."
        )
        st.session_state.migration_id = None
        return None
    if migration.get("completed_at"):
        st.info("This migration is finished. View it under **Audit log**.")
        st.session_state.migration_id = None
        return None
    return migration


# Back-compat alias (audit is the only consumer of a full listing picker).
render_migration_picker = render_audit_migration_picker
