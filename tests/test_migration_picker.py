from __future__ import annotations

from ui.migration_picker import migration_selectbox_index


def test_selectbox_index_defaults_to_none_without_session() -> None:
    options = ["(none)", "MIG-1 • Demo (0 files)"]
    labels = {"MIG-1 • Demo (0 files)": 1}
    assert migration_selectbox_index(options, labels) == 0


def test_selectbox_index_selects_active_migration() -> None:
    options = ["(none)", "MIG-1 • A (0 files)", "MIG-2 • B (1 files)"]
    labels = {"MIG-1 • A (0 files)": 1, "MIG-2 • B (1 files)": 2}
    assert migration_selectbox_index(options, labels, migration_id=2) == 2
