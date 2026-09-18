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


def fetch_backend_health() -> tuple[bool, dict]:
    try:
        response = requests.get(f"{BACKEND_URL}/health", timeout=2)
        response.raise_for_status()
        return True, response.json()
    except requests.RequestException as exc:
        return False, {"status": "down", "error": str(exc)}


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

st.title("New Employee Migration")
st.caption("Upload one or more CSV/XLSX employee exports. Phase 1 is bootstrap only — file ingestion starts in Phase 2.")

if not backend_ok:
    st.error(
        f"Flask backend is not reachable at `{BACKEND_URL}`. "
        "Start it with `python flask_app.py` in another terminal."
    )
else:
    st.success("Flask started successfully. SQLite connection is working.")

schema = target_schema_summary()
st.subheader(schema["name"])
st.caption(f"{schema['required_count']} required • {schema['optional_count']} optional")

rows = [
    {
        "Field": field["name"],
        "Type": field["type"],
        "Required": "Yes" if field["required"] else "No",
    }
    for field in schema["fields"]
]
st.dataframe(rows, hide_index=True, width="stretch")

if page != PIPELINE_PAGES[0] and page != PIPELINE_PAGES[-1]:
    st.info("This pipeline step will be implemented in a later phase. The implementation spec wins over placeholder UI copy.")
elif page == PIPELINE_PAGES[-1]:
    st.info("Tier 1 shows the default employee schema only. Schema editing is Tier 2.")
