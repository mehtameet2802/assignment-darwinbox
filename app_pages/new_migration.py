from __future__ import annotations

import pandas as pd
import streamlit as st

from ui.api import api_delete, api_get, api_patch, api_post, show_api_error
from ui.migration import current_migration
from ui.migration_picker import migration_selectbox_index
from ui.navigation import PAGE_MAPPINGS, render_pipeline_stepper, switch_to
from ui.schema import render_schema_card


def _clear_mapping_cache(migration_id: int) -> None:
    st.session_state.pop(f"mappings_{migration_id}", None)
    st.session_state.pop(f"analysis_{migration_id}", None)


render_pipeline_stepper(0)
st.caption("Stage source files, then continue to map columns.")
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
    labels = {
        f"MIG-{item['id']} • {item['name']} ({item['file_count']} files)": item["id"]
        for item in listing
    }
    option_labels = ["(none)"] + list(labels.keys())
    selected = st.selectbox(
        "Active migration",
        option_labels,
        index=migration_selectbox_index(option_labels, labels),
        key="new_migration_active_pick",
    )
    if selected != "(none)":
        st.session_state.migration_id = labels[selected]

migration = current_migration()
if migration is None:
    st.info("Create or select a migration to stage files.")
    st.stop()

has_files = migration["file_count"] > 0

nav_col, status_col = st.columns([1, 2])
with nav_col:
    if st.button(
        "Continue to Mappings & review →",
        type="primary",
        disabled=not has_files,
        help="Stage at least one source file before continuing.",
        width="stretch",
    ):
        switch_to(PAGE_MAPPINGS)
with status_col:
    st.success(
        f"**MIG-{migration['id']}** — {migration['file_count']} staged file(s), "
        f"{migration['total_source_rows']} source row(s) • status `{migration['status']}`"
    )

st.subheader("1. Add source files")
st.caption("Each upload adds files to this migration without removing files already staged.")

if st.button("Load demo files into this migration"):
    response = api_post(f"/api/migrations/{migration['id']}/demo-files")
    if response.status_code == 201:
        _clear_mapping_cache(migration["id"])
        st.rerun()
    else:
        show_api_error(response, "Could not load demo files.")

uploaded = st.file_uploader(
    "Source datasets (CSV / XLSX)",
    type=["csv", "xlsx"],
    accept_multiple_files=True,
)
if uploaded and st.button("Add uploaded files to this migration"):
    files = [
        ("files", (item.name, item.getvalue(), item.type or "application/octet-stream"))
        for item in uploaded
    ]
    response = api_post(f"/api/migrations/{migration['id']}/files", files=files)
    if response.status_code == 201:
        _clear_mapping_cache(migration["id"])
        st.rerun()
    else:
        show_api_error(response, "Upload failed.")
elif not uploaded:
    st.caption("Choose file(s), then click **Add uploaded files to this migration**.")

migration = current_migration() or migration
has_files = migration["file_count"] > 0

st.subheader("2. Staged files")
if not migration["files"]:
    st.warning("No files staged yet. Load demo files or upload your own above.")
else:
    file_id_by_name: dict[str, int] = {}
    for source_file in migration["files"]:
        file_id_by_name[source_file["filename"]] = source_file["id"]

    id_by_file = {sf["filename"]: sf["id"] for sf in migration["files"]}
    staged_df = pd.DataFrame(
        [
            {
                "File": sf["filename"],
                "Format": sf["format"],
                "Rows": int(sf["row_count"]),
                "Cols": int(sf["column_count"]),
                "Remove": False,
            }
            for sf in migration["files"]
        ]
    )
    edited = st.data_editor(
        staged_df,
        hide_index=True,
        width="stretch",
        column_config={
            "File": st.column_config.TextColumn("File", width="large"),
            "Format": st.column_config.TextColumn("Format", width="small"),
            "Rows": st.column_config.NumberColumn("Rows", width="small", format="%d"),
            "Cols": st.column_config.NumberColumn("Cols", width="small", format="%d"),
            "Remove": st.column_config.CheckboxColumn(
                "Remove",
                width="small",
                default=False,
            ),
        },
        disabled=["File", "Format", "Rows", "Cols"],
        key=f"staged_files_table_{migration['id']}",
    )
    if edited["Remove"].any():
        if st.button("Remove checked files", type="secondary"):
            errors = 0
            for _, row in edited.iterrows():
                if row["Remove"]:
                    response = api_delete(
                        f"/api/migrations/{migration['id']}/files/{id_by_file[row['File']]}"
                    )
                    if response.status_code != 200:
                        errors += 1
                        show_api_error(response, f"Could not remove {row['File']}.")
            if errors == 0:
                _clear_mapping_cache(migration["id"])
                st.rerun()

    preview_names = list(file_id_by_name.keys())
    preview_name = st.selectbox("Preview staged file", preview_names)
    preview_id = file_id_by_name[preview_name]
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

st.subheader("3. Duplicate handling")
auto_remove = st.toggle(
    "Auto-remove exact duplicates during duplicate analysis",
    value=migration["auto_remove_exact_duplicates"],
    help="Exact duplicates can be collapsed later. Conflicting duplicates always require human review.",
)
if auto_remove != migration["auto_remove_exact_duplicates"]:
    api_patch(
        f"/api/migrations/{migration['id']}",
        json={"auto_remove_exact_duplicates": auto_remove},
    )
    st.rerun()

if has_files:
    st.divider()
    if st.button("Continue to Mappings & review →", type="primary", width="stretch"):
        switch_to(PAGE_MAPPINGS)
