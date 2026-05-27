from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from pixelle_video.models.base_visual_brief import BaseVisualBrief
from pixelle_video.models.final_visual_prompt_contract import FinalVisualPromptContract, RenderedMediaPrompt
from pixelle_video.models.visual_anchor_planning import VisualAnchorPlacementPlan


_FORBIDDEN_PROVIDER_TERMS = (
    "IP角色",
    "IP character",
    "visual anchor",
    "视觉锚点",
    "source subjects",
    "文案主体",
    "character layer",
    "world layer",
    "role_slot",
    "semantic_role",
    "placement_zone",
    "support_anchor",
    "style_relation",
    "Priority",
    "priority",
)


@dataclass(frozen=True)
class ProviderPromptProjector:
    renderer_id: str = "provider_prompt_projector_z_image"
    renderer_version: str = "v1"

    def project(
        self,
        *,
        base_visual_brief: BaseVisualBrief,
        visual_anchor_plan: VisualAnchorPlacementPlan | None = None,
        negative_rules: Sequence[str] = (),
        capabilities: Any = None,
        workflow: str | None = None,
    ) -> RenderedMediaPrompt:
        prompt = self._build_prompt(
            base_visual_brief=base_visual_brief,
            visual_anchor_plan=visual_anchor_plan,
            negative_rules=negative_rules if _is_positive_only(workflow, capabilities) else (),
        )
        negative_prompt = None if _is_positive_only(workflow, capabilities) else _join_rules(negative_rules)
        contract = FinalVisualPromptContract(
            scene=base_visual_brief.base_image_prompt,
            composition=_join_non_empty(base_visual_brief.spatial_layout, base_visual_brief.camera_plan, base_visual_brief.composition_rules) or "主体画面构图清晰",
            style_assignment=_join_non_empty(*base_visual_brief.subject_identity_anchors) or "主体视觉特征清楚",
            character_layer_style=visual_anchor_plan.image_prompt_clause if visual_anchor_plan and visual_anchor_plan.visible else "无额外频道视觉锚点",
            world_layer_style=base_visual_brief.style_surface or "画面风格与主体表达一致",
            integration_priority=_join_non_empty(*base_visual_brief.readability_constraints) or "画面可读性优先",
            negative_rules=tuple(negative_rules),
            metadata={
                "base_visual_brief_version": base_visual_brief.version,
                "visual_anchor_plan_version": visual_anchor_plan.version if visual_anchor_plan else None,
                "provider_prompt_projector": self.renderer_id,
                "ip_present": bool(visual_anchor_plan and visual_anchor_plan.visible),
            },
        )
        return RenderedMediaPrompt(
            prompt=prompt,
            negative_prompt=negative_prompt,
            prompt_contract=contract,
            renderer_id=self.renderer_id,
            renderer_version=self.renderer_version,
            metadata={"provider_prompt_mode": "image_facing_structured_projection"},
        )

    def _build_prompt(
        self,
        *,
        base_visual_brief: BaseVisualBrief,
        visual_anchor_plan: VisualAnchorPlacementPlan | None,
        negative_rules: Sequence[str],
    ) -> str:
        parts = [
            base_visual_brief.base_image_prompt,
            visual_anchor_plan.image_prompt_clause if visual_anchor_plan and visual_anchor_plan.visible else "",
            base_visual_brief.style_surface,
            _positive_readability_text(base_visual_brief.readability_constraints),
            _positive_requirements(negative_rules),
        ]
        return _sanitize_provider_prompt(" ".join(part.strip() for part in parts if part and part.strip()))


def _positive_readability_text(rules: Sequence[str]) -> str:
    positive_rules: list[str] = []
    for rule in rules:
        text = str(rule or "").strip()
        if not text:
            continue
        if _looks_like_negative_rule(text):
            converted = _negative_rule_to_positive_visual_requirement(text)
            if converted:
                positive_rules.append(converted)
            continue
        positive_rules.append(text)
    return "；".join(_dedupe(positive_rules))


def _positive_requirements(rules: Sequence[str]) -> str:
    if not rules:
        return ""
    converted: list[str] = []
    for rule in rules:
        text = str(rule or "").strip()
        if not text:
            continue
        positive = _negative_rule_to_positive_visual_requirement(text)
        if positive:
            converted.append(positive)
            continue
        if _looks_like_negative_rule(text):
            continue
        converted.append(text)
    return "；".join(_dedupe(converted))


def _looks_like_negative_rule(text: str) -> bool:
    lowered = text.lower()
    return any(
        token in lowered
        for token in (
            "不要",
            "不能",
            "避免",
            "禁止",
            "do not",
            "don't",
            "not ",
            "no ",
            "negative",
            "replace source",
            "source subjects",
        )
    )


def _negative_rule_to_positive_visual_requirement(text: str) -> str:
    lowered = text.lower()
    if "不能变成蓝色兔子" in text or "blue rabbit" in lowered:
        return "白色科技兔子保持白色身体，蓝色领结只是小面积识别点"
    if any(token in text for token in ("不能替代", "不要替代")) or "replace source" in lowered or "source subjects" in lowered:
        return "主要画面主体保持清晰可见，频道视觉元素不遮挡主体"
    if "不要给奥特曼添加红色披风" in text:
        return "奥特曼保持无披风的银红外星英雄造型"
    if "不要画成蓝色紧身衣人类英雄" in text:
        return "奥特曼保持银红外星英雄造型、椭圆黄色眼睛和胸前能量计时器"
    if "不要画成银色外星面具" in text or "不要画成奥特曼盔甲" in text or "不要使用椭圆黄色发光眼睛" in text:
        return "超人保持人类男性超级英雄造型、蓝色战衣、红色披风、胸前S标志和黑发"
    return ""


def _sanitize_provider_prompt(prompt: str) -> str:
    cleaned = " ".join(str(prompt or "").split())
    replacements = {
        "IP角色": "频道标志物",
        "文案主体": "主要画面主体",
        "source subjects": "main subjects",
        "character layer": "character",
        "world layer": "background",
    }
    for source, target in replacements.items():
        cleaned = cleaned.replace(source, target)
    for term in _FORBIDDEN_PROVIDER_TERMS:
        cleaned = cleaned.replace(term, "")
    return " ".join(cleaned.split()).strip()


def _is_positive_only(workflow: str | None, capabilities: Any) -> bool:
    workflow_text = (workflow or "").lower()
    if "z_image" in workflow_text or "z-image" in workflow_text:
        return True
    return not bool(getattr(capabilities, "supports_negative_prompt", False))


def _join_rules(rules: Sequence[str]) -> str | None:
    joined = "，".join(_dedupe(str(rule).strip() for rule in rules if str(rule).strip()))
    return joined or None


def _join_non_empty(*values: str) -> str:
    return "，".join(_dedupe(str(value).strip() for value in values if str(value or "").strip()))


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


__all__ = ["ProviderPromptProjector"]
