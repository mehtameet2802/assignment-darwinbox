from __future__ import annotations

import requests
import streamlit as st

from app.config import APP_VERSION, BACKEND_URL
from app.schema import target_schema_summary

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

    st.button("Start Analysis & AI Field Matching", disabled=True)
    st.caption("Mapping and AI start in Phase 3–5. Unresolved mappings will block transform then.")
    with start_later:
        st.caption(f"Status: {migration['status']}")


if page == PIPELINE_PAGES[0]:
    render_new_migration()
elif page == PIPELINE_PAGES[-1]:
    st.title("Settings / Target Schema")
    render_schema_card()
    st.info("Tier 1 shows the default employee schema only. Schema editing is Tier 2.")
else:
    st.title(page)
    st.info("This pipeline step will be implemented in a later phase.")
