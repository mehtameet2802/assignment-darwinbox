from __future__ import annotations

import streamlit as st

from ui.api import api_get


def render_migration_picker() -> None:
    listing = api_get("/api/migrations").json().get("migrations", [])
    labels = {f"MIG-{item['id']} • {item['name']} ({item['file_count']} files)": item["id"] for item in listing}
    selected = st.selectbox("Active migration", ["(none)"] + list(labels.keys()), key="active_migration_pick")
    if selected != "(none)":
        st.session_state.migration_id = labels[selected]


def current_migration() -> dict | None:
    if not st.session_state.migration_id:
        return None
    response = api_get(f"/api/migrations/{st.session_state.migration_id}")
    if response.status_code != 200:
        st.session_state.migration_id = None
        return None
    return response.json()


def require_migration(empty_message: str) -> dict | None:
    render_migration_picker()
    migration = current_migration()
    if migration is None:
        st.info(empty_message)
        return None
    return migration
