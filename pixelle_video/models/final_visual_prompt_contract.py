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
        object.__setattr__(self, "locked", _normalize_bool("locked", self.locked))
        object.__setattr__(
            self,
            "critic_check_required",
            _normalize_bool("critic_check_required", self.critic_check_required),
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
    contract_schema_version: str = "final_visual_prompt_contract.v4_4"

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

        object.__setattr__(
            self,
            "primary_visual_task",
            PrimaryVisualTask.from_value(self.primary_visual_task),
        )
        object.__setattr__(
            self,
            "visual_role_strategy",
            VisualRoleStrategy.from_value(self.visual_role_strategy),
        )
        object.__setattr__(
            self,
            "visible_text_policy",
            VisibleTextPolicy.from_value(self.visible_text_policy),
        )
        object.__setattr__(self, "required_subjects", _freeze_json_value("required_subjects", self.required_subjects))
        object.__setattr__(self, "identity_contract", _freeze_json_value("identity_contract", self.identity_contract))
        object.__setattr__(self, "weight_contract", _freeze_json_value("weight_contract", self.weight_contract))
        object.__setattr__(
            self,
            "projected_prompt_parts",
            _normalize_projected_prompt_parts(self.projected_prompt_parts),
        )
        object.__setattr__(self, "negative_semantics", _normalize_rule_tuple(self.negative_semantics))

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
        object.__setattr__(self, "metadata", dict(self.metadata or {}))
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
            "metadata": dict(self.metadata),
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
        object.__setattr__(self, "metadata", dict(self.metadata or {}))

    def with_prompt(self, prompt: str) -> "RenderedMediaPrompt":
        return replace(self, prompt=prompt)

    def to_dict(self) -> dict[str, Any]:
        return {
            "prompt": self.prompt,
            "negative_prompt": self.negative_prompt,
            "prompt_contract": self.prompt_contract.to_dict(),
            "renderer_id": self.renderer_id,
            "renderer_version": self.renderer_version,
            "metadata": dict(self.metadata),
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
    metadata = dict(contract.metadata)
    metadata["v44_contract"] = v44_contract.to_dict()
    return replace(contract, metadata=metadata)


def _require_non_empty(field_name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    return value.strip()


def _require_int(field_name: str, value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be an int")
    return value


def _normalize_bool(field_name: str, value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "t", "yes", "y", "1", "on"}:
            return True
        if normalized in {"false", "f", "no", "n", "0", "off"}:
            return False
    raise ValueError(f"{field_name} must be a bool or accepted boolean string")


def _optional_prompt(value: str) -> str | None:
    cleaned = value.strip()
    return cleaned or None


def _normalize_rule_tuple(values: Sequence[str]) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, str) or not isinstance(values, Sequence):
        raise ValueError("rules must be a list or tuple")
    return tuple(_dedupe(str(value).strip() for value in values if str(value).strip()))


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
        return value.value
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
    "FINAL_VISUAL_PROMPT_SECTION_KEYS",
    "FinalVisualPromptContract",
    "FinalVisualPromptContractV44",
    "ProjectedPromptPart",
    "RenderedMediaPrompt",
    "attach_v44_contract_metadata",
    "join_rendered_negative_prompts",
]
