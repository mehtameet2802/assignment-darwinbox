from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from app.services.cleaning import CleanResult, is_null_sentinel

ISO_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
SLASH_DATE_RE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")

FORMAT_ISO = "ISO"
FORMAT_DMY = "DD/MM/YYYY"
FORMAT_MDY = "MM/DD/YYYY"
DATE_FORMAT_AMBIGUITY = "DATE_FORMAT_AMBIGUITY"


@dataclass
class DateParseResult:
    value: str | None
    ok: bool
    time_removed: bool = False
    error: str | None = None


def split_date_and_time(raw: str) -> tuple[str, bool]:
    text = raw.strip()
    time_removed = False
    if "T" in text:
        time_removed = True
        text = text.split("T", 1)[0]
    elif " " in text:
        parts = text.split(None, 1)
        if len(parts) == 2 and ":" in parts[1]:
            time_removed = True
        text = parts[0]
    return text, time_removed


def _fits_dmy(day: int, month: int, year: int) -> bool:
    try:
        date(year, month, day)
        return True
    except ValueError:
        return False


def _fits_mdy(month: int, day: int, year: int) -> bool:
    try:
        date(year, month, day)
        return True
    except ValueError:
        return False


def formats_for_date_part(date_part: str) -> set[str]:
    if ISO_DATE_RE.match(date_part):
        return {FORMAT_ISO}
    match = SLASH_DATE_RE.match(date_part)
    if not match:
        return set()
    a, b, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
    fits: set[str] = set()
    if _fits_dmy(a, b, year):
        fits.add(FORMAT_DMY)
    if _fits_mdy(a, b, year):
        fits.add(FORMAT_MDY)
    return fits


def analyze_date_column(samples: Iterable[str]) -> dict:
    """Column-level format detection. One ambiguity escalation per column when needed."""
    intersection: set[str] | None = None
    used_samples: list[str] = []
    for raw in samples:
        if is_null_sentinel(raw):
            continue
        date_part, _ = split_date_and_time(str(raw))
        fits = formats_for_date_part(date_part)
        if not fits:
            continue
        used_samples.append(str(raw).strip())
        intersection = fits if intersection is None else intersection & fits

    if intersection is None:
        return {
            "ambiguous": False,
            "chosen_format": None,
            "issue_type": None,
            "review_reason": None,
            "sample_values": used_samples,
        }
    if len(intersection) == 1:
        chosen = next(iter(intersection))
        return {
            "ambiguous": False,
            "chosen_format": chosen,
            "issue_type": None,
            "review_reason": None,
            "sample_values": used_samples,
        }
    return {
        "ambiguous": True,
        "chosen_format": None,
        "issue_type": DATE_FORMAT_AMBIGUITY,
        "review_reason": "Date format is ambiguous. Choose DD/MM/YYYY or MM/DD/YYYY for the entire column.",
        "sample_values": used_samples,
        "options": sorted(intersection),
    }


def parse_with_format(raw: str, column_format: str) -> DateParseResult:
    if is_null_sentinel(raw):
        return DateParseResult(value=None, ok=True)
    date_part, time_removed = split_date_and_time(str(raw))
    if column_format == FORMAT_ISO and ISO_DATE_RE.match(date_part):
        return DateParseResult(value=date_part, ok=True, time_removed=time_removed)

    match = SLASH_DATE_RE.match(date_part)
    if not match:
        if ISO_DATE_RE.match(date_part):
            return DateParseResult(value=date_part, ok=True, time_removed=time_removed)
        return DateParseResult(value=None, ok=False, time_removed=time_removed, error="Unrecognized date format.")

    a, b, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
    if column_format == FORMAT_DMY:
        if not _fits_dmy(a, b, year):
            return DateParseResult(value=None, ok=False, time_removed=time_removed, error="Invalid date for DD/MM/YYYY.")
        return DateParseResult(
            value=date(year, b, a).isoformat(),
            ok=True,
            time_removed=time_removed,
        )
    if column_format == FORMAT_MDY:
        if not _fits_mdy(a, b, year):
            return DateParseResult(value=None, ok=False, time_removed=time_removed, error="Invalid date for MM/DD/YYYY.")
        return DateParseResult(
            value=date(year, a, b).isoformat(),
            ok=True,
            time_removed=time_removed,
        )
    return DateParseResult(
        value=None,
        ok=False,
        time_removed=time_removed,
        error="Column date format is not resolved.",
    )


def parse_joining_date(raw: str, column_format: str | None) -> DateParseResult:
    if column_format is None:
        auto = analyze_date_column([raw])
        if auto["ambiguous"] or not auto["chosen_format"]:
            return DateParseResult(
                value=None,
                ok=False,
                error="Date column format must be resolved before parsing.",
            )
        column_format = auto["chosen_format"]
    return parse_with_format(raw, column_format)


def clean_joining_date(raw: str, column_format: str | None = None) -> CleanResult:
    parsed = parse_joining_date(raw, column_format)
    if not parsed.ok:
        return CleanResult(value=None, ok=False, error=parsed.error)
    return CleanResult(value=parsed.value, ok=True)
