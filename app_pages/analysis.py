from __future__ import annotations

import pandas as pd
import streamlit as st

from ui.api import api_get, api_patch, api_post, show_api_error
from ui.migration import require_migration_mappings_ready
from ui.navigation import PAGE_MAPPINGS, PAGE_PUSH, render_pipeline_stepper, switch_to

_SUCCESS_PHASES = {
    "full_processing",
    "revalidated_after_duplicate",
    "revalidated_after_validation",
}

st.caption(
    "Run one analysis pass. The system handles dates, transform, duplicates, and validation; "
    "you only see items that still need review."
)

migration = require_migration_mappings_ready("Select a migration that has completed mappings review.")
if migration is None:
    st.stop()

mid = migration["id"]
snapshot_key = f"analysis_snapshot_{mid}"


def _load_snapshot() -> dict | None:
    resp = api_get(f"/api/migrations/{mid}/analysis/snapshot")
    if resp.status_code != 200:
        return None
    snapshot = resp.json()
    cached = st.session_state.get(snapshot_key)
    if cached and cached.get("last_run"):
        snapshot["last_run"] = cached["last_run"]
    return snapshot


def _store_snapshot(payload: dict) -> None:
    st.session_state[snapshot_key] = payload


def _merge_snapshot(last_run: dict) -> None:
    resp = api_get(f"/api/migrations/{mid}/analysis/snapshot")
    if resp.status_code != 200:
        show_api_error(resp, "Could not load analysis snapshot.")
        return
    payload = resp.json()
    payload["last_run"] = last_run
    _store_snapshot(payload)


def _run_analysis() -> None:
    with st.status("Agent pipeline", expanded=True) as pipeline_status:
        st.write("Scanning mapped date columns…")
        scan = api_post(f"/api/migrations/{mid}/date-columns/scan", timeout=120)
        if scan.status_code != 201:
            show_api_error(scan, "Date column scan failed.")
            pipeline_status.update(label="Date scan failed", state="error")
            return
        date_payload = scan.json()
        blocking_dates = date_payload.get("blocking_count", 0)
        st.write(f"✓ Date scan complete ({blocking_dates} column(s) need confirmation)")
        if blocking_dates > 0:
            pipeline_status.update(label="Waiting on date format confirmation", state="complete")
            _merge_snapshot(
                {
                    "phase": "blocked_dates",
                    "message": "Date format must be confirmed before processing continues.",
                }
            )
            st.rerun()
            return

        st.write("Transforming source rows…")
        transform = api_post(f"/api/migrations/{mid}/transform", timeout=120)
        if transform.status_code != 201:
            show_api_error(transform, "Transform failed.")
            pipeline_status.update(label="Transform failed", state="error")
            return
        transform_payload = transform.json()
        created = transform_payload.get("records_created", 0)
        st.write(f"✓ Transformed {created} record(s)")

        st.write("Analyzing duplicates…")
        dupes = api_post(f"/api/migrations/{mid}/duplicates/analyze", timeout=120)
        if dupes.status_code != 201:
            show_api_error(dupes, "Duplicate analysis failed.")
            pipeline_status.update(label="Duplicate analysis failed", state="error")
            return
        dup_payload = dupes.json()
        exact = dup_payload.get("exact_duplicate_groups_collapsed", 0)
        conflicts = dup_payload.get("duplicate_conflicts", 0)
        st.write(
            f"✓ Duplicate scan complete ({exact} exact group(s) collapsed, {conflicts} conflict(s))"
        )

        st.write("Validating records…")
        validation = api_post(f"/api/migrations/{mid}/validate", timeout=120)
        if validation.status_code != 201:
            show_api_error(validation, "Validation failed.")
            pipeline_status.update(label="Validation failed", state="error")
            return
        val_payload = validation.json()
        st.write(
            f"✓ Validation complete ({val_payload.get('ready_to_push', 0)} ready, "
            f"{val_payload.get('validation_escalations', 0)} escalation(s))"
        )
        pipeline_status.update(label="Analysis pipeline complete", state="complete")

    _merge_snapshot(
        {
            "phase": "full_processing",
            "records_transformed": transform_payload.get("records_created", 0),
            "exact_duplicate_groups_handled": dup_payload.get("exact_duplicate_groups_collapsed", 0),
            "duplicate_conflicts_created": dup_payload.get("duplicate_conflicts", 0),
            "records_validated": val_payload.get("records_validated", 0),
            "ready_to_push": val_payload.get("ready_to_push", 0),
            "validation_escalations": val_payload.get("validation_escalations", 0),
        }
    )
    st.rerun()


def _continue_after(after: str) -> None:
    with st.spinner("Continuing analysis…"):
        resp = api_post(f"/api/migrations/{mid}/analysis/continue", json={"after": after}, timeout=300)
    if resp.status_code == 201:
        _store_snapshot(resp.json())
        st.rerun()
    else:
        show_api_error(resp, "Could not continue analysis.")


def _analysis_succeeded(last: dict) -> bool:
    return last.get("phase") in _SUCCESS_PHASES


def _source_labels(sources: list[dict]) -> list[str]:
    labels = []
    for src in sources:
        file_name = src.get("source_file") or "unknown file"
        row = src.get("source_row_number")
        labels.append(f"{file_name} (row {row})" if row is not None else file_name)
    return labels


def _member_column_title(index: int, member: dict) -> str:
    sources = _source_labels(member.get("sources") or [])
    source = sources[0] if sources else "Unknown source"
    return f"Record {index + 1} ({source})"


def _field_order_for_members(members: list[dict], differing_fields: list[str] | None) -> list[str]:
    differing = list(differing_fields or [])
    all_keys: set[str] = set()
    for member in members:
        all_keys.update((member.get("payload") or {}).keys())
    order = [k for k in differing if k in all_keys]
    order.extend(sorted(all_keys - set(order)))
    return order


def _cell_display(payload: dict, key: str) -> str:
    value = payload.get(key)
    if value is None or value == "":
        return "—"
    return str(value)


def _duplicate_comparison_vertical(members: list[dict], field_order: list[str]) -> pd.DataFrame:
    """Fields as rows, one column per record — best for two-way compare."""
    columns: dict[str, list[str]] = {}
    for idx, member in enumerate(members):
        payload = member.get("payload") or {}
        col_name = _member_column_title(idx, member)
        columns[col_name] = [_cell_display(payload, key) for key in field_order]
    if not columns:
        return pd.DataFrame({"Field": ["—"], "Record 1": ["—"]})
    df = pd.DataFrame(columns, index=field_order)
    return df.reset_index().rename(columns={"index": "Field"})


def _duplicate_comparison_table(members: list[dict], differing_fields: list[str] | None) -> pd.DataFrame:
    field_order = _field_order_for_members(members, differing_fields)
    return _duplicate_comparison_vertical(members, field_order)


def _payload_field_table(payload: dict, highlight_field: str | None = None) -> pd.DataFrame:
    rows: list[dict[str, str]] = []
    for key in sorted(payload.keys()):
        value = payload.get(key)
        if value is None or value == "":
            continue
        note = "Needs correction" if highlight_field and key == highlight_field else ""
        rows.append({"Field": key, "Value": str(value), "Note": note})
    if not rows:
        return pd.DataFrame([{"Field": "—", "Value": "—", "Note": ""}])
    return pd.DataFrame(rows)


def _validation_file_group_key(esc: dict) -> str:
    sources = esc.get("sources") or []
    if not sources:
        return "Source file unknown"
    files = list(dict.fromkeys(src.get("source_file") or "unknown" for src in sources))
    if len(files) == 1:
        return files[0]
    return " · ".join(files)


def _validation_source_rows_label(sources: list[dict]) -> str:
    labels = _source_labels(sources)
    return ", ".join(labels) if labels else "Row unknown"


render_pipeline_stepper(2)

if st.button("← Back to Mappings & review"):
    switch_to(PAGE_MAPPINGS)

if st.button("Run analysis", type="primary"):
    _run_analysis()

snapshot = _load_snapshot()
last = (snapshot or {}).get("last_run") or {}
issues = (snapshot or {}).get("issues_requiring_review", 0)
analysis_ok = _analysis_succeeded(last)

if snapshot is None:
    st.info("Click **Run analysis** to scan dates, transform rows, check duplicates, and validate records.")
    st.stop()

st.subheader("Completed steps")
if last.get("phase") == "blocked_dates":
    st.markdown("✓ Date column scan")
    st.markdown("⚠ Date format confirmation (waiting)")
elif analysis_ok:
    st.markdown("✓ Date column scan")
    if last.get("phase") == "full_processing":
        st.markdown(f"✓ Transform ({last.get('records_transformed', 0)} rows)")
        exact = last.get("exact_duplicate_groups_handled", 0)
        if exact:
            st.markdown(f"✓ Exact deduplication ({exact} group(s))")
        else:
            st.markdown("✓ Exact deduplication check")
        st.markdown("✓ Duplicate conflict scan")
        st.markdown("✓ Validation")
    elif last.get("phase") == "revalidated_after_duplicate":
        st.markdown("✓ Re-validated after duplicate resolution")
    elif last.get("phase") == "revalidated_after_validation":
        st.markdown("✓ Re-validated after validation correction")
else:
    st.caption("Run **Run analysis** to populate completed steps.")

st.subheader("Processing summary")
if not last:
    st.caption("Run **Run analysis** to refresh the processing summary.")
elif last.get("phase") == "blocked_dates":
    st.warning("Date format must be confirmed before processing can continue.")
elif last.get("phase") == "full_processing":
    st.markdown(f"✓ **{last.get('records_transformed', 0)}** rows transformed")
    exact = last.get("exact_duplicate_groups_handled", 0)
    if exact:
        st.markdown(f"✓ **{exact}** exact duplicate group(s) handled automatically")
    if snapshot.get("duplicate_blocking"):
        st.markdown(f"⚠ **{snapshot['duplicate_blocking']}** duplicate conflict(s) need review")
    if snapshot.get("validation_blocking"):
        st.markdown(f"⚠ **{snapshot['validation_blocking']}** validation issue(s) need review")
    if issues == 0:
        st.success("✓ Analysis complete — no issues requiring review.")
elif analysis_ok and issues == 0:
    st.success("✓ Analysis complete — no issues requiring review.")
else:
    st.caption("Review items below or run analysis again to refresh.")

if analysis_ok and issues == 0:
    st.divider()
    if st.button("Ready to push →", type="primary", width="stretch"):
        switch_to(PAGE_PUSH)
    st.stop()

if issues > 0:
    st.subheader("Needs review")
    counts = []
    if snapshot.get("date_blocking"):
        counts.append(f"Date format — {snapshot['date_blocking']}")
    if snapshot.get("duplicate_blocking"):
        counts.append(f"Duplicates — {snapshot['duplicate_blocking']}")
    if snapshot.get("validation_blocking"):
        counts.append(f"Validation — {snapshot['validation_blocking']}")
    st.markdown(" · ".join(counts))

date_payload = snapshot.get("dates") or {}
date_blocking = [e for e in date_payload.get("escalations", []) if e["status"] == "NEEDS_REVIEW"]
if date_blocking:
    st.markdown("#### Date format")
    for item in date_blocking:
        with st.container(border=True):
            st.markdown(f"**{item['source_file']}** · `{item['source_column']}` → joining_date")
            st.caption("Detected values:")
            st.write(", ".join(item["sample_values"][:8]))
            if item.get("suggested_format"):
                conf = item.get("suggestion_confidence")
                conf_label = f"{conf:.0%}" if conf is not None else "n/a"
                st.caption(f"Suggested: **{item['suggested_format']}** · Confidence: {conf_label}")
            fmt = st.selectbox(
                "Format",
                ["DD/MM/YYYY", "MM/DD/YYYY"],
                index=0 if (item.get("suggested_format") or "DD/MM/YYYY") == "DD/MM/YYYY" else 1,
                key=f"date_fmt_{item['id']}",
            )
            btn_accept, btn_confirm = st.columns(2)
            with btn_accept:
                if item.get("suggested_format") and st.button(
                    "Accept suggestion",
                    key=f"date_accept_{item['id']}",
                    width="stretch",
                ):
                    resp = api_patch(
                        f"/api/migrations/{mid}/date-escalations/{item['id']}",
                        json={"chosen_format": item["suggested_format"]},
                    )
                    if resp.status_code == 200:
                        _continue_after("date")
                    else:
                        show_api_error(resp, "Could not apply suggestion.")
            with btn_confirm:
                if st.button("Confirm", key=f"date_confirm_{item['id']}", type="primary", width="stretch"):
                    resp = api_patch(
                        f"/api/migrations/{mid}/date-escalations/{item['id']}",
                        json={"chosen_format": fmt},
                    )
                    if resp.status_code == 200:
                        _continue_after("date")
                    else:
                        show_api_error(resp, "Could not resolve date format.")

dup_payload = snapshot.get("duplicates") or {}
dup_blocking = [c for c in dup_payload.get("conflicts", []) if c["status"] == "NEEDS_REVIEW"]
if dup_blocking:
    st.markdown("#### Duplicate conflicts")
    for conflict in dup_blocking:
        with st.container(border=True):
            members = conflict["members"]
            differing = conflict.get("differing_fields") or []
            st.markdown(f"**Employee {conflict['employee_id']}** · {len(members)} conflicting record(s)")
            st.error(conflict["review_reason"])
            if differing:
                st.caption(f"Fields that differ: **{', '.join(differing)}**")
            st.caption("Each column is one duplicate source record; compare field values down the rows.")
            compare_df = _duplicate_comparison_table(members, differing)
            st.dataframe(compare_df, width="stretch", hide_index=True)
            base = dict(members[0]["payload"])
            edit_fields = conflict.get("differing_fields") or list(base.keys())
            st.markdown("**Resolve to final values**")
            for field in edit_fields:
                raw = base.get(field)
                st.text_input(
                    f"Final {field}",
                    value=str(raw) if raw is not None else "",
                    key=f"dup_{conflict['id']}_{field}",
                )
            if st.button("Save resolution", key=f"save_dup_{conflict['id']}", type="primary"):
                final_payload = dict(base)
                for field in edit_fields:
                    final_payload[field] = st.session_state.get(
                        f"dup_{conflict['id']}_{field}",
                        final_payload.get(field),
                    )
                resp = api_patch(
                    f"/api/migrations/{mid}/duplicate-conflicts/{conflict['id']}",
                    json={"action": "save", "final_payload": final_payload},
                )
                if resp.status_code == 200:
                    _continue_after("duplicate")
                else:
                    show_api_error(resp, "Could not save duplicate resolution.")

val_payload = snapshot.get("validation") or {}
val_blocking = [e for e in val_payload.get("escalations", []) if e["status"] == "NEEDS_REVIEW"]
if val_blocking:
    st.markdown("#### Validation")
    by_file: dict[str, list[dict]] = {}
    for esc in val_blocking:
        by_file.setdefault(_validation_file_group_key(esc), []).append(esc)
    for file_name in sorted(by_file.keys()):
        st.markdown(f"##### {file_name}")
        for esc in by_file[file_name]:
            with st.container(border=True):
                field_name = esc.get("field_name") or "value"
                current_payload = esc.get("current_payload") or {}
                source_line = _validation_source_rows_label(esc.get("sources") or [])
                st.markdown(f"**{esc['employee_id']}** — {esc['issue_type']}")
                st.caption(f"**Source row:** {source_line}")
                st.caption(esc["review_reason"])
                record_df = _payload_field_table(current_payload, highlight_field=field_name)
                st.dataframe(
                    record_df,
                    width="stretch",
                    hide_index=True,
                    column_config={
                        "Field": st.column_config.TextColumn("Field", width="small"),
                        "Value": st.column_config.TextColumn("Value", width="large"),
                        "Note": st.column_config.TextColumn("Note", width="small"),
                    },
                )
                current_value = current_payload.get(field_name)
                new_value = st.text_input(
                    f"Correct {field_name}",
                    value=str(current_value) if current_value is not None else "",
                    key=f"val_{field_name}_{esc['id']}",
                )
                save_col, ex_col = st.columns(2)
                with save_col:
                    if st.button("Save value", key=f"val_save_{esc['id']}", type="primary", width="stretch"):
                        saved_value = st.session_state.get(
                            f"val_{field_name}_{esc['id']}",
                            new_value,
                        )
                        resp = api_patch(
                            f"/api/migrations/{mid}/validation-escalations/{esc['id']}",
                            json={
                                "action": "enter_value",
                                "field_name": field_name,
                                "value": saved_value,
                            },
                        )
                        if resp.status_code == 200:
                            _continue_after("validation")
                        else:
                            show_api_error(resp, "Could not update record.")
                with ex_col:
                    if st.button("Exclude record", key=f"val_ex_{esc['id']}", width="stretch"):
                        resp = api_patch(
                            f"/api/migrations/{mid}/validation-escalations/{esc['id']}",
                            json={"action": "exclude"},
                        )
                        if resp.status_code == 200:
                            _continue_after("validation")
                        else:
                            show_api_error(resp, "Could not exclude record.")
