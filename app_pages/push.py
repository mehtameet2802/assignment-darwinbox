from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from ui.api import api_get, api_post, show_api_error
from ui.migration import require_migration_push_ready
from ui.navigation import PAGE_ANALYSIS, PAGE_AUDIT, render_pipeline_stepper, switch_to

render_pipeline_stepper(3)

st.subheader("How push to target works")
st.info(
    """
**Push** sends every `READY_TO_PUSH` row to the mock API (`POST /mock-target/employees`).

**Retry** sends only rows in `PUSH_FAILED` status (new attempt number per employee).

**Rollback** removes employees from the **latest completed push batch** in the target and sets them back to `READY_TO_PUSH`.

**Latest operation** summarizes only the most recent push, retry, or rollback — not mixed with older batch states.

**Attempt history** (below) is the full audit trail (e.g. E009 failed once, then succeeded on retry).

**Complete migration** — you must click this to mark the push workflow **finished** (success or, if every record failed and nothing is in the target, you can close without a successful push). It removes the migration from this Push picker. **Audit log** lists every migration anytime.
    """.strip()
)

migration = require_migration_push_ready("Select a migration that has completed analysis.")
if migration is None:
    if st.button("← Go to Analysis & review"):
        switch_to(PAGE_ANALYSIS)
    st.stop()

mid = migration["id"]


def _load_overview() -> dict | None:
    resp = api_get(f"/api/migrations/{mid}/push/overview")
    if resp.status_code != 200:
        show_api_error(resp, "Could not load push overview.")
        return None
    return resp.json()


def _render_operation_result(op: dict) -> None:
    summary = op.get("summary") or {}
    st.markdown(f"**{op.get('operation_label', 'Operation completed')}**")
    st.markdown(
        f"Successful: **{summary.get('successful', 0)}** · "
        f"Failed: **{summary.get('failed', 0)}** · "
        f"Total: **{summary.get('total', 0)}**"
    )
    for item in op.get("results") or []:
        if item.get("result") == "success":
            st.markdown(f"✓ **{item['employee_id']}**")
        else:
            err = item.get("error_message") or "Unknown error"
            http = item.get("http_status")
            http_part = f" · HTTP {http}" if http is not None else ""
            st.markdown(f"✗ **{item['employee_id']}** — {err}{http_part}")


def _store_last_operation(payload: dict) -> None:
    st.session_state[f"push_last_op_{mid}"] = payload


overview = _load_overview()
if overview is None:
    st.stop()

workflow = overview.get("workflow") or {}
counts = overview.get("record_counts") or {}
ready = counts.get("ready_to_push", 0)
failed_count = counts.get("push_failed", 0)
pushed_count = counts.get("pushed", 0)
target_count = overview.get("target_record_count", 0)

st.subheader("Where you are now")
st.markdown(f"**{workflow.get('title', 'Push workflow')}**")
st.markdown(workflow.get("summary", ""))
st.caption(workflow.get("next_step", ""))

st.divider()
st.subheader(f"MIG-{mid} • {migration['name']}")
st.markdown(
    f"**{ready}** ready · **{pushed_count}** pushed in migration · "
    f"**{failed_count}** failed · **{target_count}** in mock target"
)

action_cols = st.columns(4)
with action_cols[0]:
    if st.button("Push to target", type="primary", disabled=ready == 0):
        resp = api_post(f"/api/migrations/{mid}/push")
        if resp.status_code == 201:
            _store_last_operation(resp.json())
            st.rerun()
        else:
            show_api_error(resp, "Push failed.")
with action_cols[1]:
    if st.button("Retry failed records", disabled=failed_count == 0):
        resp = api_post(f"/api/migrations/{mid}/push/retry")
        if resp.status_code == 201:
            _store_last_operation(resp.json())
            st.rerun()
        else:
            show_api_error(resp, "Retry failed.")
with action_cols[2]:
    if st.button("Roll back latest batch", disabled=target_count == 0):
        resp = api_post(f"/api/migrations/{mid}/push/rollback")
        if resp.status_code == 200:
            _store_last_operation(resp.json())
            st.rerun()
        else:
            show_api_error(resp, "Rollback failed.")
with action_cols[3]:
    complete_mode = workflow.get("complete_mode")
    complete_label = (
        "Complete migration (push unresolved)"
        if complete_mode == "unresolved"
        else "Complete migration"
    )
    complete_help = (
        "All pushes failed and the target is empty. Close this workflow or retry first."
        if complete_mode == "unresolved"
        else "All records are in the target with no failures."
    )
    if st.button(
        complete_label,
        disabled=not workflow.get("can_complete"),
        help=complete_help,
    ):
        resp = api_post(f"/api/migrations/{mid}/push/complete")
        if resp.status_code == 200:
            st.session_state.migration_id = mid
            switch_to(PAGE_AUDIT)
        else:
            show_api_error(resp, "Could not complete migration.")

if workflow.get("can_complete") and workflow.get("complete_mode") == "success":
    st.success("All records are in the target. Click **Complete migration** when you are done.")
elif workflow.get("can_complete") and workflow.get("complete_mode") == "unresolved":
    st.warning(
        "Every record failed and the mock target is empty. **Retry failed records** or "
        "**Complete migration (push unresolved)** to close this workflow."
    )

st.divider()
st.subheader("Latest operation")
flashed = st.session_state.pop(f"push_last_op_{mid}", None)
latest = overview.get("latest_operation")
if flashed:
    _render_operation_result(flashed)
elif latest:
    _render_operation_result(latest)
else:
    st.caption("No push, retry, or rollback has been run yet.")

failed_records = overview.get("failed_records") or []
if failed_records:
    st.subheader("Failed records (current state)")
    for item in failed_records:
        http = item.get("http_status")
        http_label = f" · HTTP {http}" if http is not None else ""
        st.error(f"**{item['employee_id']}** — {item.get('reason', 'Push failed')}{http_label}")

with st.expander("View API responses (latest operation)", expanded=False):
    op = flashed or latest
    if not op or not op.get("results"):
        st.caption("Run a push or retry to see per-employee API responses.")
    else:
        for item in op["results"]:
            st.markdown(f"**{item.get('employee_id')}** · {item.get('operation_label', 'Push')}")
            st.caption(f"Result: {item.get('result')} · HTTP {item.get('http_status')}")
            body = item.get("response_body")
            if body:
                st.code(json.dumps(body, indent=2), language="json")
            elif item.get("error_message"):
                st.code(item["error_message"], language="text")
            st.divider()

with st.expander("View target records", expanded=False):
    targets = overview.get("target_records") or []
    if not targets:
        st.caption("No employee records are stored in the mock target for this migration yet.")
    else:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Employee ID": row["employee_id"],
                        "Name": row.get("name"),
                        "Email": row.get("email"),
                        "Department": row.get("department"),
                        "Migration status": row.get("migration_record_status") or "—",
                        "Target batch": row.get("batch_id"),
                    }
                    for row in targets
                ]
            ),
            hide_index=True,
            width="stretch",
        )

with st.expander("View attempt history (audit)", expanded=False):
    history = overview.get("attempt_history") or []
    if not history:
        st.caption("No attempts recorded yet.")
    else:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Employee": row.get("employee_id"),
                        "Operation": row.get("operation_label"),
                        "Attempt": row.get("attempt_number") if row.get("attempt_number") else "—",
                        "Result": row.get("result"),
                        "HTTP": row.get("http_status"),
                        "Error": row.get("error_message") or "",
                    }
                    for row in history
                ]
            ),
            hide_index=True,
            width="stretch",
        )
