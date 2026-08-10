from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any


@dataclass(frozen=True)
class FinalVisualPromptBundle:
    """Provider- and media-neutral final visual prompt payload.

    This is the semantic boundary between Pixelle visual planning and concrete
    image/video provider adapters. Provider-specific field limits belong in the
    adapter; protected visual semantics belong here.
    """

    positive_prompt: str
    negative_prompt: str = ""
    locked_constraints: Sequence[str] = field(default_factory=tuple)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "positive_prompt",
            _require_text("positive_prompt", self.positive_prompt),
        )
        object.__setattr__(
            self,
            "negative_prompt",
            _optional_text(self.negative_prompt) or "",
        )
        object.__setattr__(
            self,
            "locked_constraints",
            _text_tuple("locked_constraints", self.locked_constraints),
        )
        object.__setattr__(self, "metadata", _freeze_json(dict(self.metadata or {})))

    def to_dict(self) -> dict[str, Any]:
        return {
            "positive_prompt": self.positive_prompt,
            "negative_prompt": self.negative_prompt,
            "locked_constraints": list(self.locked_constraints),
            "metadata": _thaw_json(self.metadata),
        }


def _require_text(field_name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return " ".join(value.strip().split())


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("optional prompt text must be a string")
    text = " ".join(value.strip().split())
    return text or None


def _text_tuple(field_name: str, values: Sequence[Any]) -> tuple[str, ...]:
    if values is None:
        values = ()
    if isinstance(values, str) or not isinstance(values, Sequence):
        raise ValueError(f"{field_name} must be a sequence of strings")
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _require_text(field_name, value)
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    return tuple(result)


def _freeze_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): _freeze_json(child) for key, child in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(child) for child in value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise ValueError(
        f"FinalVisualPromptBundle metadata must be JSON-compatible, got {type(value).__name__}"
    )


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw_json(child) for key, child in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(child) for child in value]
    return value


__all__ = ["FinalVisualPromptBundle"]
