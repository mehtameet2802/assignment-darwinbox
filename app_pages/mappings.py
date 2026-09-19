from __future__ import annotations

import streamlit as st

from ui.api import api_get, api_patch, api_post, show_api_error
from ui.migration import require_migration
from ui.schema import TARGET_FIELDS

st.caption("Application policy decides review (0.85 threshold + structural compatibility). Humans resolve escalations.")

migration = require_migration("Select or create a migration on the New migration page first.")
if migration is None:
    st.stop()
if migration["file_count"] == 0:
    st.warning("Upload source files before generating mappings.")
    st.stop()

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
    st.stop()

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
