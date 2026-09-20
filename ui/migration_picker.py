from __future__ import annotations

import streamlit as st

PICKER_SESSION_KEY_SUFFIX = "_pick"


def _session_state():
    return st.session_state


def migration_picker_session_keys() -> list[str]:
    session = _session_state()
    return [key for key in session if key.endswith(PICKER_SESSION_KEY_SUFFIX) or "_pick" in key]


def reset_migration_picker_widgets() -> None:
    """Drop selectbox widget state so pickers re-bind after programmatic migration changes."""
    session = _session_state()
    for key in migration_picker_session_keys():
        del session[key]


def _label_for_migration_id(migration_id: int, label_to_id: dict[str, int]) -> str | None:
    for label, mid in label_to_id.items():
        if mid == migration_id:
            return label
    return None


def sync_migration_selectbox(
    session_key: str,
    option_labels: list[str],
    label_to_id: dict[str, int],
) -> None:
    """Initialize selectbox widget from st.session_state.migration_id (first render only)."""
    session = _session_state()
    migration_id = session.get("migration_id")
    selected_label = "(none)"
    if migration_id is not None:
        for label, mid in label_to_id.items():
            if mid == migration_id:
                selected_label = label
                break
    if selected_label not in option_labels:
        selected_label = "(none)"
    session[session_key] = selected_label


def apply_migration_from_picker(session_key: str, label_to_id: dict[str, int]) -> int | None:
    """Read the active picker widget and update st.session_state.migration_id."""
    session = _session_state()
    choice = session.get(session_key, "(none)")
    if choice != "(none)" and choice not in label_to_id:
        # Stale widget value (e.g. listing changed); do not clear the active migration.
        return session.get("migration_id")
    new_id = label_to_id.get(choice) if choice != "(none)" else None
    previous = session.get("migration_id")
    if new_id != previous:
        if previous is not None:
            _clear_migration_page_cache(previous)
        if new_id is not None:
            _clear_migration_page_cache(new_id)
    session.migration_id = new_id
    return new_id


def _clear_migration_page_cache(migration_id: int) -> None:
    session = _session_state()
    for prefix in ("mappings_", "analysis_snapshot_", "analysis_phases_", "audit_offset_"):
        session.pop(f"{prefix}{migration_id}", None)


def render_bound_migration_selectbox(
    *,
    label: str,
    session_key: str,
    option_labels: list[str],
    label_to_id: dict[str, int],
) -> None:
    """Selectbox that drives st.session_state.migration_id without clobbering user switches."""
    session = _session_state()
    if session_key not in session:
        sync_migration_selectbox(session_key, option_labels, label_to_id)
    else:
        current = session.get(session_key)
        if current is not None and current not in label_to_id:
            migration_id = session.get("migration_id")
            canonical = (
                _label_for_migration_id(migration_id, label_to_id) if migration_id is not None else None
            )
            if canonical:
                # Listing labels often embed file_count; refresh after staging uploads.
                session[session_key] = canonical

    st.selectbox(label, option_labels, key=session_key)
    apply_migration_from_picker(session_key, label_to_id)


def migration_selectbox_index(
    option_labels: list[str],
    label_to_id: dict[str, int],
    migration_id: int | None = None,
    *,
    include_none: bool = True,
) -> int:
    """Index for st.selectbox so session migration_id matches the visible selection."""
    if migration_id is None:
        migration_id = _session_state().get("migration_id")
    if migration_id is None:
        return 0
    for idx, label in enumerate(option_labels):
        if include_none and idx == 0 and label == "(none)":
            continue
        if label_to_id.get(label) == migration_id:
            return idx
    return 0
