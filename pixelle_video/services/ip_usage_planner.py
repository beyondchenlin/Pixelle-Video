from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pixelle_video.models.asset_bible import IPProfile
from pixelle_video.models.ip_prompt_planning import (
    IPFrameAdaptationPackage,
    IPImageTextPlan,
    IPPresenceType,
)
from pixelle_video.models.storyboard_plan import StoryboardPlan, StoryboardPlanFrame
from pixelle_video.models.style_resolution import ResolvedStyleSpec

ResolvedStyleInput = Mapping[str, Any] | ResolvedStyleSpec | None


class IPUsagePlanner:
    """Deterministic per-frame IP presence planner for prompt context building."""

    def plan_batch(
        self,
        *,
        storyboard_plan: StoryboardPlan,
        ip_profile: IPProfile,
        resolved_style: ResolvedStyleInput = None,
        scene_casts_by_frame: Mapping[str, Any] | None = None,
    ) -> list[IPFrameAdaptationPackage]:
        scene_casts = scene_casts_by_frame or {}
        return [
            self.plan_frame(
                frame=frame,
                ip_profile=ip_profile,
                resolved_style=resolved_style,
                scene_cast=_scene_cast_for_frame(scene_casts, frame),
            )
            for frame in storyboard_plan.frames
        ]

    def plan_frame(
        self,
        *,
        frame: StoryboardPlanFrame,
        ip_profile: IPProfile,
        resolved_style: ResolvedStyleInput = None,
        scene_cast: Any | None = None,
    ) -> IPFrameAdaptationPackage:
        frame_text = _frame_text(frame)
        presence_type = _presence_type_for_frame(
            frame=frame,
            frame_text=frame_text,
            ip_profile=ip_profile,
            resolved_style=resolved_style,
            scene_cast=scene_cast,
        )
        landmark_terms = _landmark_terms(frame)
        image_text_plan = _image_text_plan(frame, ip_profile, landmark_terms)

        return IPFrameAdaptationPackage(
            frame_id=frame.frame_id,
            ip_presence_type=presence_type,
            presence_mode=_presence_mode(presence_type),
            semantic_reason=_semantic_reason(presence_type),
            must_not_replace=tuple(landmark_terms),
            identity_anchors_visible=_visible_anchors(presence_type, ip_profile),
            identity_anchors_suppressed=_suppressed_anchors(presence_type, ip_profile),
            identity_color_terms=_identity_color_terms(ip_profile),
            action=_action_for_presence(presence_type),
            expression=_expression_for_presence(presence_type),
            camera_relationship=_camera_relationship_for_presence(presence_type),
            depth_layer=_depth_layer_for_presence(presence_type),
            interaction_target=landmark_terms[0] if landmark_terms else None,
            shot_fit_notes=_shot_fit_notes(presence_type),
            image_text_plan=image_text_plan,
            prompt_weight=_prompt_weight(presence_type),
            negative_constraints=_negative_constraints(ip_profile, presence_type),
        )


def _scene_cast_for_frame(scene_casts: Mapping[str, Any], frame: StoryboardPlanFrame) -> Any | None:
    return scene_casts.get(frame.frame_id) or scene_casts.get(str(frame.index))


def _frame_text(frame: StoryboardPlanFrame) -> str:
    parts = [
        frame.source_text,
        frame.visual_goal,
        frame.prompt_intent,
        frame.shot_type,
        frame.shot_purpose,
        frame.primary_subject,
        *frame.secondary_subjects,
        *frame.continuity_anchors,
        *frame.world_elements,
    ]
    return " ".join(part for part in parts if part)


def _presence_type_for_frame(
    *,
    frame: StoryboardPlanFrame,
    frame_text: str,
    ip_profile: IPProfile,
    resolved_style: ResolvedStyleInput,
    scene_cast: Any | None,
) -> IPPresenceType:
    scene_cast_presence = _presence_type_from_scene_cast(scene_cast)
    if scene_cast_presence is not None:
        return scene_cast_presence
    if _contains_any(frame_text, _PROTECTED_SUBJECT_KEYWORDS):
        return IPPresenceType.LOW_INTRUSION
    if _style_is_serious_documentary(resolved_style):
        return IPPresenceType.LOW_INTRUSION
    if _contains_any(frame_text, _PURE_LANDSCAPE_KEYWORDS) and not _contains_any(frame_text, _NARRATIVE_KEYWORDS):
        return IPPresenceType.SYMBOLIC_ONLY
    if _is_ip_hero_frame(frame_text, ip_profile):
        return IPPresenceType.STRONG_IDENTITY
    if _is_opening_or_establishing_frame(frame, frame_text):
        return IPPresenceType.SCENE_INTEGRATED
    if _contains_any(frame_text, _NARRATIVE_KEYWORDS):
        return IPPresenceType.BALANCED_NARRATIVE
    return IPPresenceType.BALANCED_NARRATIVE


def _presence_type_from_scene_cast(scene_cast: Any | None) -> IPPresenceType | None:
    if not isinstance(scene_cast, Mapping):
        return None
    value = scene_cast.get("ip_presence_type") or scene_cast.get("presence_type")
    if value is None:
        metadata = scene_cast.get("metadata")
        if isinstance(metadata, Mapping):
            value = metadata.get("ip_presence_type") or metadata.get("presence_type")
    if value is None:
        return None
    try:
        return IPPresenceType(value)
    except ValueError:
        return None


def _style_is_serious_documentary(resolved_style: ResolvedStyleInput) -> bool:
    positive_style_text = _positive_style_signal_text(resolved_style)
    if not positive_style_text:
        return False
    return _contains_any(positive_style_text.lower(), _SERIOUS_STYLE_KEYWORDS)


def _positive_style_signal_text(resolved_style: ResolvedStyleInput) -> str:
    if isinstance(resolved_style, Mapping):
        return _mapping_positive_style_signal_text(resolved_style)
    values = [
        getattr(resolved_style, "style_kind", None),
        getattr(resolved_style, "prompt_template", None),
    ]
    style_profile = getattr(resolved_style, "style_profile", None)
    if isinstance(style_profile, Mapping):
        values.append(_mapping_positive_style_signal_text(style_profile))
    return " ".join(_flatten_mapping_text(value) for value in values if value)


def _mapping_positive_style_signal_text(style_mapping: Mapping[str, Any]) -> str:
    return " ".join(
        _flatten_mapping_text(value)
        for value in _iter_positive_style_values(style_mapping)
        if value
    )


def _iter_positive_style_values(style_mapping: Mapping[str, Any]) -> list[Any]:
    values: list[Any] = []
    for key, item in style_mapping.items():
        if str(key) in _NEGATIVE_STYLE_SIGNAL_KEYS:
            continue
        if isinstance(item, Mapping):
            values.extend(_iter_positive_style_values(item))
            continue
        values.append(item)
    return values


def _flatten_mapping_text(value: Any) -> str:
    if isinstance(value, Mapping):
        return " ".join(_flatten_mapping_text(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return " ".join(_flatten_mapping_text(item) for item in value)
    if value is None:
        return ""
    return str(value)


def _is_opening_or_establishing_frame(frame: StoryboardPlanFrame, frame_text: str) -> bool:
    return frame.index == 1 and _contains_any(
        frame_text,
        ("开篇", "出发", "建立场景", "建立空间", "入口", "第一站", "旅程", "南大门"),
    )


def _is_ip_hero_frame(frame_text: str, ip_profile: IPProfile) -> bool:
    return ip_profile.name in frame_text or _contains_any(
        frame_text,
        ("IP主角", "IP 主角", "品牌主角", "吉祥物主画面", "角色主画面", "强露出"),
    )


def _landmark_terms(frame: StoryboardPlanFrame) -> list[str]:
    candidates = [
        "长乐门",
        "古寺",
        "佛祖",
        "古寺壁画",
        "壁画",
        "历史建筑",
        "宗教人物",
    ]
    text = _frame_text(frame)
    terms = [term for term in candidates if term in text]
    if terms:
        return _unique(terms)
    if frame.primary_subject:
        return [part.strip(" 、，。") for part in frame.primary_subject.split("、") if part.strip(" 、，。")][:2]
    return []


def _image_text_plan(
    frame: StoryboardPlanFrame,
    ip_profile: IPProfile,
    landmark_terms: list[str],
) -> IPImageTextPlan:
    summary = _summary_text(frame)
    whitelist = _unique(
        [
            *(item for item in (summary,) if item),
            *landmark_terms,
            *ip_profile.visible_text_whitelist,
        ]
    )
    return IPImageTextPlan(
        summary_text=summary,
        scene_text=tuple(landmark_terms[:2]),
        visible_text_whitelist=tuple(whitelist),
        text_safety_rules=("只允许生成白名单中的画面文字", "避免额外标语和乱码文字"),
    )


def _summary_text(frame: StoryboardPlanFrame) -> str | None:
    if "从长乐门出发" in frame.source_text:
        return "从长乐门出发"
    if "正定古城" in frame.source_text or "正定古城" in frame.visual_goal:
        return "正定古城"
    if frame.primary_subject:
        return frame.primary_subject.split("、")[0].strip()
    return None


def _presence_mode(presence_type: IPPresenceType) -> str | None:
    return {
        IPPresenceType.STRONG_IDENTITY: "hero",
        IPPresenceType.BALANCED_NARRATIVE: "guide",
        IPPresenceType.SCENE_INTEGRATED: "support",
        IPPresenceType.LOW_INTRUSION: "ambient",
        IPPresenceType.SYMBOLIC_ONLY: "symbolic",
        IPPresenceType.ABSENT: "absent",
    }[presence_type]


def _semantic_reason(presence_type: IPPresenceType) -> str:
    return {
        IPPresenceType.STRONG_IDENTITY: "frame explicitly asks the IP to carry the main visual identity",
        IPPresenceType.BALANCED_NARRATIVE: "narrative frame can use the IP as a guide without dominating the scene",
        IPPresenceType.SCENE_INTEGRATED: "opening establishing frame should keep the place as the primary subject",
        IPPresenceType.LOW_INTRUSION: "protected historical or religious subject should keep IP intrusion low",
        IPPresenceType.SYMBOLIC_ONLY: "landscape or protected cutaway should use only symbolic IP traces",
        IPPresenceType.ABSENT: "frame should omit the IP",
    }[presence_type]


def _visible_anchors(presence_type: IPPresenceType, ip_profile: IPProfile) -> tuple[str, ...]:
    if presence_type is IPPresenceType.ABSENT:
        return ()
    if presence_type is IPPresenceType.SYMBOLIC_ONLY:
        return tuple(ip_profile.identity_anchors[:1])
    return tuple([*ip_profile.identity_lock, *ip_profile.identity_anchors])


def _suppressed_anchors(presence_type: IPPresenceType, ip_profile: IPProfile) -> tuple[str, ...]:
    if presence_type in {IPPresenceType.LOW_INTRUSION, IPPresenceType.SYMBOLIC_ONLY, IPPresenceType.ABSENT}:
        return tuple(ip_profile.identity_lock)
    return tuple(ip_profile.identity_suppression_rules)


def _identity_color_terms(ip_profile: IPProfile) -> tuple[str, ...]:
    terms: list[str] = []
    for palette_entry in ip_profile.color_palette.values():
        if isinstance(palette_entry, Mapping):
            prompt = palette_entry.get("prompt")
            if isinstance(prompt, str) and prompt.strip():
                terms.append(prompt.strip())
    return tuple(_unique(terms))


def _negative_constraints(
    ip_profile: IPProfile,
    presence_type: IPPresenceType,
) -> tuple[str, ...]:
    constraints = [
        *ip_profile.semantic_boundary,
        *ip_profile.negative_constraints,
        "不能替代画面中的历史建筑或宗教人物",
    ]
    if presence_type in {IPPresenceType.LOW_INTRUSION, IPPresenceType.SYMBOLIC_ONLY, IPPresenceType.ABSENT}:
        constraints.append("避免让IP角色成为严肃历史宗教叙事的主体")
    return tuple(_unique(constraints))


def _action_for_presence(presence_type: IPPresenceType) -> str | None:
    if presence_type is IPPresenceType.STRONG_IDENTITY:
        return "面向镜头介绍主题"
    if presence_type in {IPPresenceType.BALANCED_NARRATIVE, IPPresenceType.SCENE_INTEGRATED}:
        return "自然陪伴并指向场景重点"
    return None


def _expression_for_presence(presence_type: IPPresenceType) -> str | None:
    if presence_type in {
        IPPresenceType.STRONG_IDENTITY,
        IPPresenceType.BALANCED_NARRATIVE,
        IPPresenceType.SCENE_INTEGRATED,
    }:
        return "温和克制"
    return None


def _camera_relationship_for_presence(presence_type: IPPresenceType) -> str | None:
    return {
        IPPresenceType.STRONG_IDENTITY: "foreground primary subject",
        IPPresenceType.BALANCED_NARRATIVE: "mid-ground guide subject",
        IPPresenceType.SCENE_INTEGRATED: "mid-ground support subject",
        IPPresenceType.LOW_INTRUSION: "edge or background minor subject",
        IPPresenceType.SYMBOLIC_ONLY: "symbolic detail only",
        IPPresenceType.ABSENT: None,
    }[presence_type]


def _depth_layer_for_presence(presence_type: IPPresenceType) -> str | None:
    return {
        IPPresenceType.STRONG_IDENTITY: "foreground",
        IPPresenceType.BALANCED_NARRATIVE: "middle",
        IPPresenceType.SCENE_INTEGRATED: "middle",
        IPPresenceType.LOW_INTRUSION: "background",
        IPPresenceType.SYMBOLIC_ONLY: "detail",
        IPPresenceType.ABSENT: None,
    }[presence_type]


def _shot_fit_notes(presence_type: IPPresenceType) -> str | None:
    if presence_type is IPPresenceType.STRONG_IDENTITY:
        return "IP can dominate the frame while preserving stated scene context"
    if presence_type in {IPPresenceType.LOW_INTRUSION, IPPresenceType.SYMBOLIC_ONLY, IPPresenceType.ABSENT}:
        return "do not let IP replace the protected subject"
    return "IP should support the scene without replacing the landmark"


def _prompt_weight(presence_type: IPPresenceType) -> float:
    return {
        IPPresenceType.STRONG_IDENTITY: 0.9,
        IPPresenceType.BALANCED_NARRATIVE: 0.7,
        IPPresenceType.SCENE_INTEGRATED: 0.6,
        IPPresenceType.LOW_INTRUSION: 0.3,
        IPPresenceType.SYMBOLIC_ONLY: 0.2,
        IPPresenceType.ABSENT: 0.0,
    }[presence_type]


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = value.strip()
        if normalized and normalized not in seen:
            result.append(normalized)
            seen.add(normalized)
    return result


_PROTECTED_SUBJECT_KEYWORDS = (
    "佛祖",
    "佛像",
    "菩萨",
    "宗教人物",
    "宗教叙事",
    "宗教场景",
    "香火",
    "严肃历史",
    "严肃纪实",
    "纪录片",
    "真实人物",
    "历史说明",
)
_PURE_LANDSCAPE_KEYWORDS = ("空镜", "纯风景", "风景切镜", "山水", "天空", "河流", "远山")
_NARRATIVE_KEYWORDS = ("讲述", "说明", "叙事", "介绍", "导览", "科普", "铺开")
_SERIOUS_STYLE_KEYWORDS = ("严肃纪实", "纪录片", "documentary", "serious documentary")
_NEGATIVE_STYLE_SIGNAL_KEYS = ("negative_prompt", "negative_rules")


__all__ = ["IPUsagePlanner"]
