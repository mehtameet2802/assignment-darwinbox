from __future__ import annotations

import streamlit as st

from ui.schema import render_schema_card

render_schema_card()
st.info("Tier 1 shows the default employee schema only. Schema editing is Tier 2.")
