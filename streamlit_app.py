from __future__ import annotations

import streamlit as st

from app.config import APP_VERSION, BACKEND_URL
from ui.api import fetch_backend_health

st.set_page_config(
    page_title="SyncHR Migrate",
    page_icon=":material/folder_open:",
    layout="wide",
    initial_sidebar_state="expanded",
)

if "migration_id" not in st.session_state:
    st.session_state.migration_id = None

page = st.navigation(
    {
        "Migration pipeline": [
            st.Page("app_pages/new_migration.py", title="New migration", icon=":material/upload_file:", default=True),
            st.Page("app_pages/mappings.py", title="Mappings & review", icon=":material/join:"),
            st.Page("app_pages/analysis.py", title="Analysis & review", icon=":material/fact_check:"),
            st.Page("app_pages/push.py", title="Push to target", icon=":material/cloud_upload:"),
            st.Page("app_pages/audit.py", title="Audit log", icon=":material/history:"),
        ],
        "Setup": [
            st.Page("app_pages/settings.py", title="Target schema", icon=":material/settings:"),
        ],
    },
    position="sidebar",
)

with st.sidebar:
    st.caption("AI HRIS migration console")
    backend_ok, health = fetch_backend_health()
    sqlite_ok = backend_ok and health.get("sqlite", {}).get("initialized") == "true"
    if backend_ok and sqlite_ok:
        st.caption(":material/check_circle: Flask connected • SQLite ready")
    else:
        st.caption(":material/error: Flask offline or SQLite not ready")
    st.caption(f"Local migration engine • v{APP_VERSION}")

if not backend_ok:
    st.error(
        f"Flask backend is not reachable at `{BACKEND_URL}`. "
        "Start it with `python flask_app.py` in another terminal."
    )
    st.stop()

st.title(page.title, icon=page.icon)
page.run()
