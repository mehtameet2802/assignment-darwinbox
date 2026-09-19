from __future__ import annotations

import requests
import streamlit as st

from app.config import APP_VERSION, BACKEND_URL
from app.schema import EMPLOYEE_TARGET_SCHEMA, target_schema_summary

TARGET_FIELDS = [field["name"] for field in EMPLOYEE_TARGET_SCHEMA["fields"]]

PIPELINE_PAGES = [
    "1. New Migration & File Analysis",
    "2. Mappings & Ambiguity Review",
    "3. Analysis & Review",
    "4. Push to Target",
    "5. Audit Log & Governance",
    "Settings / Target Schema",
]


def api_get(path: str, timeout: int = 10, **kwargs):
    return requests.get(f"{BACKEND_URL}{path}", timeout=timeout, **kwargs)


def api_post(path: str, **kwargs):
    timeout = kwargs.pop("timeout", 30)
    return requests.post(f"{BACKEND_URL}{path}", timeout=timeout, **kwargs)


def api_patch(path: str, **kwargs):
    timeout = kwargs.pop("timeout", 10)
    return requests.patch(f"{BACKEND_URL}{path}", timeout=timeout, **kwargs)


def api_delete(path: str, **kwargs):
    timeout = kwargs.pop("timeout", 10)
    return requests.delete(f"{BACKEND_URL}{path}", timeout=timeout, **kwargs)


def fetch_backend_health() -> tuple[bool, dict]:
    try:
        response = api_get("/health", timeout=2)
        response.raise_for_status()
        return True, response.json()
    except requests.RequestException as exc:
        return False, {"status": "down", "error": str(exc)}


def show_api_error(response: requests.Response | None = None, fallback: str = "Request failed.") -> None:
    if response is None:
        st.error(fallback)
        return
    try:
        payload = response.json()
        st.error(payload.get("error") or fallback)
    except ValueError:
        st.error(fallback)


st.set_page_config(
    page_title="SyncHR Migrate",
    page_icon="🗂️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Source+Sans+3:wght@400;600;700&display=swap');
    html, body, [class*="st-"] { font-family: "Source Sans 3", sans-serif; }
    </style>
    """,
    unsafe_allow_html=True,
)

if "migration_id" not in st.session_state:
    st.session_state.migration_id = None

with st.sidebar:
    st.markdown("**SyncHR Migrate**")
    st.caption("AI HRIS Migration Console")
    st.divider()
    st.caption("MIGRATION PIPELINE")
    page = st.radio("Pipeline", PIPELINE_PAGES, label_visibility="collapsed")
    st.divider()
    backend_ok, health = fetch_backend_health()
    sqlite_ok = backend_ok and health.get("sqlite", {}).get("initialized") == "true"
    status_dot = "🟢" if backend_ok and sqlite_ok else "🔴"
    st.caption(f"{status_dot} Flask {'connected' if backend_ok else 'offline'} • SQLite {'ready' if sqlite_ok else 'not ready'}")
    st.caption(f"Local Migration Engine • v{APP_VERSION}")

if not backend_ok:
    st.error(
        f"Flask backend is not reachable at `{BACKEND_URL}`. "
        "Start it with `python flask_app.py` in another terminal."
    )
    st.stop()


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


def render_schema_card() -> None:
    schema = target_schema_summary()
    st.subheader(schema["name"])
    st.caption(f"{schema['required_count']} required • {schema['optional_count']} optional • employees only")
    st.dataframe(
        [
            {
                "Field": field["name"],
                "Type": field["type"],
                "Required": "Yes" if field["required"] else "No",
            }
            for field in schema["fields"]
        ],
        hide_index=True,
        width="stretch",
    )


def render_new_migration() -> None:
    st.title("New Employee Migration")
    st.caption(
        "Upload one or more CSV/XLSX employee exports. Counts, filenames, and row numbers come from runtime state."
    )
    render_schema_card()

    migration = current_migration()
    col_new, col_existing = st.columns([1, 2])
    with col_new:
        if st.button("Create migration", type="primary"):
            response = api_post("/api/migrations", json={"name": "Employee Migration"})
            if response.status_code == 201:
                st.session_state.migration_id = response.json()["id"]
                st.rerun()
            else:
                show_api_error(response, "Could not create migration.")
    with col_existing:
        listing = api_get("/api/migrations").json().get("migrations", [])
        labels = {f"MIG-{item['id']} • {item['name']} ({item['file_count']} files)": item["id"] for item in listing}
        selected = st.selectbox("Active migration", ["(none)"] + list(labels.keys()))
        if selected != "(none)":
            st.session_state.migration_id = labels[selected]

    migration = current_migration()
    if migration is None:
        st.info("Create a migration before uploading files.")
        return

    st.success(
        f"Active session MIG-{migration['id']} • {migration['file_count']} files • "
        f"{migration['total_source_rows']} source rows"
    )

    uploaded = st.file_uploader(
        "Source datasets",
        type=["csv", "xlsx"],
        accept_multiple_files=True,
        help="Accepted formats: CSV (.csv), Excel (.xlsx). Other extensions are rejected.",
    )
    load_demo, start_later = st.columns(2)
    with load_demo:
        if st.button("Load spec demo files"):
            response = api_post(f"/api/migrations/{migration['id']}/demo-files")
            if response.status_code == 201:
                st.rerun()
            else:
                show_api_error(response, "Could not load demo files.")
    if uploaded:
        if st.button("Upload selected files"):
            files = [("files", (item.name, item.getvalue(), item.type or "application/octet-stream")) for item in uploaded]
            response = api_post(f"/api/migrations/{migration['id']}/files", files=files)
            if response.status_code == 201:
                st.rerun()
            else:
                show_api_error(response, "Upload failed.")

    migration = current_migration() or migration
    st.markdown(f"**Staged source files** — {migration['file_count']} loaded, {migration['total_source_rows']} source rows")
    if not migration["files"]:
        st.caption("No files staged yet.")
    else:
        table_rows = []
        for source_file in migration["files"]:
            table_rows.append(
                {
                    "ID": source_file["id"],
                    "Filename": source_file["filename"],
                    "Format": source_file["format"],
                    "Rows": source_file["row_count"],
                    "Cols": source_file["column_count"],
                    "Status": source_file["status"],
                    "Error": source_file["error_message"] or "",
                }
            )
        st.dataframe(table_rows, hide_index=True, width="stretch")

        file_options = {f"{item['filename']} ({item['row_count']} rows)": item["id"] for item in migration["files"]}
        preview_label = st.selectbox("Preview file", list(file_options.keys()))
        preview_id = file_options[preview_label]
        preview = api_get(f"/api/migrations/{migration['id']}/files/{preview_id}/preview?limit=20")
        if preview.status_code == 200:
            payload = preview.json()
            st.caption(
                f"{payload['filename']} • header row {payload['header_row_number']} • "
                f"first data row {payload['rows'][0]['source_row_number'] if payload['rows'] else 'n/a'}"
            )
            st.dataframe(payload["rows"], hide_index=True, width="stretch")
        else:
            show_api_error(preview, "Preview failed.")

        delete_label = st.selectbox("Remove file", list(file_options.keys()), key="delete_file")
        if st.button("Delete selected file"):
            response = api_delete(f"/api/migrations/{migration['id']}/files/{file_options[delete_label]}")
            if response.status_code == 200:
                st.rerun()
            else:
                show_api_error(response, "Could not delete file.")

    auto_remove = st.toggle(
        "Auto-remove exact duplicates",
        value=migration["auto_remove_exact_duplicates"],
        help="Exact duplicates are collapsed later. Conflicting duplicates always need review. Detection always runs.",
    )
    if auto_remove != migration["auto_remove_exact_duplicates"]:
        api_patch(
            f"/api/migrations/{migration['id']}",
            json={"auto_remove_exact_duplicates": auto_remove},
        )
        st.rerun()

    if migration["file_count"] > 0:
        col_det, col_sem = st.columns(2)
        with col_det:
            run_det = st.button("Run deterministic column analysis")
        with col_sem:
            run_sem = st.button("Run Ollama semantic mapping")
        if run_det:
            analysis = api_get(f"/api/migrations/{migration['id']}/source-analysis")
            if analysis.status_code == 200:
                st.session_state[f"analysis_{migration['id']}"] = analysis.json()
            else:
                show_api_error(analysis, "Column analysis failed.")
        if run_sem:
            analysis = api_get(
                f"/api/migrations/{migration['id']}/source-analysis?include_semantic=true",
                timeout=120,
            )
            if analysis.status_code == 200:
                st.session_state[f"analysis_{migration['id']}"] = analysis.json()
            else:
                show_api_error(analysis, "Ollama semantic mapping failed.")
        analysis_payload = st.session_state.get(f"analysis_{migration['id']}")
        if analysis_payload:
            semantic_note = (
                f", {analysis_payload.get('semantic_mappings', 0)} via Ollama"
                if analysis_payload.get("include_semantic")
                else ""
            )
            st.markdown(
                f"**Column analysis** — {analysis_payload.get('mapped_columns', 0)} / "
                f"{analysis_payload['column_count']} mapped "
                f"({analysis_payload['deterministic_mappings']} alias{semantic_note})"
            )
            analysis_rows = [
                {
                    "Source file": item["source_file"],
                    "Source column": item["source_column"],
                    "Detected type": item["detected_source_type"],
                    "Proposed target": item["proposed_target"] or "—",
                    "Method": item["mapping_method"] or "—",
                    "Confidence": item["confidence"] if item["confidence"] is not None else "—",
                    "Samples": ", ".join(item["sample_values"][:3]),
                }
                for item in analysis_payload["columns"]
            ]
            st.dataframe(analysis_rows, hide_index=True, width="stretch")

    with start_later:
        st.caption(f"Status: {migration['status']}")


def render_mappings_review() -> None:
    st.title("Mappings & Ambiguity Review")
    st.caption("Application policy decides review (0.85 threshold + structural compatibility). Humans resolve escalations.")
    render_migration_picker()
    migration = current_migration()
    if migration is None:
        st.info("Select or create a migration on the New Migration page first.")
        return
    if migration["file_count"] == 0:
        st.warning("Upload source files before generating mappings.")
        return

    if st.button("Generate mappings (aliases + Ollama)", type="primary"):
        response = api_post(
            f"/api/migrations/{migration['id']}/mappings/generate?include_semantic=true",
            timeout=180,
        )
        if response.status_code == 201:
            st.session_state[f"mappings_{migration['id']}"] = response.json()
            st.rerun()
        else:
            show_api_error(response, "Could not generate mappings.")

    payload = st.session_state.get(f"mappings_{migration['id']}")
    if payload is None:
        cached = api_get(f"/api/migrations/{migration['id']}/mappings")
        if cached.status_code == 200 and cached.json().get("mapping_count"):
            payload = cached.json()
            st.session_state[f"mappings_{migration['id']}"] = payload

    if not payload or not payload.get("mappings"):
        st.info("No mappings stored yet. Click **Generate mappings**.")
        return

    blocking = payload.get("blocking_review_count", 0)
    if blocking:
        st.warning(f"{blocking} column(s) still need review before transform can continue.")
    else:
        st.success("All mapping issues resolved or auto-approved.")

    for item in payload["mappings"]:
        status = item["status"]
        title = f"{item['source_file']} • {item['source_column']} — {status}"
        with st.expander(title, expanded=item["review_required"]):
            st.write(f"**Detected type:** {item['detected_source_type']}")
            st.write(f"**Samples:** {', '.join(item['sample_values'][:5])}")
            st.write(f"**Proposed target:** {item['proposed_target'] or '—'}")
            st.write(f"**Final target:** {item['final_target'] or '—'}")
            st.write(f"**Method:** {item['mapping_method'] or '—'}")
            st.write(f"**Confidence:** {item['confidence'] if item['confidence'] is not None else '—'}")
            if item.get("ai_reason"):
                st.write(f"**AI reason:** {item['ai_reason']}")
            if item["review_required"] and item.get("review_reason"):
                st.error(f"Needs review: {item['review_reason']}")
            elif item["status"] == "AUTO_APPROVED":
                st.success("Auto-approved (confidence and structure OK). Still editable below.")

            col_map, col_ignore = st.columns(2)
            with col_map:
                chosen = st.selectbox(
                    "Map to target field",
                    TARGET_FIELDS,
                    key=f"map_target_{item['id']}",
                    index=TARGET_FIELDS.index(item["final_target"])
                    if item["final_target"] in TARGET_FIELDS
                    else 0,
                )
                if st.button("Save mapping", key=f"save_map_{item['id']}"):
                    resp = api_patch(
                        f"/api/migrations/{migration['id']}/mappings/{item['id']}",
                        json={"action": "map", "target_field": chosen},
                    )
                    if resp.status_code == 200:
                        st.session_state.pop(f"mappings_{migration['id']}", None)
                        st.rerun()
                    else:
                        show_api_error(resp, "Could not save mapping.")
            with col_ignore:
                if st.button("Ignore source field", key=f"ignore_{item['id']}"):
                    resp = api_patch(
                        f"/api/migrations/{migration['id']}/mappings/{item['id']}",
                        json={"action": "ignore"},
                    )
                    if resp.status_code == 200:
                        st.session_state.pop(f"mappings_{migration['id']}", None)
                        st.rerun()
                    else:
                        show_api_error(resp, "Could not ignore field.")


def render_analysis_review() -> None:
    st.title("Analysis & Review")
    st.caption("Resolve date formats, transform records, and reconcile duplicate conflicts.")
    render_migration_picker()
    migration = current_migration()
    if migration is None:
        st.info("Select a migration first.")
        return

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

    push_cols = st.columns(3)
    with push_cols[0]:
        if st.button("Push ready records"):
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
            st.markdown(f"**{esc['employee_id']}** — {esc['issue_type']}")
            st.caption(esc["review_reason"])
            new_email = st.text_input("Enter email", key=f"val_email_{esc['id']}")
            if st.button("Save value", key=f"val_save_{esc['id']}"):
                resp = api_patch(
                    f"/api/migrations/{migration['id']}/validation-escalations/{esc['id']}",
                    json={"action": "enter_value", "field_name": "email", "value": new_email},
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
                    base = conflict["members"][0]["payload"]
                    email = st.text_input("Final email", value=base.get("email") or "", key=f"email_{conflict['id']}")
                    if st.button("Save resolution", key=f"save_dup_{conflict['id']}"):
                        final_payload = {**base, "email": email}
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

    audit = api_get(
        f"/api/migrations/{migration['id']}/audit-log?limit=25&offset=0"
    )
    if audit.status_code == 200 and audit.json().get("entries"):
        st.subheader("Audit log (latest 25)")
        for entry in audit.json()["entries"]:
            st.caption(
                f"{entry['timestamp']} • {entry['actor']} • {entry['action']} • "
                f"{entry.get('entity') or ''} — {entry.get('reason') or ''}"
            )


if page == PIPELINE_PAGES[0]:
    render_new_migration()
elif page == PIPELINE_PAGES[1]:
    render_mappings_review()
elif page == PIPELINE_PAGES[2]:
    render_analysis_review()
elif page == PIPELINE_PAGES[-1]:
    st.title("Settings / Target Schema")
    render_schema_card()
    st.info("Tier 1 shows the default employee schema only. Schema editing is Tier 2.")
else:
    st.title(page)
    st.info("This pipeline step will be implemented in a later phase.")
