from __future__ import annotations

import streamlit as st

from ui.api import api_get, api_patch, api_post, show_api_error
from ui.migration import require_migration

st.caption("Resolve date formats, transform records, and reconcile duplicate conflicts.")

migration = require_migration("Select a migration first.")
if migration is None:
    st.stop()

st.subheader("Transform, duplicates & validation")
col_t, col_d, col_v = st.columns(3)
with col_t:
    if st.button("Transform source rows"):
        resp = api_post(f"/api/migrations/{migration['id']}/transform")
        if resp.status_code == 201:
            st.success(f"Transformed {resp.json().get('records_created')} records.")
        else:
            show_api_error(resp, "Transform failed.")
with col_d:
    if st.button("Analyze duplicates"):
        resp = api_post(f"/api/migrations/{migration['id']}/duplicates/analyze")
        if resp.status_code == 201:
            st.session_state[f"dup_{migration['id']}"] = resp.json()
            st.rerun()
        else:
            show_api_error(resp, "Duplicate analysis failed.")
with col_v:
    if st.button("Validate records"):
        resp = api_post(f"/api/migrations/{migration['id']}/validate")
        if resp.status_code == 201:
            st.session_state.pop(f"val_{migration['id']}", None)
            st.rerun()
        else:
            show_api_error(resp, "Validation failed.")

queue = api_get(f"/api/migrations/{migration['id']}/review-queue")
if queue.status_code == 200:
    q = queue.json()
    st.markdown(f"**Unified review queue** — {q.get('blocking_count', 0)} blocking item(s)")
    for item in q.get("items", []):
        with st.expander(f"{item['category']} • {item.get('employee_id') or item.get('source_column', '')}"):
            st.error(f"Rule fired: {item.get('rule_fired')} — {item.get('review_reason')}")

val_resp = api_get(f"/api/migrations/{migration['id']}/validation-escalations")
if val_resp.status_code == 200:
    for esc in val_resp.json().get("escalations", []):
        if esc["status"] != "NEEDS_REVIEW":
            continue
        field_name = esc.get("field_name") or "value"
        current_payload = esc.get("current_payload") or {}
        st.markdown(f"**{esc['employee_id']}** — {esc['issue_type']}")
        st.caption(esc["review_reason"])
        current_value = current_payload.get(field_name)
        new_value = st.text_input(
            f"Enter {field_name}",
            value=str(current_value) if current_value is not None else "",
            key=f"val_{field_name}_{esc['id']}",
        )
        if st.button("Save value", key=f"val_save_{esc['id']}"):
            resp = api_patch(
                f"/api/migrations/{migration['id']}/validation-escalations/{esc['id']}",
                json={"action": "enter_value", "field_name": field_name, "value": new_value},
            )
            if resp.status_code == 200:
                st.rerun()
            else:
                show_api_error(resp, "Could not update record.")
        if st.button("Exclude record", key=f"val_ex_{esc['id']}"):
            resp = api_patch(
                f"/api/migrations/{migration['id']}/validation-escalations/{esc['id']}",
                json={"action": "exclude"},
            )
            if resp.status_code == 200:
                st.rerun()
            else:
                show_api_error(resp, "Could not exclude record.")

dup_payload = st.session_state.get(f"dup_{migration['id']}")
if dup_payload is None:
    cached_dup = api_get(f"/api/migrations/{migration['id']}/duplicate-conflicts")
    if cached_dup.status_code == 200:
        dup_payload = cached_dup.json()
if dup_payload and dup_payload.get("conflicts"):
    st.markdown(f"**Duplicate conflicts** — {dup_payload.get('blocking_count', 0)} blocking")
    for conflict in dup_payload["conflicts"]:
        with st.expander(
            f"{conflict['employee_id']} — {conflict['status']}",
            expanded=conflict["status"] == "NEEDS_REVIEW",
        ):
            st.error(f"Rule fired: {conflict['review_reason']}")
            for idx, member in enumerate(conflict["members"]):
                st.write(f"Record {idx + 1}: {member['payload']}")
                for src in member.get("sources", []):
                    st.caption(f"{src['source_file']} row {src['source_row_number']}")
            if conflict["status"] == "NEEDS_REVIEW" and conflict["members"]:
                base = dict(conflict["members"][0]["payload"])
                edit_fields = conflict.get("differing_fields") or list(base.keys())
                final_payload = dict(base)
                for field in edit_fields:
                    raw = base.get(field)
                    final_payload[field] = st.text_input(
                        f"Final {field}",
                        value=str(raw) if raw is not None else "",
                        key=f"dup_{conflict['id']}_{field}",
                    )
                if st.button("Save resolution", key=f"save_dup_{conflict['id']}"):
                    resp = api_patch(
                        f"/api/migrations/{migration['id']}/duplicate-conflicts/{conflict['id']}",
                        json={"action": "save", "final_payload": final_payload},
                    )
                    if resp.status_code == 200:
                        st.session_state.pop(f"dup_{migration['id']}", None)
                        st.rerun()
                    else:
                        show_api_error(resp, "Could not save duplicate resolution.")

st.subheader("Date format")
if st.button("Scan date columns", type="primary"):
    response = api_post(f"/api/migrations/{migration['id']}/date-columns/scan")
    if response.status_code == 201:
        st.session_state[f"date_esc_{migration['id']}"] = response.json()
        st.rerun()
    else:
        show_api_error(response, "Date scan failed.")

payload = st.session_state.get(f"date_esc_{migration['id']}")
if payload is None:
    cached = api_get(f"/api/migrations/{migration['id']}/date-escalations")
    if cached.status_code == 200 and cached.json().get("escalation_count"):
        payload = cached.json()
        st.session_state[f"date_esc_{migration['id']}"] = payload

if not payload or not payload.get("escalations"):
    st.caption("Run **Scan date columns** after mappings target `joining_date`.")
elif payload.get("blocking_count"):
    st.warning(f"{payload['blocking_count']} date column(s) need format selection.")
elif payload:
    st.success("All date columns have a resolved format.")

if payload and payload.get("escalations"):
    for item in payload["escalations"]:
        with st.expander(
            f"{item['source_file']} • {item['source_column']} — {item['status']}",
            expanded=item["status"] == "NEEDS_REVIEW",
        ):
            st.write(f"**Issue:** {item['issue_type']}")
            st.write(f"**Samples:** {', '.join(item['sample_values'][:6])}")
            if item.get("review_reason"):
                st.error(item["review_reason"])
            if item["status"] == "NEEDS_REVIEW":
                fmt = st.radio(
                    "Choose column date format",
                    ["DD/MM/YYYY", "MM/DD/YYYY"],
                    key=f"date_fmt_{item['id']}",
                )
                if st.button("Apply to entire column", key=f"date_apply_{item['id']}"):
                    resp = api_patch(
                        f"/api/migrations/{migration['id']}/date-escalations/{item['id']}",
                        json={"chosen_format": fmt},
                    )
                    if resp.status_code == 200:
                        st.session_state.pop(f"date_esc_{migration['id']}", None)
                        st.rerun()
                    else:
                        show_api_error(resp, "Could not resolve date format.")
            else:
                st.write(f"**Chosen format:** {item.get('chosen_format')}")
