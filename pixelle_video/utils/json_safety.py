from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from enum import Enum
from typing import Any

JSONValue = None | bool | int | float | str | list["JSONValue"] | dict[str, "JSONValue"]


def to_json_compatible(value: Any, *, field_name: str = "value") -> JSONValue:
    """Return a detached JSON-compatible value or fail at the owning boundary."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{field_name} must not contain non-finite floats")
        return value
    if isinstance(value, Enum):
        return to_json_compatible(value.value, field_name=field_name)
    if isinstance(value, Mapping):
        return {
            str(key): to_json_compatible(item, field_name=f"{field_name}.{key}")
            for key, item in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [
            to_json_compatible(item, field_name=f"{field_name}[{index}]")
            for index, item in enumerate(value)
        ]
    raise TypeError(f"{field_name} must be JSON-compatible, got {type(value).__name__}")


__all__ = ["JSONValue", "to_json_compatible"]
