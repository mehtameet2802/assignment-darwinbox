from __future__ import annotations

from collections import defaultdict

import pandas as pd
import streamlit as st

from ui.api import api_get, api_patch, api_post, fetch_backend_health, show_api_error
from ui.migration import require_migration_staged_files
from ui.navigation import PAGE_ANALYSIS, PAGE_NEW_MIGRATION, render_pipeline_stepper, switch_to
from ui.schema import TARGET_FIELDS

_REVIEW_ROW_STYLE = "background-color: #fef3c7; color: #78350f;"
_OK_ROW_STYLE = ""


def _render_mapping_editor(migration: dict, item: dict, *, compact: bool = False) -> None:
    label = item["source_column"]
    if item["review_required"]:
        label = f":material/warning: {label} — needs review"
    with st.expander(label, expanded=item["review_required"] and not compact):
        if item["review_required"]:
            st.warning(item.get("review_reason") or "This column needs a human decision before transform.")
        elif item["status"] == "AUTO_APPROVED":
            st.success("Auto-approved. You can still change the mapping below.")

        st.write(f"**Detected type:** {item['detected_source_type']}")
        st.write(f"**Samples:** {', '.join(item['sample_values'][:5])}")
        st.write(f"**Proposed target:** {item['proposed_target'] or '—'}")
        st.write(f"**Final target:** {item['final_target'] or '—'}")
        st.write(f"**Method:** {item['mapping_method'] or '—'}")
        st.write(f"**Confidence:** {item['confidence'] if item['confidence'] is not None else '—'}")
        if item.get("ai_reason"):
            st.write(f"**AI reason:** {item['ai_reason']}")

        chosen = st.selectbox(
            "Map to target field",
            TARGET_FIELDS,
            key=f"map_target_{item['id']}",
            index=TARGET_FIELDS.index(item["final_target"])
            if item["final_target"] in TARGET_FIELDS
            else 0,
        )
        save_col, ignore_col = st.columns(2)
        with save_col:
            if st.button("Save mapping", type="primary", key=f"save_map_{item['id']}", width="stretch"):
                resp = api_patch(
                    f"/api/migrations/{migration['id']}/mappings/{item['id']}",
                    json={"action": "map", "target_field": chosen},
                )
                if resp.status_code == 200:
                    st.session_state.pop(f"mappings_{migration['id']}", None)
                    st.rerun()
                else:
                    show_api_error(resp, "Could not save mapping.")
        with ignore_col:
            if st.button("Ignore source field", key=f"ignore_{item['id']}", width="stretch"):
                resp = api_patch(
                    f"/api/migrations/{migration['id']}/mappings/{item['id']}",
                    json={"action": "ignore"},
                )
                if resp.status_code == 200:
                    st.session_state.pop(f"mappings_{migration['id']}", None)
                    st.rerun()
                else:
                    show_api_error(resp, "Could not ignore field.")


def _style_mapping_row(row: pd.Series) -> list[str]:
    if row["Review"] == "Needs review":
        return [_REVIEW_ROW_STYLE] * len(row)
    return [_OK_ROW_STYLE] * len(row)


def _file_overview_table(items: list[dict]):
    rows = []
    for item in items:
        if item["ignored"]:
            review_label = "Ignored"
        elif item["review_required"]:
            review_label = "Needs review"
        else:
            review_label = "OK"
        rows.append(
            {
                "Review": review_label,
                "Source column": item["source_column"],
                "Status": item["status"],
                "Final target": item["final_target"] or "—",
                "Method": item["mapping_method"] or "—",
                "Confidence": item["confidence"] if item["confidence"] is not None else "—",
            }
        )
    df = pd.DataFrame(rows)
    return df.style.apply(_style_mapping_row, axis=1)


render_pipeline_stepper(1)

st.caption(
    "One mapping pass: **Ollama first**, then **deterministic alias fallback** if Ollama fails or is down. "
    "Policy still escalates incompatible or low-confidence proposals for human review."
)

migration = require_migration_staged_files("Select a migration with staged files.")
if migration is None:
    st.stop()

backend_ok, health = fetch_backend_health()
ollama_cfg = health.get("ollama", {}) if backend_ok else {}
if backend_ok:
    st.caption(
        f"Ollama endpoint: `{ollama_cfg.get('base_url', 'n/a')}` • model `{ollama_cfg.get('model', 'n/a')}`"
    )

if st.button("Generate column mappings", type="primary"):
    with st.spinner("Mapping columns (Ollama, with alias fallback)…"):
        response = api_post(
            f"/api/migrations/{migration['id']}/mappings/generate?include_semantic=true",
            timeout=300,
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
    st.info(
        "No mappings stored yet. Click **Generate column mappings** after staging files.\n\n"
        "**If Ollama is unavailable:** aliases still map obvious headers (e.g. DOJ → joining_date). "
        "**If both fail:** the column stays unmapped — choose a target below.\n\n"
        "**If a fallback alias is wrong:** change the target and save, or ignore the source column."
    )
    st.stop()

summary = payload.get("generation_summary")
if summary:
    parts = [
        f"{summary.get('mapped_columns', 0)} mapped",
        f"{summary.get('semantic_mappings', 0)} via Ollama",
        f"{summary.get('alias_fallback_mappings', 0)} alias fallback",
        f"{summary.get('unmapped_columns', 0)} unmapped",
    ]
    st.markdown("**Last generation:** " + " • ".join(parts))
    if summary.get("strategy") == "ollama_then_alias_fallback" and summary.get("alias_fallback_mappings"):
        st.caption("Some columns used alias fallback because Ollama failed or returned no mapping for that header.")

blocking = payload.get("blocking_review_count", 0)
mappings_finalized = blocking == 0 and payload.get("mapping_count", 0) > 0

if blocking:
    st.warning(f":material/warning: **{blocking} column(s)** still need review before transform can continue.")
else:
    st.success(":material/check_circle: All mapping issues resolved or auto-approved.")

nav_back, nav_forward = st.columns(2)
with nav_back:
    if st.button("← Back to New migration", width="stretch"):
        switch_to(PAGE_NEW_MIGRATION)
with nav_forward:
    if mappings_finalized:
        if st.button(
            "Continue to Analysis & review →",
            type="primary",
            width="stretch",
            help="All column mappings are resolved or auto-approved.",
        ):
            switch_to(PAGE_ANALYSIS)
    elif blocking:
        st.caption("Resolve pending mapping reviews to unlock **Analysis & review**.")

st.caption("Rows highlighted in amber are **Needs review**. Expand a column below to change or ignore it.")

grouped: dict[str, list[dict]] = defaultdict(list)
for item in payload["mappings"]:
    grouped[item["source_file"]].append(item)

for source_file in sorted(grouped.keys()):
    items = sorted(grouped[source_file], key=lambda row: row["source_column"])
    review_count = sum(1 for item in items if item["review_required"])
    ignored_count = sum(1 for item in items if item["ignored"])

    with st.container(border=True):
        title_col, badge_col = st.columns([5, 2])
        with title_col:
            st.markdown(f"##### {source_file}")
            st.caption(
                f"{len(items)} columns"
                + (f" · {review_count} need review" if review_count else " · no review blockers")
                + (f" · {ignored_count} ignored" if ignored_count else "")
            )
        with badge_col:
            if review_count:
                st.error(f":material/error: {review_count} to review")
            else:
                st.success(":material/check_circle: File ready")

        st.dataframe(
            _file_overview_table(items),
            hide_index=True,
            width="stretch",
        )

        review_items = [item for item in items if item["review_required"]]
        if review_items:
            st.markdown("**Review these columns**")
            for item in review_items:
                _render_mapping_editor(migration, item)

        settled = [item for item in items if not item["review_required"]]
        if settled:
            with st.expander(f"Other columns in this file ({len(settled)})", expanded=False):
                for item in settled:
                    _render_mapping_editor(migration, item, compact=True)

if mappings_finalized:
    st.divider()
    if st.button("Continue to Analysis & review →", type="primary", width="stretch"):
        switch_to(PAGE_ANALYSIS)
