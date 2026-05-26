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

    def render(self, contract: FinalVisualPromptContract, *, capabilities: Any = None) -> RenderedMediaPrompt:
        prompt = _render_compact_contract_prompt(contract, rendering_requirements=contract.negative_rules)
        return RenderedMediaPrompt(
            prompt=prompt,
            negative_prompt=None,
            prompt_contract=contract,
            renderer_id=self.renderer_id,
            renderer_version=self.renderer_version,
            metadata={
                "supports_negative_prompt": False,
                "provider_prompt_mode": "compact_z_image",
            },
        )


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


def _render_compact_contract_prompt(contract: FinalVisualPromptContract, *, rendering_requirements) -> str:
    """Render a shorter provider prompt for z-image.

    The full six-section contract remains stored in PromptPlan for audit, but z-image
    is more stable with a compact natural-language prompt than with long bracketed
    contract headings and internal role terminology.
    """
    parts = [
        _image_facing_text(contract.scene),
        _image_facing_text(contract.composition),
        _image_facing_relationship_clause(contract),
        _image_facing_text(contract.character_layer_style),
        _image_facing_text(contract.world_layer_style),
    ]
    requirements = _join_rules(_image_facing_requirements(rendering_requirements))
    if requirements:
        parts.append(f"Rendering requirements: {requirements}")
    return _clean_prompt(" ".join(str(part).strip() for part in parts if str(part or "").strip()))


def _image_facing_relationship_clause(contract: FinalVisualPromptContract) -> str:
    if not contract.metadata.get("ip_present"):
        return ""
    return (
        "IP角色作为画面中的协调配角融入同一场景，与主要角色共享空间、比例、透视和光线，"
        "有明确支撑点，比如站在地面、楼顶、桌边、电视旁、人群边缘、标牌旁或车辆旁，"
        "身体或脚与场景物体有接触或遮挡关系，不抢占画面主体，不像贴纸或独立吉祥物。"
    )


def _image_facing_text(value: str) -> str:
    text = str(value or "").strip()
    replacements = {
        "Apply visual styles by layer and target.": "",
        "Preserve clear boundaries between IP character layer, source subjects, world layer, props, and background.": "",
        "The IP character may be a scene-integrated supporting role, but the source subjects remain the main content.": "",
        "IP character layer": "IP角色",
        "human character layer": "角色",
        "source subjects": "文案主体",
        "non-IP world layer": "背景环境",
        "non-IP animals, props, background, and environment": "非IP动物、道具、背景和环境",
        "scene-integrated supporting character": "作为协调配角融入画面",
        "shares the same ground plane, scale, perspective, lighting, and atmosphere as the source scene": "与场景共享同一地面、比例、透视、光线和氛围",
        "not isolated, not floating, not a sticker, not pasted on top": "不是孤立漂浮的贴纸式元素",
        "coexists with the source subjects without replacing them": "与文案主体共处但不替代他们",
        "has a concrete physical placement anchor in the scene, such as standing on the ground, sitting beside a screen, standing on a rooftop, leaning near a board, or staying at the edge of a crowd": "有明确支撑点，如地面、楼顶、电视旁、讲解板旁或人群边缘",
        "the IP body or feet visibly contact a ground plane, surface, object, rooftop, table edge, signboard, or another physical support": "身体或脚与地面、物体或支撑面有可见接触",
        "if the source subject is flying, the IP remains grounded on a visible support unless the script explicitly says the IP is flying": "当主体在空中飞行时，IP默认站在地面、楼顶或前景支撑面上观看，除非文案明确要求IP飞行",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return " ".join(text.split())


def _image_facing_requirements(rules) -> tuple[str, ...]:
    result: list[str] = []
    for rule in rules or ():
        text = str(rule or "").strip()
        if not text:
            continue
        lowered = text.lower()
        if any(
            marker in lowered
            for marker in (
                "role slot",
                "not pasted",
                "not a sticker",
                "replace source",
                "source subjects remain",
            )
        ):
            continue
        if "不能变成蓝色兔子" in text or "blue rabbit" in lowered:
            result.append("科技兔子保持白色身体，只有蓝色领结作为身份锚点")
            continue
        if "不能替代" in text:
            continue
        result.append(_image_facing_text(text))
    return tuple(result)


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
