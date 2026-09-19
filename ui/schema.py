from __future__ import annotations

import streamlit as st

from app.schema import EMPLOYEE_TARGET_SCHEMA, target_schema_summary

TARGET_FIELDS = [field["name"] for field in EMPLOYEE_TARGET_SCHEMA["fields"]]


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
