from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pixelle_video.models.final_visual_prompt_contract import (
    FinalVisualPromptContract,
    RenderedMediaPrompt,
)
from pixelle_video.prompts.template_loader import render_prompt_template


@dataclass(frozen=True)
class ModelPromptRenderer:
    renderer_id: str = "generic_negative_capable"
    renderer_version: str = "v1"

    def render(self, contract: FinalVisualPromptContract, *, capabilities: Any = None) -> RenderedMediaPrompt:
        negative_prompt = _join_rules(contract.negative_rules)
        prompt = _render_contract_prompt(contract, rendering_requirements=())
        return RenderedMediaPrompt(
            prompt=prompt,
            negative_prompt=negative_prompt,
            prompt_contract=contract,
            renderer_id=self.renderer_id,
            renderer_version=self.renderer_version,
            metadata={"supports_negative_prompt": bool(getattr(capabilities, "supports_negative_prompt", False))},
        )


@dataclass(frozen=True)
class PositiveOnlyPromptRenderer(ModelPromptRenderer):
    renderer_id: str = "positive_only_contract_renderer"
    renderer_version: str = "v1"

    def render(self, contract: FinalVisualPromptContract, *, capabilities: Any = None) -> RenderedMediaPrompt:
        prompt = _render_contract_prompt(contract, rendering_requirements=contract.negative_rules)
        return RenderedMediaPrompt(
            prompt=prompt,
            negative_prompt=None,
            prompt_contract=contract,
            renderer_id=self.renderer_id,
            renderer_version=self.renderer_version,
            metadata={"supports_negative_prompt": False},
        )


@dataclass(frozen=True)
class ZImagePromptRenderer(PositiveOnlyPromptRenderer):
    renderer_id: str = "z_image_positive_only_contract_renderer"
    renderer_version: str = "v1"


def select_model_prompt_renderer(*, workflow: str | None = None, capabilities: Any = None) -> ModelPromptRenderer:
    workflow_text = (workflow or "").lower()
    if "z_image" in workflow_text or "z-image" in workflow_text:
        return ZImagePromptRenderer()
    if bool(getattr(capabilities, "supports_negative_prompt", False)):
        return ModelPromptRenderer()
    return PositiveOnlyPromptRenderer()


def _render_contract_prompt(contract: FinalVisualPromptContract, *, rendering_requirements) -> str:
    rendered = render_prompt_template(
        "final_visual_prompt",
        contract.to_template_variables(rendering_requirements=rendering_requirements),
    )
    return _clean_prompt(rendered.text)


def _join_rules(rules) -> str | None:
    normalized = []
    seen = set()
    for rule in rules or ():
        text = str(rule or "").strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(text)
    return ", ".join(normalized) if normalized else None


def _clean_prompt(prompt: str) -> str:
    lines = [line.rstrip() for line in str(prompt or "").splitlines()]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines).strip()


__all__ = [
    "ModelPromptRenderer",
    "PositiveOnlyPromptRenderer",
    "ZImagePromptRenderer",
    "select_model_prompt_renderer",
]
