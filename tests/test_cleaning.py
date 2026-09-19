from __future__ import annotations

import pytest

from app.services.cleaning import (
    clean_boolean,
    clean_email,
    clean_employee_id,
    clean_for_target_field,
    clean_number,
    clean_string,
    is_null_sentinel,
    normalize_null,
)


@pytest.mark.parametrize(
    "raw",
    ["", " ", "NULL", "null", "N/A", "NA", "None", "none", "-"],
)
def test_null_sentinels(raw: str) -> None:
    assert is_null_sentinel(raw)
    assert normalize_null(raw) is None


def test_real_string_not_null() -> None:
    assert not is_null_sentinel("McDonald")
    assert clean_string("McDonald").value == "McDonald"


def test_string_trim_and_collapse() -> None:
    assert clean_string("  Meet    Gopal   Mehta  ").value == "Meet Gopal Mehta"
    assert clean_for_target_field("first_name", "  Meet    Mehta ").value == "Meet Mehta"


def test_email_clean_and_validate() -> None:
    assert clean_email(" MEET@EXAMPLE.COM ").value == "meet@example.com"
    bad = clean_email("gmail.con")
    assert bad.ok is False
    assert bad.value == "gmail.con"


def test_employee_id_preserves_leading_zeros() -> None:
    assert clean_employee_id(" 00125 ").value == "00125"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("42", 42),
        ("42.0", 42),
        ("42.75", 42.75),
        ("1,250", 1250),
        ("-25", -25),
        (" 18.5 ", 18.5),
    ],
)
def test_number_valid(raw: str, expected: int | float) -> None:
    result = clean_number(raw)
    assert result.ok is True
    assert result.value == expected


@pytest.mark.parametrize(
    "raw",
    ["₹1,250", "12 years", "12 lakhs", "1.250,50", "abc"],
)
def test_number_invalid(raw: str) -> None:
    assert clean_number(raw).ok is False


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (" YES ", True),
        ("False", False),
        ("1", True),
        ("no", False),
    ],
)
def test_boolean_valid(raw: str, expected: bool) -> None:
    assert clean_boolean(raw).value is expected
    assert clean_boolean(raw).ok is True


@pytest.mark.parametrize("raw", ["active", "enabled", "checked", "maybe"])
def test_boolean_rejects_guesses(raw: str) -> None:
    assert clean_boolean(raw).ok is False
