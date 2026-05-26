from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any


FINAL_VISUAL_PROMPT_SECTION_KEYS = (
    "scene",
    "composition",
    "style_assignment",
    "character_layer_style",
    "world_layer_style",
    "integration_priority",
)


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


def _require_non_empty(field_name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    return value.strip()


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


__all__ = ["FINAL_VISUAL_PROMPT_SECTION_KEYS", "FinalVisualPromptContract", "RenderedMediaPrompt", "join_rendered_negative_prompts"]
