from __future__ import annotations

import streamlit as st

from ui.api import api_delete, api_get, api_patch, api_post, show_api_error
from ui.migration import current_migration
from ui.schema import render_schema_card

st.caption(
    "Upload one or more CSV/XLSX employee exports. Counts, filenames, and row numbers come from runtime state."
)
render_schema_card()

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
    st.stop()

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
