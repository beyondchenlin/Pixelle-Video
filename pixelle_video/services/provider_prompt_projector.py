from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from pixelle_video.models.asset_bible import IPProfile
from pixelle_video.models.base_visual_brief import BaseVisualBrief
from pixelle_video.models.final_visual_prompt_contract import (
    FinalVisualPromptContract,
    RenderedMediaPrompt,
)
from pixelle_video.models.series_visual_signature_strategy import (
    SeriesVisualSignatureStrategyControls,
)
from pixelle_video.models.visual_anchor_planning import VisualAnchorPlacementPlan
from pixelle_video.models.visual_signature_policy import VisualSignaturePolicy
from pixelle_video.services.final_prompt_ip_gate import (
    FinalPromptIPGateError,
    assert_mandatory_ip_final_prompt,
)
from pixelle_video.services.visual_anchor_projection_gate import validate_visual_anchor_projection
from pixelle_video.services.visual_signature_policy_loader import load_visual_signature_policy

_FORBIDDEN_PROVIDER_TERMS = (
    "IP角色",
    "IP character",
    "visual IP",
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
    "scale_ratio",
    "non-IP",
    "non ip",
    "history-teaching",
    "必须",
    "不要",
    "禁止",
    "不能",
)


class MandatoryIPProjectionError(ValueError):
    """Raised when mandatory IP participation cannot reach provider prompt output."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "mandatory_ip_projection_failed",
    ) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ProviderPromptProjector:
    renderer_id: str = "provider_prompt_projector_z_image"
    renderer_version: str = "v4_0_content_bound_ip"

    def project(
        self,
        *,
        base_visual_brief: BaseVisualBrief,
        anchor_profile: IPProfile | None = None,
        visual_anchor_plan: VisualAnchorPlacementPlan | None = None,
        negative_rules: Sequence[str] = (),
        capabilities: Any = None,
        workflow: str | None = None,
        visual_signature_policy: VisualSignaturePolicy | None = None,
        series_visual_signature_strategy: SeriesVisualSignatureStrategyControls | None = None,
    ) -> RenderedMediaPrompt:
        policy = visual_signature_policy or load_visual_signature_policy()
        projection_gate = validate_visual_anchor_projection(visual_anchor_plan, policy=policy)
        anchor_clause = projection_gate.anchor_clause if projection_gate.passed else ""
        content_bound_anchor_active = bool(
            anchor_clause and visual_anchor_plan is not None and policy.is_content_bound_mandatory
        )
        if policy.requires_every_frame_signature and policy.requires_repair_or_fail and not anchor_clause:
            raise MandatoryIPProjectionError(
                f"{base_visual_brief.frame_id}: mandatory IP participation was lost before provider projection",
                code=projection_gate.code,
            )
        if _is_positive_only(workflow, capabilities):
            prompt_negative_rules = (
                _content_bound_prompt_safe_negative_rules(negative_rules)
                if content_bound_anchor_active
                else tuple(negative_rules)
            )
        else:
            prompt_negative_rules = ()
        prompt = self._build_prompt(
            base_visual_brief=base_visual_brief,
            visual_anchor_plan=visual_anchor_plan,
            visual_anchor_clause=anchor_clause,
            negative_rules=prompt_negative_rules,
            policy=policy,
            content_bound_anchor_active=content_bound_anchor_active,
        )
        negative_prompt = None if _is_positive_only(workflow, capabilities) else _join_rules(negative_rules)
        try:
            final_gate = assert_mandatory_ip_final_prompt(
                prompt=prompt,
                anchor_clause=anchor_clause,
                visual_anchor_plan=visual_anchor_plan,
                policy=policy,
                anchor_profile=anchor_profile,
            )
        except FinalPromptIPGateError as exc:
            raise MandatoryIPProjectionError(
                f"{base_visual_brief.frame_id}: {exc}",
                code="final_prompt_ip_gate_failed",
            ) from exc
        contract_metadata = {
            "base_visual_brief_version": base_visual_brief.version,
            "visual_anchor_plan_version": visual_anchor_plan.version if visual_anchor_plan else None,
            "anchor_prominence": visual_anchor_plan.anchor_prominence.value if visual_anchor_plan else None,
            "provider_prompt_projector": self.renderer_id,
            "ip_present": bool(anchor_clause),
            "scene_bound_anchor_gate": "passed" if anchor_clause else "absent_or_rejected",
            "visual_signature_policy": policy.version,
            "visual_signature_coverage_mode": policy.coverage_mode,
            "mandatory_ip_final_gate": final_gate.to_dict(),
        }
        if series_visual_signature_strategy is not None:
            contract_metadata["series_visual_signature_strategy"] = series_visual_signature_strategy.to_dict()

        contract = FinalVisualPromptContract(
            scene=base_visual_brief.base_image_prompt,
            composition=_join_non_empty(
                base_visual_brief.spatial_layout,
                base_visual_brief.camera_plan,
                base_visual_brief.composition_rules,
            )
            or "主体画面构图清晰",
            style_assignment=_join_non_empty(*base_visual_brief.subject_identity_anchors)
            or "主体视觉特征清楚",
            character_layer_style=anchor_clause or ("" if policy.requires_every_frame_signature else "无额外频道视觉元素"),
            world_layer_style=base_visual_brief.style_surface or "画面风格与主体表达一致",
            integration_priority=_join_non_empty(*base_visual_brief.readability_constraints)
            or "画面可读性优先",
            negative_rules=tuple(negative_rules),
            metadata=contract_metadata,
        )
        return RenderedMediaPrompt(
            prompt=prompt,
            negative_prompt=negative_prompt,
            prompt_contract=contract,
            renderer_id=self.renderer_id,
            renderer_version=self.renderer_version,
            metadata={"provider_prompt_mode": "image_facing_visual_signature_projection_v3_2"},
        )

    def _build_prompt(
        self,
        *,
        base_visual_brief: BaseVisualBrief,
        visual_anchor_plan: VisualAnchorPlacementPlan | None,
        visual_anchor_clause: str,
        negative_rules: Sequence[str],
        policy: VisualSignaturePolicy,
        content_bound_anchor_active: bool,
    ) -> str:
        base_prompt = _strip_anchor_mentions_from_base_prompt(
            base_visual_brief.base_image_prompt,
            visual_anchor_plan=visual_anchor_plan,
        )
        prompt_guards = () if content_bound_anchor_active else (policy.positive_prompt_guards if visual_anchor_clause else ())
        parts = [
            base_prompt,
            visual_anchor_clause,
            _provider_style_clause(
                base_visual_brief.style_surface,
                base_prompt=base_prompt,
            ),
            _provider_scene_context_text(base_visual_brief),
            _positive_readability_text(base_visual_brief.readability_constraints),
            _positive_requirements(negative_rules),
            "；".join(prompt_guards),
        ]
        return _sanitize_provider_prompt(
            " ".join(part.strip() for part in parts if part and part.strip()),
            policy=policy,
        )


def _safe_visual_anchor_clause(
    visual_anchor_plan: VisualAnchorPlacementPlan | None,
    *,
    policy: VisualSignaturePolicy,
) -> str:
    result = validate_visual_anchor_projection(visual_anchor_plan, policy=policy)
    return result.anchor_clause if result.passed else ""


def _strip_anchor_mentions_from_base_prompt(
    base_prompt: str,
    *,
    visual_anchor_plan: VisualAnchorPlacementPlan | None,
) -> str:
    if not visual_anchor_plan or not visual_anchor_plan.visible:
        return str(base_prompt or "").strip()

    anchor_markers = _anchor_markers(visual_anchor_plan.image_prompt_clause)
    if not anchor_markers:
        return str(base_prompt or "").strip()

    chunks = re.split(r"([。；;!?！？])", str(base_prompt or ""))
    rebuilt: list[str] = []
    index = 0
    while index < len(chunks):
        chunk = chunks[index]
        punct = chunks[index + 1] if index + 1 < len(chunks) else ""
        sentence = chunk + punct
        if not _contains_any(sentence, anchor_markers):
            rebuilt.append(sentence)
        index += 2
    cleaned = "".join(rebuilt).strip()
    if cleaned:
        return cleaned

    clauses = re.split(r"([，,])", str(base_prompt or ""))
    rebuilt_clauses: list[str] = []
    index = 0
    while index < len(clauses):
        clause = clauses[index]
        sep = clauses[index + 1] if index + 1 < len(clauses) else ""
        if not _contains_any(clause, anchor_markers):
            rebuilt_clauses.append(clause + sep)
        index += 2
    return "".join(rebuilt_clauses).strip() or str(base_prompt or "").strip()


def _anchor_markers(anchor_text: str) -> tuple[str, ...]:
    markers: list[str] = []
    if "兔" in anchor_text:
        markers.extend(("白色科技兔子", "白色卡通兔子", "科技兔子", "卡通兔子", "蓝色领结", "蓝领结", "长耳朵", "圆润脸型"))
    if "麻雀" in anchor_text:
        markers.extend(("红嘴麻雀", "麻雀"))
    return tuple(_dedupe(markers))


def _image_facing_style_surface(style_surface: str, *, base_prompt: str = "") -> str:
    text = f"{style_surface or ''} {base_prompt or ''}".lower()
    clauses: list[str] = []
    if any(token in text for token in ("flat monochrome", "monochrome", "black-and-white", "黑白", "单色", "灰", "line art", "线条", "扁平")):
        clauses.append("黑白灰扁平插画，线条简洁，二维无纹理，背景简洁")
    elif any(token in text for token in ("storybook", "hand-painted", "插画", "绘本")):
        clauses.append("柔和插画风格，光线自然，构图清晰")
    if any(token in text for token in ("minimal", "negative space", "简洁", "留白")):
        clauses.append("画面保留留白，避免杂乱细节")
    return "，".join(_dedupe(clauses))


def _provider_style_clause(style_surface: str, *, base_prompt: str) -> str:
    """Project one provider-facing style clause without re-deriving it twice."""

    explicit_style = _provider_style_surface_text(style_surface)
    if explicit_style:
        return explicit_style
    return _image_facing_style_surface("", base_prompt=base_prompt)


def _provider_style_surface_text(style_surface: str) -> str:
    text = str(style_surface or "").strip()
    if not text:
        return ""
    text = re.sub(
        r"\bnon-IP world layer,\s*non-IP animals,\s*props,\s*background,\s*and environment:\s*",
        "",
        text,
    )
    replacements = {
        "non-IP world layer:": "",
        "non-IP world layer,": "",
        "non-IP animals, props, background, and environment:": "",
        "non-IP animals:": "",
        "non-IP": "background",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return text


def _provider_scene_context_text(base_visual_brief: BaseVisualBrief) -> str:
    props = ", ".join(base_visual_brief.key_props_symbols)
    text = _join_non_empty(
        base_visual_brief.camera_plan,
        f"environment includes {props}" if props else "",
    )
    return re.sub(r"[_-]+", " ", text)


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


def _content_bound_prompt_safe_negative_rules(rules: Sequence[str]) -> tuple[str, ...]:
    safe_rules: list[str] = []
    for rule in rules:
        text = str(rule or "").strip()
        if not text:
            continue
        if _looks_like_content_bound_internal_rule(text):
            continue
        safe_rules.append(text)
    return tuple(safe_rules)


def _looks_like_content_bound_internal_rule(text: str) -> bool:
    lowered = text.lower()
    return any(
        token in lowered
        for token in (
            "ip",
            "visual signature",
            "visual anchor",
            "policy",
            "forbidden",
            "must",
            "do not",
            "don't",
            "sticker",
            "corner badge",
            "watermark",
            "bookmark",
            "bookplate",
            "surface graphic",
            "printed mark",
            "视觉签名",
            "视觉锚点",
            "贴纸",
            "角标",
            "水印",
            "书签",
            "藏书票",
            "表面图案",
            "禁止",
            "不要",
            "不能",
        )
    )


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
            "avoid",
            "negative",
            "excessive",
            "gradient",
            "complex background",
            "detailed background",
            "replace source",
            "source subjects",
        )
    )


def _negative_rule_to_positive_visual_requirement(text: str) -> str:
    lowered = text.lower()
    if "不能变成蓝色兔子" in text or "blue rabbit" in lowered:
        return "白色科技兔子保持白色身体，蓝色领结只是小面积识别点"
    if any(token in text for token in ("不能替代", "不要替代")) or "replace source" in lowered or "source subjects" in lowered:
        return "主要画面主体保持清晰可见，辅助角色动作服务内容表达"
    if "不要给奥特曼添加红色披风" in text:
        return "奥特曼保持无披风的银红外星英雄造型"
    if "不要画成蓝色紧身衣人类英雄" in text:
        return "奥特曼保持银红外星英雄造型、椭圆黄色眼睛和胸前能量计时器"
    if "不要画成银色外星面具" in text or "不要画成奥特曼盔甲" in text or "不要使用椭圆黄色发光眼睛" in text:
        return "超人保持人类男性超级英雄造型、蓝色战衣、红色披风、胸前S标志和黑发"
    if "no visible text" in lowered or "no chinese characters" in lowered or "no english letters" in lowered:
        return "画面通过物体、构图和符号表达内容，表面保持干净完整"

    style_requirements: list[str] = []
    if (
        "excessive color" in lowered
        or "excessive use of color" in lowered
        or lowered.strip(" .;,") in {"color", "colour"}
    ):
        style_requirements.append("使用克制且一致的配色")
    if "gradient" in lowered:
        style_requirements.append("使用平整色块")
    if "complex texture" in lowered:
        style_requirements.append("使用平面线条和无纹理表面")
    if "complex background" in lowered or "detailed background" in lowered:
        style_requirements.append("背景简洁、低细节")
    if "simplicity and clarity" in lowered:
        style_requirements.append("构图简洁清晰")
    if style_requirements:
        return "，".join(_dedupe(style_requirements))
    return ""


def _sanitize_provider_prompt(prompt: str, *, policy: VisualSignaturePolicy) -> str:
    cleaned = " ".join(str(prompt or "").split())
    replacements = {
        "IP角色": "角色",
        "视觉IP": "角色",
        "visual IP": "character",
        "文案主体": "主要画面主体",
        "source subjects": "main subjects",
        "character layer": "character",
        "world layer": "background",
    }
    for source, target in replacements.items():
        cleaned = cleaned.replace(source, target)
    for term in _FORBIDDEN_PROVIDER_TERMS:
        cleaned = cleaned.replace(term, "")
    cleaned = re.sub(r"\bIP\b", "", cleaned)
    cleaned = re.sub(r"(?i)\bmust\b|\bdo not\b|\bforbidden\b|\bpolicy\b|\brule\b", "", cleaned)
    cleaned = re.sub(r"\bhistory-teaching[^，。;；]*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bnon[- ]?IP[^，。;；]*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\d+\s*%\s*(到|至|-|~)?\s*\d*\s*%?", "", cleaned)
    cleaned = " ".join(cleaned.split()).strip()
    if policy.contains_forbidden_overlay_text(cleaned):
        cleaned = _remove_sentences_with_forbidden_terms(cleaned, policy=policy, overlay_only=True)
    return cleaned


def _remove_sentences_with_forbidden_terms(text: str, *, policy: VisualSignaturePolicy, overlay_only: bool = False) -> str:
    sentences = re.split(r"([。；;!?！？])", text)
    kept: list[str] = []
    index = 0
    while index < len(sentences):
        sentence = sentences[index]
        punct = sentences[index + 1] if index + 1 < len(sentences) else ""
        combined = sentence + punct
        blocked = policy.contains_forbidden_overlay_text(combined) if overlay_only else policy.contains_forbidden_final_prompt_text(combined)
        if combined.strip() and not blocked:
            kept.append(combined)
        index += 2
    return "".join(kept).strip() or text


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


def _contains_any(text: str, values: Sequence[str]) -> bool:
    return any(value and value in text for value in values)


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


__all__ = ["MandatoryIPProjectionError", "ProviderPromptProjector"]
