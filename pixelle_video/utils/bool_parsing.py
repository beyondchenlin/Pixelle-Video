from __future__ import annotations

from typing import Any


TRUE_STRINGS = frozenset({"1", "true", "yes", "y", "on", "enabled"})
FALSE_STRINGS = frozenset({"0", "false", "no", "n", "off", "disabled", ""})


def coerce_bool(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in TRUE_STRINGS:
            return True
        if normalized in FALSE_STRINGS:
            return False
    return bool(value)


__all__ = ["coerce_bool"]
