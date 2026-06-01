from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import Enum
from types import MappingProxyType
from typing import Any

from pixelle_video.models.visual_planning_mode import PrimaryVisualTask, VisibleTextPolicy
from pixelle_video.models.visual_role_strategy import VisualRoleStrategy

FINAL_VISUAL_PROMPT_SECTION_KEYS = (
    "scene",
    "composition",
    "style_assignment",
    "character_layer_style",
    "world_layer_style",
    "integration_priority",
)
FINAL_VISUAL_PROMPT_CONTRACT_V44_SCHEMA_VERSION = "final_visual_prompt_contract.v4_4"
V44_TRACE_METADATA_KEYS = (
    "contract_schema_version",
    "contract_id",
    "frame_id",
    "route_decision_id",
)


@dataclass(frozen=True)
class ProjectedPromptPart:
    part_id: str
    priority: int
    source_plan_type: str
    source_field: str
    content: str
    locked: bool
    critic_check_required: bool

    def __post_init__(self) -> None:
        for field_name in ("part_id", "source_plan_type", "source_field", "content"):
            object.__setattr__(self, field_name, _require_non_empty(field_name, getattr(self, field_name)))
        object.__setattr__(self, "priority", _require_int("priority", self.priority))
        object.__setattr__(self, "locked", _require_bool("locked", self.locked))
        object.__setattr__(
            self,
            "critic_check_required",
            _require_bool("critic_check_required", self.critic_check_required),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "part_id": self.part_id,
            "priority": self.priority,
            "source_plan_type": self.source_plan_type,
            "source_field": self.source_field,
            "content": self.content,
            "locked": self.locked,
            "critic_check_required": self.critic_check_required,
        }


@dataclass(frozen=True)
class FinalVisualPromptContractV44:
    contract_id: str
    frame_id: str
    primary_visual_task: PrimaryVisualTask | str
    article_anchor: str
    required_subjects: Any
    visual_concretization_summary: str
    identity_contract: Any
    visual_role_strategy: VisualRoleStrategy | str
    weight_contract: Any
    visible_text_policy: VisibleTextPolicy | str
    projected_prompt_parts: Sequence[ProjectedPromptPart]
    negative_semantics: Sequence[str]
    route_decision_id: str
    contract_schema_version: str = FINAL_VISUAL_PROMPT_CONTRACT_V44_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for field_name in (
            "contract_id",
            "frame_id",
            "article_anchor",
            "visual_concretization_summary",
            "route_decision_id",
            "contract_schema_version",
        ):
            object.__setattr__(self, field_name, _require_non_empty(field_name, getattr(self, field_name)))
        if self.contract_schema_version != FINAL_VISUAL_PROMPT_CONTRACT_V44_SCHEMA_VERSION:
            raise ValueError(
                "contract_schema_version must be "
                f"{FINAL_VISUAL_PROMPT_CONTRACT_V44_SCHEMA_VERSION}"
            )

        object.__setattr__(
            self,
            "primary_visual_task",
            _strict_enum_value("primary_visual_task", self.primary_visual_task, PrimaryVisualTask),
        )
        object.__setattr__(
            self,
            "visual_role_strategy",
            _strict_enum_value("visual_role_strategy", self.visual_role_strategy, VisualRoleStrategy),
        )
        object.__setattr__(
            self,
            "visible_text_policy",
            _strict_enum_value("visible_text_policy", self.visible_text_policy, VisibleTextPolicy),
        )
        object.__setattr__(self, "required_subjects", _freeze_json_value("required_subjects", self.required_subjects))
        object.__setattr__(self, "identity_contract", _freeze_json_value("identity_contract", self.identity_contract))
        object.__setattr__(self, "weight_contract", _freeze_json_value("weight_contract", self.weight_contract))
        object.__setattr__(
            self,
            "projected_prompt_parts",
            _normalize_projected_prompt_parts(self.projected_prompt_parts),
        )
        object.__setattr__(
            self,
            "negative_semantics",
            _normalize_strict_string_tuple("negative_semantics", self.negative_semantics),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_schema_version": self.contract_schema_version,
            "contract_id": self.contract_id,
            "frame_id": self.frame_id,
            "primary_visual_task": _serialize_enum_value(self.primary_visual_task),
            "article_anchor": self.article_anchor,
            "required_subjects": _thaw_json_value(self.required_subjects),
            "visual_concretization_summary": self.visual_concretization_summary,
            "identity_contract": _thaw_json_value(self.identity_contract),
            "visual_role_strategy": _serialize_enum_value(self.visual_role_strategy),
            "weight_contract": _thaw_json_value(self.weight_contract),
            "visible_text_policy": _serialize_enum_value(self.visible_text_policy),
            "projected_prompt_parts": [part.to_dict() for part in self.projected_prompt_parts],
            "negative_semantics": list(self.negative_semantics),
            "route_decision_id": self.route_decision_id,
        }


@dataclass(frozen=True)
class FinalVisualPromptContract:
    scene: str
    composition: str
    style_assignment: str
    character_layer_style: str
    world_layer_style: str
    integration_priority: str
    negative_rules: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    version: str = "final_visual_prompt_contract.v1"

    def __post_init__(self) -> None:
        for field_name in FINAL_VISUAL_PROMPT_SECTION_KEYS:
            object.__setattr__(self, field_name, _require_non_empty(field_name, getattr(self, field_name)))
        object.__setattr__(self, "negative_rules", _normalize_rule_tuple(self.negative_rules))
        object.__setattr__(self, "metadata", _freeze_metadata(self.metadata or {}))
        object.__setattr__(self, "version", _require_non_empty("version", self.version))

    def prompt_sections(self) -> dict[str, str]:
        return {key: getattr(self, key) for key in FINAL_VISUAL_PROMPT_SECTION_KEYS}

    def to_template_variables(self, *, rendering_requirements: Sequence[str] | None = None) -> dict[str, Any]:
        requirements = _normalize_rule_tuple(rendering_requirements or ())
        return {
            **self.prompt_sections(),
            "rendering_requirements": ", ".join(requirements),
        }

    def with_negative_rules(self, extra_rules: Sequence[str]) -> "FinalVisualPromptContract":
        return replace(
            self,
            negative_rules=tuple(_dedupe([*self.negative_rules, *extra_rules])),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            **self.prompt_sections(),
            "negative_rules": list(self.negative_rules),
            "metadata": _detach_metadata(self.metadata),
        }


@dataclass(frozen=True)
class RenderedMediaPrompt:
    prompt: str
    negative_prompt: str | None
    prompt_contract: FinalVisualPromptContract
    renderer_id: str
    renderer_version: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "prompt", _require_non_empty("prompt", self.prompt))
        if self.negative_prompt is not None:
            object.__setattr__(self, "negative_prompt", _optional_prompt(self.negative_prompt))
        object.__setattr__(self, "renderer_id", _require_non_empty("renderer_id", self.renderer_id))
        object.__setattr__(self, "renderer_version", _require_non_empty("renderer_version", self.renderer_version))
        object.__setattr__(
            self,
            "metadata",
            _freeze_metadata(_rendered_prompt_metadata(self.metadata or {}, self.prompt_contract)),
        )

    def with_prompt(self, prompt: str) -> "RenderedMediaPrompt":
        return replace(self, prompt=prompt)

    def to_dict(self) -> dict[str, Any]:
        return {
            "prompt": self.prompt,
            "negative_prompt": self.negative_prompt,
            "prompt_contract": self.prompt_contract.to_dict(),
            "renderer_id": self.renderer_id,
            "renderer_version": self.renderer_version,
            "metadata": _detach_metadata(self.metadata),
        }


def join_rendered_negative_prompts(rendered_prompts: Sequence[RenderedMediaPrompt]) -> str | None:
    rules: list[str] = []
    for rendered in rendered_prompts:
        if rendered.negative_prompt:
            rules.extend(_split_rule_string(rendered.negative_prompt))
    normalized = _dedupe(rules)
    return ", ".join(normalized) if normalized else None


def attach_v44_contract_metadata(
    contract: FinalVisualPromptContract,
    v44_contract: FinalVisualPromptContractV44,
) -> FinalVisualPromptContract:
    metadata = _detach_metadata(contract.metadata)
    v44_payload = v44_contract.to_dict()
    if "v44_contract" in metadata and metadata["v44_contract"] != v44_payload:
        raise ValueError("metadata v44_contract conflicts with v44_contract")
    metadata["v44_contract"] = v44_payload
    return replace(contract, metadata=metadata)


def _require_non_empty(field_name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    return value.strip()


def _require_int(field_name: str, value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be an int")
    return value


def _require_bool(field_name: str, value: Any) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field_name} must be a bool")
    return value


def _strict_enum_value(field_name: str, value: Any, enum_cls: type[Enum]) -> Enum:
    if isinstance(value, enum_cls):
        return value
    if isinstance(value, Enum):
        raise ValueError(f"{field_name} must be a valid {enum_cls.__name__}")
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a valid {enum_cls.__name__}")
    for item in enum_cls:
        if value == item.value or value == item.name:
            return item
    raise ValueError(f"{field_name} must be a valid {enum_cls.__name__}")


def _optional_prompt(value: str) -> str | None:
    cleaned = value.strip()
    return cleaned or None


def _normalize_rule_tuple(values: Sequence[str]) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, str) or not isinstance(values, Sequence):
        raise ValueError("rules must be a list or tuple")
    return tuple(_dedupe(str(value).strip() for value in values if str(value).strip()))


def _normalize_strict_string_tuple(field_name: str, values: Any) -> tuple[str, ...]:
    if isinstance(values, str) or not isinstance(values, Sequence):
        raise ValueError(f"{field_name} must be a list or tuple of non-empty strings")
    normalized: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field_name} must contain only non-empty strings")
        normalized.append(value.strip())
    return tuple(_dedupe(normalized))


def _split_rule_string(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in value.split(",") if part.strip())


def _dedupe(values: Sequence[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def _normalize_projected_prompt_parts(values: Any) -> tuple[ProjectedPromptPart, ...]:
    if isinstance(values, str) or not isinstance(values, Sequence):
        raise ValueError("projected_prompt_parts must be a list or tuple of ProjectedPromptPart")
    parts: list[ProjectedPromptPart] = []
    for value in values:
        if not isinstance(value, ProjectedPromptPart):
            raise ValueError("projected_prompt_parts must contain only ProjectedPromptPart")
        parts.append(value)
    return tuple(parts)


def _freeze_json_value(field_name: str, value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{field_name} must not contain non-finite floats")
        return value
    if isinstance(value, Enum):
        return _freeze_json_value(field_name, value.value)
    if isinstance(value, Mapping):
        frozen: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{field_name} mapping keys must be strings")
            frozen[key] = _freeze_json_value(field_name, item)
        return MappingProxyType(frozen)
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return tuple(_freeze_json_value(field_name, item) for item in value)
    raise ValueError(f"{field_name} must be JSON-safe")


def _detach_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    detached = _sanitize_metadata_mapping(metadata)
    return detached if isinstance(detached, dict) else {}


def _freeze_metadata(metadata: Mapping[str, Any]) -> Mapping[str, Any]:
    frozen = _freeze_json_value("metadata", _detach_metadata(metadata))
    if not isinstance(frozen, Mapping):
        return MappingProxyType({})
    return frozen


def _sanitize_metadata_mapping(metadata: Mapping[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in dict(metadata).items():
        if not isinstance(key, str):
            continue
        if key == "v44_contract":
            sanitized[key] = _sanitize_v44_contract_metadata(value)
            continue
        safe_value = _sanitize_metadata_value(value)
        if safe_value is not _UNSAFE_METADATA:
            sanitized[key] = safe_value
    return sanitized


_UNSAFE_METADATA = object()


def _sanitize_metadata_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else _UNSAFE_METADATA
    if isinstance(value, Enum):
        return _sanitize_metadata_value(value.value)
    if isinstance(value, Mapping):
        return _sanitize_metadata_mapping(value)
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        sanitized_items = []
        for item in value:
            safe_item = _sanitize_metadata_value(item)
            if safe_item is not _UNSAFE_METADATA:
                sanitized_items.append(safe_item)
        return sanitized_items
    return _UNSAFE_METADATA


def _sanitize_v44_contract_metadata(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("metadata v44_contract must be a mapping")
    payload = _thaw_json_value(_freeze_json_value("metadata v44_contract", value))
    if not isinstance(payload, dict):
        raise ValueError("metadata v44_contract must be a mapping")
    for key in V44_TRACE_METADATA_KEYS:
        item = payload.get(key)
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"metadata v44_contract.{key} must be a non-empty string")
        payload[key] = item.strip()
    if payload["contract_schema_version"] != FINAL_VISUAL_PROMPT_CONTRACT_V44_SCHEMA_VERSION:
        raise ValueError(
            "metadata v44_contract.contract_schema_version must be "
            f"{FINAL_VISUAL_PROMPT_CONTRACT_V44_SCHEMA_VERSION}"
        )
    return payload


def _rendered_prompt_metadata(
    metadata: Mapping[str, Any],
    prompt_contract: FinalVisualPromptContract,
) -> dict[str, Any]:
    rendered_metadata = _detach_metadata(metadata)
    trace_metadata = _v44_trace_metadata(prompt_contract.metadata)
    trace_summary = trace_metadata.get("v44_contract")
    if not trace_metadata:
        _reject_rendered_trace_without_contract(rendered_metadata)
    for key in V44_TRACE_METADATA_KEYS:
        if key not in trace_metadata:
            continue
        if key in rendered_metadata and rendered_metadata[key] != trace_metadata[key]:
            raise ValueError(f"metadata {key} conflicts with prompt_contract v44_contract")
        rendered_metadata[key] = trace_metadata[key]
    if isinstance(rendered_metadata.get("v44_contract"), Mapping):
        for key in V44_TRACE_METADATA_KEYS:
            if key not in trace_metadata:
                continue
            if rendered_metadata["v44_contract"].get(key) not in (None, trace_metadata[key]):
                raise ValueError(f"metadata v44_contract.{key} conflicts with prompt_contract v44_contract")
    if isinstance(trace_summary, Mapping):
        rendered_metadata["v44_contract"] = trace_summary
    return rendered_metadata


def _reject_rendered_trace_without_contract(metadata: Mapping[str, Any]) -> None:
    reserved_keys = [key for key in (*V44_TRACE_METADATA_KEYS, "v44_contract") if key in metadata]
    if reserved_keys:
        raise ValueError(
            "RenderedMediaPrompt V4.4 trace metadata must come from prompt_contract metadata: "
            + ", ".join(reserved_keys)
        )


def _v44_trace_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    v44_contract = metadata.get("v44_contract") if isinstance(metadata, Mapping) else None
    if v44_contract is None:
        return {}
    payload = _sanitize_v44_contract_metadata(v44_contract)
    summary = {key: payload[key] for key in V44_TRACE_METADATA_KEYS}
    trace: dict[str, Any] = dict(summary)
    trace["v44_contract"] = summary
    return trace


def _thaw_json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw_json_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json_value(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    return value


def _serialize_enum_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    return value


__all__ = [
    "FINAL_VISUAL_PROMPT_CONTRACT_V44_SCHEMA_VERSION",
    "FINAL_VISUAL_PROMPT_SECTION_KEYS",
    "FinalVisualPromptContract",
    "FinalVisualPromptContractV44",
    "ProjectedPromptPart",
    "RenderedMediaPrompt",
    "attach_v44_contract_metadata",
    "join_rendered_negative_prompts",
]
