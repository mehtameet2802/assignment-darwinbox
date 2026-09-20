from __future__ import annotations

import pytest

from ui.migration_picker import (
    _label_for_migration_id,
    apply_migration_from_picker,
    migration_selectbox_index,
    reset_migration_picker_widgets,
    sync_migration_selectbox,
)


class _Session(dict):
    def __getattr__(self, name):
        return self[name]

    def __setattr__(self, name, value):
        self[name] = value

    def keys(self):
        return super().keys()


@pytest.fixture
def session(monkeypatch):
    state = _Session(migration_id=None)
    monkeypatch.setattr("ui.migration_picker._session_state", lambda: state)
    return state


def test_selectbox_index_defaults_to_none_without_session() -> None:
    options = ["(none)", "MIG-1 • Demo (0 files)"]
    labels = {"MIG-1 • Demo (0 files)": 1}
    assert migration_selectbox_index(options, labels) == 0


def test_selectbox_index_selects_active_migration() -> None:
    options = ["(none)", "MIG-1 • A (0 files)", "MIG-2 • B (1 files)"]
    labels = {"MIG-1 • A (0 files)": 1, "MIG-2 • B (1 files)": 2}
    assert migration_selectbox_index(options, labels, migration_id=2) == 2


def test_sync_selectbox_sets_widget_state(session) -> None:
    session.migration_id = 2
    options = ["(none)", "MIG-1 • A (0 files)", "MIG-2 • B (1 files)"]
    labels = {"MIG-1 • A (0 files)": 1, "MIG-2 • B (1 files)": 2}
    sync_migration_selectbox("pick", options, labels)
    assert session["pick"] == "MIG-2 • B (1 files)"


def test_apply_migration_from_picker_updates_session(session) -> None:
    labels = {"MIG-1 • A (0 files)": 1, "MIG-2 • B (1 files)": 2}
    session["pick"] = "MIG-2 • B (1 files)"
    assert apply_migration_from_picker("pick", labels) == 2
    assert session.migration_id == 2


def test_apply_migration_from_picker_keeps_session_on_stale_widget_label(session) -> None:
    labels = {"MIG-1 • A (0 files)": 1}
    session.migration_id = 1
    session["pick"] = "MIG-99 • Old listing label (0 files)"
    assert apply_migration_from_picker("pick", labels) == 1
    assert session.migration_id == 1


def test_apply_migration_from_picker_switches_between_migrations(session) -> None:
    labels = {"MIG-1 • A (0 files)": 1, "MIG-2 • B (1 files)": 2}
    session.migration_id = 1
    session["pick"] = "MIG-2 • B (1 files)"
    assert apply_migration_from_picker("pick", labels) == 2
    session["pick"] = "MIG-1 • A (0 files)"
    assert apply_migration_from_picker("pick", labels) == 1


def test_label_for_migration_id_matches_listing() -> None:
    labels = {"MIG-1 • A (0 files)": 1, "MIG-1 • A (3 files)": 1}
    assert _label_for_migration_id(1, labels) in labels


def test_apply_migration_from_picker_survives_file_count_label_change(session) -> None:
    labels = {"MIG-1 • A (3 files)": 1}
    session.migration_id = 1
    session["pick"] = "MIG-1 • A (0 files)"
    assert apply_migration_from_picker("pick", labels) == 1
    assert session.migration_id == 1


def test_reset_migration_picker_widgets(session) -> None:
    session["active_migration_pick"] = "MIG-1 • A (0 files)"
    session["new_migration_active_pick"] = "MIG-2 • B (1 files)"
    reset_migration_picker_widgets()
    assert "active_migration_pick" not in session
    assert "new_migration_active_pick" not in session
