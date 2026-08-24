from __future__ import annotations

import re
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

_CONTRACT_VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

_RESERVED_PROMPT_PROJECTION_METADATA_KEYS = frozenset({
    "image_text_plan",
    "ip_adaptation",
    "ip_profile",
    "provider_params",
    "provider",
    "provider_routing",
    "raw_provider_params",
    "raw_workflow",
    "routing",
    "workflow",
    "workflow_path",
})


@dataclass(frozen=True)
class ImagePromptDraft:
    image_prompt_draft_id: str
    storyboard_plan_id: str
    frame_id: str
    prompt_text: str
    source_trace_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    preserve_prompt_verbatim: bool = False

    def __post_init__(self) -> None:
        _require_bool("preserve_prompt_verbatim", self.preserve_prompt_verbatim)
        object.__setattr__(
            self,
            "image_prompt_draft_id",
            _require_non_empty("image_prompt_draft_id", self.image_prompt_draft_id),
        )
        object.__setattr__(
            self,
            "storyboard_plan_id",
            _require_non_empty("storyboard_plan_id", self.storyboard_plan_id),
        )
        object.__setattr__(self, "frame_id", _require_non_empty("frame_id", self.frame_id))
        object.__setattr__(
            self,
            "prompt_text",
            _verbatim_prompt(self.prompt_text)
            if self.preserve_prompt_verbatim
            else _require_non_empty("prompt_text", self.prompt_text),
        )
        object.__setattr__(self, "source_trace_id", _optional_str(self.source_trace_id))
        object.__setattr__(self, "metadata", _deep_freeze_mapping(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "image_prompt_draft_id": self.image_prompt_draft_id,
            "storyboard_plan_id": self.storyboard_plan_id,
            "frame_id": self.frame_id,
            "prompt_text": self.prompt_text,
            "source_trace_id": self.source_trace_id,
            "metadata": _json_safe_copy(self.metadata),
        }
        if self.preserve_prompt_verbatim:
            payload["preserve_prompt_verbatim"] = True
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ImagePromptDraft":
        if not isinstance(payload, Mapping):
            raise ValueError("ImagePromptDraft payload must be a mapping")
        return cls(
            image_prompt_draft_id=payload.get("image_prompt_draft_id", ""),
            storyboard_plan_id=payload.get("storyboard_plan_id", ""),
            frame_id=payload.get("frame_id", ""),
            prompt_text=payload.get("prompt_text", ""),
            source_trace_id=payload.get("source_trace_id"),
            metadata=payload.get("metadata") or {},
            preserve_prompt_verbatim=(
                payload.get("preserve_prompt_verbatim") is True
            ),
        )


@dataclass(frozen=True)
class PromptPlan:
    prompt_plan_id: str
    storyboard_plan_id: str
    frame_id: str
    image_prompt_draft_id: str
    prompt_sections: Mapping[str, str]
    final_prompt: str
    source_trace_id: str | None = None
    character_ids: tuple[str, ...] = ()
    scene_id: str | None = None
    prop_ids: tuple[str, ...] = ()
    style_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    final_negative_prompt: str | None = None
    identity_content_sha256: str | None = None
    contract_content_sha256: str | None = None
    contract_version: str | None = None
    preserve_prompt_verbatim: bool = False

    def __post_init__(self) -> None:
        _require_bool("preserve_prompt_verbatim", self.preserve_prompt_verbatim)
        object.__setattr__(self, "prompt_plan_id", _require_non_empty("prompt_plan_id", self.prompt_plan_id))
        object.__setattr__(
            self,
            "storyboard_plan_id",
            _require_non_empty("storyboard_plan_id", self.storyboard_plan_id),
        )
        object.__setattr__(self, "frame_id", _require_non_empty("frame_id", self.frame_id))
        object.__setattr__(
            self,
            "image_prompt_draft_id",
            _require_non_empty("image_prompt_draft_id", self.image_prompt_draft_id),
        )
        object.__setattr__(
            self,
            "prompt_sections",
            _freeze_prompt_sections_verbatim(self.prompt_sections)
            if self.preserve_prompt_verbatim
            else _freeze_prompt_sections(self.prompt_sections),
        )
        object.__setattr__(
            self,
            "final_prompt",
            _verbatim_prompt(self.final_prompt)
            if self.preserve_prompt_verbatim
            else _require_non_empty("final_prompt", self.final_prompt),
        )
        object.__setattr__(
            self,
            "final_negative_prompt",
            _optional_str(self.final_negative_prompt),
        )
        object.__setattr__(
            self,
            "identity_content_sha256",
            _optional_sha256("identity_content_sha256", self.identity_content_sha256),
        )
        object.__setattr__(
            self,
            "contract_content_sha256",
            _optional_sha256("contract_content_sha256", self.contract_content_sha256),
        )
        object.__setattr__(
            self,
            "contract_version",
            _optional_contract_version(self.contract_version),
        )
        if (self.contract_content_sha256 is None) != (self.contract_version is None):
            raise ValueError(
                "contract_content_sha256 and contract_version must be provided together"
            )
        if (
            self.identity_content_sha256 is not None
            and self.contract_content_sha256 is None
        ):
            raise ValueError(
                "identity_content_sha256 requires contract_content_sha256 and "
                "contract_version"
            )
        object.__setattr__(self, "source_trace_id", _optional_str(self.source_trace_id))
        object.__setattr__(self, "character_ids", _normalize_id_tuple("character_ids", self.character_ids))
        object.__setattr__(self, "scene_id", _optional_str(self.scene_id))
        object.__setattr__(self, "prop_ids", _normalize_id_tuple("prop_ids", self.prop_ids))
        object.__setattr__(self, "style_id", _optional_str(self.style_id))
        object.__setattr__(self, "metadata", _deep_freeze_mapping(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "prompt_plan_id": self.prompt_plan_id,
            "storyboard_plan_id": self.storyboard_plan_id,
            "frame_id": self.frame_id,
            "image_prompt_draft_id": self.image_prompt_draft_id,
            "prompt_sections": dict(self.prompt_sections),
            "final_prompt": self.final_prompt,
            "final_negative_prompt": self.final_negative_prompt,
            "identity_content_sha256": self.identity_content_sha256,
            "contract_content_sha256": self.contract_content_sha256,
            "contract_version": self.contract_version,
            "source_trace_id": self.source_trace_id,
            "character_ids": list(self.character_ids),
            "scene_id": self.scene_id,
            "prop_ids": list(self.prop_ids),
            "style_id": self.style_id,
            "metadata": _json_safe_copy(self.metadata),
        }
        if self.preserve_prompt_verbatim:
            payload["preserve_prompt_verbatim"] = True
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PromptPlan":
        if not isinstance(payload, Mapping):
            raise ValueError("PromptPlan payload must be a mapping")
        return cls(
            prompt_plan_id=payload.get("prompt_plan_id", ""),
            storyboard_plan_id=payload.get("storyboard_plan_id", ""),
            frame_id=payload.get("frame_id", ""),
            image_prompt_draft_id=payload.get("image_prompt_draft_id", ""),
            prompt_sections=payload.get("prompt_sections") or {},
            final_prompt=payload.get("final_prompt", ""),
            final_negative_prompt=payload.get("final_negative_prompt"),
            identity_content_sha256=payload.get("identity_content_sha256"),
            contract_content_sha256=payload.get("contract_content_sha256"),
            contract_version=payload.get("contract_version"),
            source_trace_id=payload.get("source_trace_id"),
            character_ids=tuple(payload.get("character_ids") or ()),
            scene_id=payload.get("scene_id"),
            prop_ids=tuple(payload.get("prop_ids") or ()),
            style_id=payload.get("style_id"),
            metadata=payload.get("metadata") or {},
            preserve_prompt_verbatim=(
                payload.get("preserve_prompt_verbatim") is True
            ),
        )


@dataclass(frozen=True)
class PromptProjection:
    prompt_plan_id: str
    frame_id: str
    final_prompt: str
    character_ids: tuple[str, ...] = ()
    scene_id: str | None = None
    prop_ids: tuple[str, ...] = ()
    style_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    preserve_prompt_verbatim: bool = False

    def __post_init__(self) -> None:
        _require_bool("preserve_prompt_verbatim", self.preserve_prompt_verbatim)
        object.__setattr__(self, "prompt_plan_id", _public_reference_id("prompt_plan_id", self.prompt_plan_id))
        object.__setattr__(self, "frame_id", _public_reference_id("frame_id", self.frame_id))
        object.__setattr__(
            self,
            "final_prompt",
            _verbatim_prompt(self.final_prompt)
            if self.preserve_prompt_verbatim
            else _require_non_empty("final_prompt", self.final_prompt),
        )
        object.__setattr__(self, "character_ids", _normalize_public_id_tuple("character_ids", self.character_ids))
        object.__setattr__(self, "scene_id", _optional_public_reference_id("scene_id", self.scene_id))
        object.__setattr__(self, "prop_ids", _normalize_public_id_tuple("prop_ids", self.prop_ids))
        object.__setattr__(self, "style_id", _optional_public_reference_id("style_id", self.style_id))
        object.__setattr__(self, "metadata", _freeze_projection_metadata(self.metadata))

    @classmethod
    def from_prompt_plan(
        cls,
        prompt_plan: PromptPlan,
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> "PromptProjection":
        return cls(
            prompt_plan_id=prompt_plan.prompt_plan_id,
            frame_id=prompt_plan.frame_id,
            final_prompt=prompt_plan.final_prompt,
            character_ids=prompt_plan.character_ids,
            scene_id=prompt_plan.scene_id,
            prop_ids=prompt_plan.prop_ids,
            style_id=prompt_plan.style_id,
            metadata=metadata or {},
            preserve_prompt_verbatim=prompt_plan.preserve_prompt_verbatim,
        )

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "prompt_plan_id": self.prompt_plan_id,
            "frame_id": self.frame_id,
            "final_prompt": self.final_prompt,
            "character_ids": list(self.character_ids),
            "scene_id": self.scene_id,
            "prop_ids": list(self.prop_ids),
            "style_id": self.style_id,
            "metadata": _json_safe_copy(self.metadata),
        }
        if self.preserve_prompt_verbatim:
            payload["preserve_prompt_verbatim"] = True
        return payload


@dataclass(frozen=True)
class PromptPlanBundle:
    storyboard_plan_id: str
    image_prompt_drafts: tuple[ImagePromptDraft, ...]
    prompt_plans: tuple[PromptPlan, ...]
    source_trace_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "storyboard_plan_id",
            _require_non_empty("storyboard_plan_id", self.storyboard_plan_id),
        )
        drafts = tuple(self.image_prompt_drafts)
        plans = tuple(self.prompt_plans)
        if not drafts:
            raise ValueError("image_prompt_drafts must not be empty")
        if len(drafts) != len(plans):
            raise ValueError("image_prompt_drafts and prompt_plans must have the same length")
        drafts_by_id = {draft.image_prompt_draft_id: draft for draft in drafts}
        for plan in plans:
            draft = drafts_by_id.get(plan.image_prompt_draft_id)
            if draft is None:
                raise ValueError("prompt_plans must reference bundle image_prompt_drafts")
            if plan.storyboard_plan_id != self.storyboard_plan_id:
                raise ValueError("prompt_plans must match bundle storyboard_plan_id")
            if draft.storyboard_plan_id != self.storyboard_plan_id:
                raise ValueError("image_prompt_drafts must match bundle storyboard_plan_id")
            if plan.frame_id != draft.frame_id:
                raise ValueError("prompt_plans must reference drafts from the same frame")
        object.__setattr__(self, "image_prompt_drafts", drafts)
        object.__setattr__(self, "prompt_plans", plans)
        object.__setattr__(self, "source_trace_id", _optional_str(self.source_trace_id))
        object.__setattr__(self, "metadata", _deep_freeze_mapping(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "storyboard_plan_id": self.storyboard_plan_id,
            "image_prompt_drafts": [
                draft.to_dict()
                for draft in self.image_prompt_drafts
            ],
            "prompt_plans": [
                plan.to_dict()
                for plan in self.prompt_plans
            ],
            "source_trace_id": self.source_trace_id,
            "metadata": _json_safe_copy(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PromptPlanBundle":
        if not isinstance(payload, Mapping):
            raise ValueError("PromptPlanBundle payload must be a mapping")
        return cls(
            storyboard_plan_id=payload.get("storyboard_plan_id", ""),
            image_prompt_drafts=tuple(
                ImagePromptDraft.from_dict(draft)
                for draft in payload.get("image_prompt_drafts") or ()
            ),
            prompt_plans=tuple(
                PromptPlan.from_dict(plan)
                for plan in payload.get("prompt_plans") or ()
            ),
            source_trace_id=payload.get("source_trace_id"),
            metadata=payload.get("metadata") or {},
        )


def _require_non_empty(field_name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    return value.strip()


def _require_bool(field_name: str, value: Any) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field_name} must be a boolean")
    return value


def _verbatim_prompt(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("verbatim prompts must be strings")
    return value


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("optional string fields must be strings")
    stripped = value.strip()
    return stripped or None


def _optional_sha256(field_name: str, value: Any) -> str | None:
    normalized = _optional_str(value)
    if normalized is None:
        return None
    lowered = normalized.lower()
    if len(lowered) != 64 or any(character not in "0123456789abcdef" for character in lowered):
        raise ValueError(f"{field_name} must be a 64-character SHA-256 hex digest")
    return lowered


def _optional_contract_version(value: Any) -> str | None:
    normalized = _optional_str(value)
    if normalized is None:
        return None
    if not _CONTRACT_VERSION_RE.fullmatch(normalized):
        raise ValueError(
            "contract_version must be a 1-128 character version identifier"
        )
    return normalized


def _freeze_prompt_sections(value: Mapping[str, str]) -> Mapping[str, str]:
    if not isinstance(value, Mapping) or not value:
        raise ValueError("prompt_sections must be a non-empty mapping")
    normalized = {}
    for key, item in value.items():
        normalized_key = _require_non_empty("prompt_sections key", key)
        normalized[normalized_key] = _require_non_empty(f"prompt_sections.{normalized_key}", item)
    return MappingProxyType(normalized)


def _freeze_prompt_sections_verbatim(
    value: Mapping[str, str],
) -> Mapping[str, str]:
    if not isinstance(value, Mapping) or not value:
        raise ValueError("prompt_sections must be a non-empty mapping")
    preserved = {}
    for key, item in value.items():
        normalized_key = _require_non_empty("prompt_sections key", key)
        preserved[normalized_key] = _verbatim_prompt(item)
    return MappingProxyType(preserved)


def _normalize_id_tuple(field_name: str, value: tuple[str, ...]) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{field_name} must be a list or tuple")
    normalized = tuple(_require_non_empty(field_name, item) for item in value)
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{field_name} must not contain duplicates")
    return normalized


def _normalize_public_id_tuple(field_name: str, value: tuple[str, ...]) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{field_name} must be a list or tuple")
    normalized = tuple(_public_reference_id(field_name, item) for item in value)
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{field_name} must not contain duplicates")
    return normalized


def _optional_public_reference_id(field_name: str, value: Any) -> str | None:
    if value is None:
        return None
    return _public_reference_id(field_name, value)


def _public_reference_id(field_name: str, value: Any) -> str:
    normalized = _require_non_empty(field_name, value)
    lowered = normalized.lower()
    if (
        ":\\" in normalized
        or "://" in normalized
        or ":" in normalized
        or "\\" in normalized
        or "/" in normalized
        or normalized in {".", ".."}
        or normalized.startswith("~")
        or ".." in normalized
        or lowered.startswith("workflows/")
    ):
        raise ValueError(f"{field_name} must be a public ID, not a path, URL, or workflow path")
    return normalized


def _freeze_projection_metadata(value: Mapping[str, Any]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("metadata must be a mapping")
    _validate_projection_metadata(value)
    return _deep_freeze_mapping(value)


def _validate_projection_metadata(value: Mapping[str, Any], *, path: str = "metadata") -> None:
    for key, item in value.items():
        key_text = str(key)
        if key_text.lower() in _RESERVED_PROMPT_PROJECTION_METADATA_KEYS:
            raise ValueError(f"metadata must not include raw or structured field: {key_text}")
        item_path = f"{path}.{key_text}"
        if isinstance(item, Mapping):
            _validate_projection_metadata(item, path=item_path)
        elif isinstance(item, (list, tuple)):
            for index, nested in enumerate(item):
                _validate_projection_metadata_value(nested, path=f"{item_path}[{index}]")
        else:
            _validate_projection_metadata_value(item, path=item_path)


def _validate_projection_metadata_value(value: Any, *, path: str) -> None:
    if isinstance(value, str):
        _reject_raw_provider_or_workflow_metadata_value(value, path=path)
        return
    if value is None or isinstance(value, (int, float, bool)):
        return
    if isinstance(value, Mapping):
        _validate_projection_metadata(value, path=path)
        return
    if isinstance(value, (list, tuple)):
        for index, nested in enumerate(value):
            _validate_projection_metadata_value(nested, path=f"{path}[{index}]")
        return
    raise ValueError(f"metadata value at {path} must be JSON-compatible")


def _reject_raw_provider_or_workflow_metadata_value(value: str, *, path: str) -> None:
    normalized = value.strip()
    lowered = normalized.lower()
    if not normalized:
        return
    if (
        lowered.startswith(("workflows/", "selfhost/", "runninghub/"))
        or "://" in lowered
        or "\\" in normalized
        or lowered.endswith(".json")
    ):
        raise ValueError(f"metadata value at {path} must not contain raw provider or workflow data")


def _deep_freeze_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("metadata must be a mapping")
    return MappingProxyType({
        str(key): _deep_freeze(item)
        for key, item in value.items()
    })


def _deep_freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _deep_freeze_mapping(value)
    if isinstance(value, (list, tuple)):
        return tuple(_deep_freeze(item) for item in value)
    return deepcopy(value)


def _json_safe_copy(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_safe_copy(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe_copy(item) for item in value]
    return deepcopy(value)


__all__ = [
    "ImagePromptDraft",
    "PromptPlan",
    "PromptPlanBundle",
    "PromptProjection",
]
