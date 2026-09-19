from __future__ import annotations

from ui.migration_picker import migration_selectbox_index, sync_migration_selectbox


def test_selectbox_index_defaults_to_none_without_session() -> None:
    options = ["(none)", "MIG-1 • Demo (0 files)"]
    labels = {"MIG-1 • Demo (0 files)": 1}
    assert migration_selectbox_index(options, labels) == 0


def test_selectbox_index_selects_active_migration() -> None:
    options = ["(none)", "MIG-1 • A (0 files)", "MIG-2 • B (1 files)"]
    labels = {"MIG-1 • A (0 files)": 1, "MIG-2 • B (1 files)": 2}
    assert migration_selectbox_index(options, labels, migration_id=2) == 2


def test_sync_selectbox_sets_widget_state(monkeypatch) -> None:
    import streamlit as st

    class _Session(dict):
        def __getattr__(self, name):
            return self[name]

        def __setattr__(self, name, value):
            self[name] = value

    session = _Session(migration_id=2)
    monkeypatch.setattr(st, "session_state", session)
    options = ["(none)", "MIG-1 • A (0 files)", "MIG-2 • B (1 files)"]
    labels = {"MIG-1 • A (0 files)": 1, "MIG-2 • B (1 files)": 2}
    sync_migration_selectbox("pick", options, labels)
    assert session["pick"] == "MIG-2 • B (1 files)"
