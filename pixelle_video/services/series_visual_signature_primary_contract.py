from __future__ import annotations

import re
from typing import Any

PRIMARY_SUBJECT_SIGNALS = (
    "primary",
    "protagonist",
    "central visual subject",
    "\u6838\u5fc3\u4e3b\u4f53",
    "\u4e3b\u89d2",
    "\u753b\u9762\u4e2d\u5fc3",
    "\u4e3b\u8981\u884c\u52a8\u8005",
)

PRIMARY_SUBJECT_NEGATIONS = (
    "not primary",
    "not the primary",
    "not a primary",
    "non-primary",
    "not protagonist",
    "not the protagonist",
    "not central visual subject",
    "not the central visual subject",
    "secondary subject",
    "background subject",
    "\u4e0d\u662f\u6838\u5fc3\u4e3b\u4f53",
    "\u4e0d\u662f\u4e3b\u89d2",
    "\u975e\u6838\u5fc3\u4e3b\u4f53",
)

PRIMARY_SUBJECT_NEGATION_REPAIRS = (
    ("not the primary subject", "the primary subject"),
    ("not the primary", "the primary"),
    ("not primary", "primary"),
    ("not a primary", "a primary"),
    ("non-primary", "primary"),
    ("not the protagonist", "the protagonist"),
    ("not protagonist", "protagonist"),
    ("not the central visual subject", "the central visual subject"),
    ("not central visual subject", "central visual subject"),
    ("secondary subject", "primary subject"),
    ("background subject", "central visual subject"),
    ("\u4e0d\u662f\u6838\u5fc3\u4e3b\u4f53", "\u4f5c\u4e3a\u6838\u5fc3\u4e3b\u4f53"),
    ("\u4e0d\u662f\u4e3b\u89d2", "\u4f5c\u4e3a\u4e3b\u89d2"),
    ("\u975e\u6838\u5fc3\u4e3b\u4f53", "\u6838\u5fc3\u4e3b\u4f53"),
)

NON_PRIMARY_SUBJECT_SIGNALS = (
    "supporting observer",
    "supporting series visual signature",
    "secondary subject",
    "background subject",
    "beside the original",
    "beside the reader",
    "watches from the side",
    "side observer",
    "\u65c1\u89c2",
    "\u8f85\u52a9\u89d2\u8272",
    "\u80cc\u666f\u89d2\u8272",
)

NON_PRIMARY_SUBJECT_PATTERNS = (
    r"\b(observes?|observing|watches?|watching)\s+from\s+the\s+side\b",
    r"\b(looks?\s+on|looking\s+on|stands?\s+by|standing\s+by|guides?\s+quietly|guiding\s+quietly)\s+from\s+the\s+side\b",
)


def has_primary_subject_signal(*values: Any) -> bool:
    text = " ".join(str(value or "") for value in values).lower()
    if not text.strip():
        return False
    if any(pattern.lower() in text for pattern in PRIMARY_SUBJECT_NEGATIONS):
        return False
    return any(signal.lower() in text for signal in PRIMARY_SUBJECT_SIGNALS)


def has_non_primary_subject_signal(*values: Any) -> bool:
    text = " ".join(str(value or "") for value in values).lower()
    if not text.strip():
        return False
    return any(signal.lower() in text for signal in NON_PRIMARY_SUBJECT_SIGNALS) or any(
        re.search(pattern, text, flags=re.IGNORECASE)
        for pattern in NON_PRIMARY_SUBJECT_PATTERNS
    )


def repair_primary_subject_negations(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    for pattern, replacement in PRIMARY_SUBJECT_NEGATION_REPAIRS:
        text = re.sub(re.escape(pattern), replacement, text, flags=re.IGNORECASE)
    return text.strip()


__all__ = [
    "NON_PRIMARY_SUBJECT_SIGNALS",
    "NON_PRIMARY_SUBJECT_PATTERNS",
    "PRIMARY_SUBJECT_NEGATION_REPAIRS",
    "PRIMARY_SUBJECT_NEGATIONS",
    "PRIMARY_SUBJECT_SIGNALS",
    "has_non_primary_subject_signal",
    "has_primary_subject_signal",
    "repair_primary_subject_negations",
]
