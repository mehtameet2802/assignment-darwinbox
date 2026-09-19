from __future__ import annotations

import streamlit as st

PAGE_NEW_MIGRATION = "app_pages/new_migration.py"
PAGE_MAPPINGS = "app_pages/mappings.py"
PAGE_ANALYSIS = "app_pages/analysis.py"
PAGE_PUSH = "app_pages/push.py"
PAGE_AUDIT = "app_pages/audit.py"

PIPELINE_STEPS = [
    ("New migration", PAGE_NEW_MIGRATION),
    ("Mappings & review", PAGE_MAPPINGS),
    ("Analysis & review", PAGE_ANALYSIS),
    ("Push to target", PAGE_PUSH),
    ("Audit log", PAGE_AUDIT),
]


def switch_to(page_path: str) -> None:
    st.switch_page(page_path)


def render_pipeline_stepper(active_index: int) -> None:
    labels = " → ".join(
        f"**{name}**" if idx == active_index else name
        for idx, (name, _) in enumerate(PIPELINE_STEPS)
    )
    st.caption(labels)
