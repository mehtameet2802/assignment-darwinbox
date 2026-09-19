from __future__ import annotations

import streamlit as st


def migration_selectbox_index(
    option_labels: list[str],
    label_to_id: dict[str, int],
    migration_id: int | None = None,
    *,
    include_none: bool = True,
) -> int:
    """Index for st.selectbox so session migration_id matches the visible selection."""
    if migration_id is None:
        migration_id = st.session_state.get("migration_id")
    if migration_id is None:
        return 0
    for idx, label in enumerate(option_labels):
        if include_none and idx == 0 and label == "(none)":
            continue
        if label_to_id.get(label) == migration_id:
            return idx
    return 0
