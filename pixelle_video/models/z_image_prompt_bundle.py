from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from pixelle_video.architecture.legacy_signature_field_guard import (
    reject_deprecated_signature_fields,
)


@dataclass(frozen=True)
class ZImagePromptBundle:
    positive_prompt: str
    negative_prompt: str = ""
    locked_constraints: Sequence[str] = field(default_factory=tuple)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "positive_prompt", _require_text("positive_prompt", self.positive_prompt, max_chars=1200))
        object.__setattr__(self, "negative_prompt", _optional_text(self.negative_prompt, max_chars=800) or "")
        object.__setattr__(self, "locked_constraints", _text_tuple("locked_constraints", self.locked_constraints, allow_empty=True))
        metadata = dict(self.metadata or {})
        reject_deprecated_signature_fields(metadata, context="z-image prompt bundle metadata")
        object.__setattr__(self, "metadata", _freeze_json(metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "positive_prompt": self.positive_prompt,
            "negative_prompt": self.negative_prompt,
            "locked_constraints": list(self.locked_constraints),
            "metadata": _thaw_json(self.metadata),
        }


def _require_text(field_name: str, value: Any, *, max_chars: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    text = " ".join(value.strip().split())
    if len(text) > max_chars:
        raise ValueError(f"{field_name} must be <= {max_chars} characters")
    return text


def _optional_text(value: Any, *, max_chars: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("optional prompt text must be a string")
    text = " ".join(value.strip().split())
    if not text:
        return None
    if len(text) > max_chars:
        raise ValueError(f"optional prompt text must be <= {max_chars} characters")
    return text


def _text_tuple(field_name: str, values: Sequence[Any], *, allow_empty: bool) -> tuple[str, ...]:
    if values is None:
        values = ()
    if isinstance(values, str) or not isinstance(values, Sequence):
        raise ValueError(f"{field_name} must be a sequence of strings")
    result = tuple(_require_text(field_name, value, max_chars=300) for value in values)
    if not allow_empty and not result:
        raise ValueError(f"{field_name} must not be empty")
    return result


def _freeze_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return tuple(sorted((str(key), _freeze_json(child)) for key, child in value.items()))
    if isinstance(value, list | tuple):
        return tuple(_freeze_json(child) for child in value)
    return value


def _thaw_json(value: Any) -> Any:
    if isinstance(value, tuple):
        if all(isinstance(item, tuple) and len(item) == 2 and isinstance(item[0], str) for item in value):
            return {key: _thaw_json(child) for key, child in value}
        return [_thaw_json(child) for child in value]
    return value
