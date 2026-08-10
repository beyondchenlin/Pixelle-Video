from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from pixelle_video.architecture.legacy_signature_field_guard import (
    reject_deprecated_signature_fields,
)
from pixelle_video.models.series_visual_signature import SeriesVisualSignatureContract


@dataclass(frozen=True)
class FinalVisualPromptContractV45:
    """Provider-neutral V4.5 final visual prompt contract."""

    contract_id: str
    frame_id: str
    primary_visual_task: str
    required_subjects: Sequence[str]
    article_concretization: Mapping[str, Any] = field(default_factory=dict)
    series_visual_signature: SeriesVisualSignatureContract | Mapping[str, Any] = field(
        default_factory=SeriesVisualSignatureContract.disabled
    )
    diagram_render: Mapping[str, Any] = field(default_factory=dict)
    visible_text_policy: str = "no_visible_text"
    projected_prompt_parts: Sequence[Mapping[str, Any]] = field(default_factory=tuple)
    prompt_compiler_name: str = "FinalVisualPromptCompiler"

    def __post_init__(self) -> None:
        object.__setattr__(self, "contract_id", _require_text("contract_id", self.contract_id))
        object.__setattr__(self, "frame_id", _require_text("frame_id", self.frame_id))
        object.__setattr__(
            self,
            "primary_visual_task",
            _require_text("primary_visual_task", self.primary_visual_task),
        )
        object.__setattr__(
            self,
            "required_subjects",
            _text_tuple("required_subjects", self.required_subjects, allow_empty=True),
        )
        article_concretization = dict(self.article_concretization or {})
        diagram_render = dict(self.diagram_render or {})
        projected_parts = tuple(dict(part) for part in self.projected_prompt_parts or ())
        reject_deprecated_signature_fields(
            article_concretization,
            context="final visual prompt contract",
        )
        reject_deprecated_signature_fields(
            diagram_render,
            context="final visual prompt contract",
        )
        reject_deprecated_signature_fields(
            projected_parts,
            context="final visual prompt contract",
        )
        signature = SeriesVisualSignatureContract.from_mapping(
            self.series_visual_signature
        )
        object.__setattr__(
            self,
            "article_concretization",
            _freeze_json(article_concretization),
        )
        object.__setattr__(self, "series_visual_signature", signature)
        object.__setattr__(self, "diagram_render", _freeze_json(diagram_render))
        object.__setattr__(
            self,
            "visible_text_policy",
            _require_text("visible_text_policy", self.visible_text_policy),
        )
        object.__setattr__(
            self,
            "projected_prompt_parts",
            _freeze_json(projected_parts),
        )
        object.__setattr__(
            self,
            "prompt_compiler_name",
            _require_text("prompt_compiler_name", self.prompt_compiler_name),
        )

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "schema_version": "v4.5-signature",
            "contract_id": self.contract_id,
            "frame_id": self.frame_id,
            "primary_visual_task": self.primary_visual_task,
            "required_subjects": list(self.required_subjects),
            "article_concretization": _thaw_json(self.article_concretization),
            "series_visual_signature": self.series_visual_signature.to_dict(),
            "diagram_render": _thaw_json(self.diagram_render),
            "visible_text_policy": self.visible_text_policy,
            "projected_prompt_parts": _thaw_json(self.projected_prompt_parts),
            "prompt_compiler_name": self.prompt_compiler_name,
        }
        reject_deprecated_signature_fields(
            payload,
            context="final visual prompt contract",
        )
        return payload


def _require_text(field_name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return " ".join(value.strip().split())


def _text_tuple(
    field_name: str,
    values: Sequence[Any],
    *,
    allow_empty: bool,
) -> tuple[str, ...]:
    if values is None:
        values = ()
    if isinstance(values, str) or not isinstance(values, Sequence):
        raise ValueError(f"{field_name} must be a sequence of strings")
    result = tuple(_require_text(field_name, value) for value in values)
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
        if all(
            isinstance(item, tuple)
            and len(item) == 2
            and isinstance(item[0], str)
            for item in value
        ):
            return {key: _thaw_json(child) for key, child in value}
        return [_thaw_json(child) for child in value]
    return value
