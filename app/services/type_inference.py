from __future__ import annotations

import re
from collections import Counter

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
DATE_RE = re.compile(
    r"^(\d{1,4}[-/]\d{1,2}[-/]\d{1,4}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4})"
    r"(\s+\d{1,2}:\d{2}(:\d{2})?)?$"
)
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}")
NUMBER_RE = re.compile(r"^-?\d{1,3}(,\d{3})*(\.\d+)?$|^-?\d+(\.\d+)?$")
BOOLEAN_VALUES = {
    "true",
    "false",
    "yes",
    "no",
    "y",
    "n",
    "1",
    "0",
}

SourceType = str  # email_like | date_like | number_like | boolean_like | string_like | unknown


def classify_value(raw: str) -> SourceType:
    value = raw.strip()
    if value == "":
        return "unknown"
    lowered = value.lower()
    if EMAIL_RE.match(lowered):
        return "email_like"
    if ISO_DATE_RE.match(value) or DATE_RE.match(value):
        return "date_like"
    if lowered in BOOLEAN_VALUES:
        return "boolean_like"
    if NUMBER_RE.match(value.replace(" ", "")):
        return "number_like"
    return "string_like"


def infer_column_type(samples: list[str], max_samples: int = 25) -> tuple[SourceType, list[str]]:
    """Infer probable source type from representative non-empty values."""
    display_samples: list[str] = []
    votes: Counter[str] = Counter()
    for raw in samples:
        if raw is None:
            continue
        text = str(raw).strip()
        if not text:
            continue
        if len(display_samples) < max_samples:
            display_samples.append(text)
        kind = classify_value(text)
        if kind != "unknown":
            votes[kind] += 1
    if not votes:
        return "unknown", display_samples
    top_kind, top_count = votes.most_common(1)[0]
    total = sum(votes.values())
    if top_count / total < 0.6:
        return "unknown", display_samples
    if len(votes) > 1 and votes.most_common(2)[1][1] / total > 0.25:
        return "unknown", display_samples
    return top_kind, display_samples
