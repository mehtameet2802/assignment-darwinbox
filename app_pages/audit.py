from __future__ import annotations

import streamlit as st

from ui.api import api_get, show_api_error
from ui.migration import require_migration
from ui.navigation import render_pipeline_stepper

AUDIT_PAGE_SIZE = 25

render_pipeline_stepper(4)

st.caption(
    "Immutable history for **every** migration (in progress or **finished**). "
    "Finished migrations appear here with a **finished** tag; they are hidden from pipeline "
    "**Active migration** dropdowns on earlier steps."
)

migration = require_migration("Select a migration to view its audit log.")
if migration is None:
    st.stop()

st.subheader(f"MIG-{migration['id']} • {migration['name']}")
if migration.get("completed_at"):
    st.caption(f"Push workflow: **finished** ({migration['completed_at']})")
else:
    st.caption(f"Push workflow: **not closed** · migration status **{migration.get('status', '—')}**")

offset_key = f"audit_offset_{migration['id']}"
if offset_key not in st.session_state:
    st.session_state[offset_key] = 0

offset = int(st.session_state[offset_key])
audit = api_get(
    f"/api/migrations/{migration['id']}/audit-log"
    f"?limit={AUDIT_PAGE_SIZE}&offset={offset}"
)
if audit.status_code != 200:
    show_api_error(audit, "Could not load audit log.")
    st.stop()

payload = audit.json()
total = int(payload.get("total") or 0)
entries = payload.get("entries") or []

if total and offset >= total:
    st.session_state[offset_key] = max(0, ((total - 1) // AUDIT_PAGE_SIZE) * AUDIT_PAGE_SIZE)
    st.rerun()

if not entries and total == 0:
    st.caption("No audit entries yet.")
else:
    nav_left, nav_center, nav_right = st.columns([1, 2, 1])
    with nav_left:
        if st.button(
            "Previous",
            key=f"audit_prev_{migration['id']}",
            disabled=offset <= 0,
        ):
            st.session_state[offset_key] = max(0, offset - AUDIT_PAGE_SIZE)
            st.rerun()
    with nav_center:
        if total:
            start = offset + 1
            end = min(offset + len(entries), total)
            st.caption(f"Showing {start}–{end} of {total} entries")
    with nav_right:
        if st.button(
            "Next",
            key=f"audit_next_{migration['id']}",
            disabled=offset + AUDIT_PAGE_SIZE >= total,
        ):
            st.session_state[offset_key] = offset + AUDIT_PAGE_SIZE
            st.rerun()

    st.dataframe(
        [
            {
                "Timestamp": entry["timestamp"],
                "Actor": entry["actor"],
                "Action": entry["action"],
                "Entity": entry.get("entity") or "",
                "Reason": entry.get("reason") or "",
            }
            for entry in entries
        ],
        hide_index=True,
        width="stretch",
    )
