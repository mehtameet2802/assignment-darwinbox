from __future__ import annotations

import streamlit as st

from ui.api import api_get, api_post, show_api_error
from ui.migration import require_migration

st.caption("Push ready records to the mock target. Retry failed rows or roll back the latest batch.")

migration = require_migration("Select a migration first.")
if migration is None:
    st.stop()

push_cols = st.columns(3)
with push_cols[0]:
    if st.button("Push ready records", type="primary"):
        resp = api_post(f"/api/migrations/{migration['id']}/push")
        if resp.status_code == 201:
            st.success(f"Pushed {resp.json().get('records_attempted')} record(s).")
        else:
            show_api_error(resp, "Push failed.")
with push_cols[1]:
    if st.button("Retry failed push"):
        resp = api_post(f"/api/migrations/{migration['id']}/push/retry")
        if resp.status_code == 201:
            st.success(f"Retried {resp.json().get('records_attempted')} failed record(s).")
        else:
            show_api_error(resp, "Retry failed.")
with push_cols[2]:
    if st.button("Rollback last push"):
        resp = api_post(f"/api/migrations/{migration['id']}/push/rollback")
        if resp.status_code == 200:
            st.warning("Rollback completed for the latest push batch.")
        else:
            show_api_error(resp, "Rollback failed.")

attempts = api_get(f"/api/migrations/{migration['id']}/push/attempts")
if attempts.status_code != 200:
    show_api_error(attempts, "Could not load push attempts.")
    st.stop()

rows = attempts.json().get("attempts", [])
if not rows:
    st.caption("No push attempts yet.")
else:
    st.dataframe(
        [
            {
                "Employee": row.get("employee_id"),
                "Attempt": row.get("attempt_number"),
                "Result": row.get("result"),
                "HTTP": row.get("http_status"),
                "Batch status": row.get("batch_status"),
                "Error": row.get("error_message") or "",
            }
            for row in rows
        ],
        hide_index=True,
        width="stretch",
    )
