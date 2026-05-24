from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from typing import Any

from pixelle_video.models.asset_bible import IPProfile
from pixelle_video.models.content_world import ContentWorldProfile
from pixelle_video.models.ip_prompt_planning import (
    IPFrameAdaptationPackage,
    IPImageTextPlan,
    IPPresenceType,
    IPRoleSlot,
)
from pixelle_video.models.storyboard_plan import StoryboardPlan, StoryboardPlanFrame
from pixelle_video.models.style_resolution import ResolvedStyleSpec

logger = logging.getLogger(__name__)

ResolvedStyleInput = Mapping[str, Any] | ResolvedStyleSpec | None
ContentWorldInput = ContentWorldProfile | Mapping[str, Any] | None


class IPUsagePlanner:
    """Deterministic per-frame IP presence planner for prompt context building."""

    def plan_batch(
        self,
        *,
        storyboard_plan: StoryboardPlan,
        ip_profile: IPProfile,
        resolved_style: ResolvedStyleInput = None,
        scene_casts_by_frame: Mapping[str, Any] | None = None,
        generation_world_profile: ContentWorldInput = None,
    ) -> list[IPFrameAdaptationPackage]:
        scene_casts = scene_casts_by_frame or {}
        world_profile = _normalize_generation_world_profile(generation_world_profile)
        return [
            self.plan_frame(
                frame=frame,
                ip_profile=ip_profile,
                resolved_style=resolved_style,
                scene_cast=_scene_cast_for_frame(scene_casts, frame),
                generation_world_profile=world_profile,
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
        generation_world_profile: ContentWorldInput = None,
    ) -> IPFrameAdaptationPackage:
        frame_text = _frame_text(frame)
        world_profile = _normalize_generation_world_profile(generation_world_profile)
        world_profile_text = _world_profile_text(world_profile)
        presence_type = _presence_type_for_frame(
            frame=frame,
            frame_text=frame_text,
            ip_profile=ip_profile,
            resolved_style=resolved_style,
            scene_cast=scene_cast,
            world_profile_text=world_profile_text,
        )
        landmark_terms = _landmark_terms(frame, world_profile_text=world_profile_text)
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
            visual_identity=_build_visual_identity(ip_profile),
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


def _validated_scene_cast_presence(scene_cast: Any | None) -> str | None:
    presence_type = _presence_type_from_scene_cast(scene_cast)
    return presence_type.value if presence_type is not None else None


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


def _normalize_generation_world_profile(
    generation_world_profile: ContentWorldInput,
) -> ContentWorldProfile | None:
    if generation_world_profile is None:
        return None
    if isinstance(generation_world_profile, ContentWorldProfile):
        profile = generation_world_profile
    elif isinstance(generation_world_profile, Mapping):
        profile = ContentWorldProfile.from_dict(generation_world_profile)
    else:
        return None
    return profile if profile.has_content() else None


def _generation_notes_from_profile(generation_world_profile: ContentWorldInput) -> str | None:
    """Extract a concise generation notes string from a world profile for appearance planning."""
    profile = _normalize_generation_world_profile(generation_world_profile)
    if profile is None:
        return None
    return " ".join(
        value
        for value in (profile.summary, profile.ip_integration_guidance)
        if value
    ) or None


def _world_profile_text(generation_world_profile: ContentWorldProfile | None) -> str:
    if generation_world_profile is None:
        return ""
    return " ".join(
        value
        for value in (
            generation_world_profile.story_constraints,
            generation_world_profile.ip_integration_guidance,
            generation_world_profile.summary,
        )
        if value
    )


def _presence_type_for_frame(
    *,
    frame: StoryboardPlanFrame,
    frame_text: str,
    ip_profile: IPProfile,
    resolved_style: ResolvedStyleInput,
    scene_cast: Any | None,
    world_profile_text: str = "",
) -> IPPresenceType:
    scene_cast_presence = _presence_type_from_scene_cast(scene_cast)
    if scene_cast_presence is not None:
        return scene_cast_presence
    if _contains_any(world_profile_text, _PROTECTED_SUBJECT_KEYWORDS):
        return IPPresenceType.LOW_INTRUSION
    if _contains_any(world_profile_text, _LOW_INTRUSION_GUIDANCE_KEYWORDS):
        return IPPresenceType.LOW_INTRUSION
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
        if str(key) in _NON_POSITIVE_STYLE_SIGNAL_KEYS:
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
        ("开篇", "出发", "建立场景", "建立空间", "入口"),
    )


def _is_ip_hero_frame(frame_text: str, ip_profile: IPProfile) -> bool:
    return ip_profile.name in frame_text


def _landmark_terms(frame: StoryboardPlanFrame, *, world_profile_text: str = "") -> list[str]:
    if frame.primary_subject:
        return [part.strip(" 、，。") for part in frame.primary_subject.split("、") if part.strip(" 、，。")][:2]
    return []


def _image_text_plan(
    frame: StoryboardPlanFrame,
    ip_profile: IPProfile,
    landmark_terms: list[str],
) -> IPImageTextPlan:
    summary = frame.primary_subject.split("、")[0].strip() if frame.primary_subject else None
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
        text_safety_rules=(),
    )


def _presence_mode(presence_type: IPPresenceType) -> str | None:
    return {
        IPPresenceType.STRONG_IDENTITY: "hero",
        IPPresenceType.BALANCED_NARRATIVE: "narrative",
        IPPresenceType.SCENE_INTEGRATED: "support",
        IPPresenceType.LOW_INTRUSION: "ambient",
        IPPresenceType.SYMBOLIC_ONLY: "symbolic",
        IPPresenceType.ABSENT: "absent",
    }[presence_type]


def _semantic_reason(presence_type: IPPresenceType) -> str:
    return {
        IPPresenceType.STRONG_IDENTITY: "frame explicitly asks the IP to carry the main visual identity",
        IPPresenceType.BALANCED_NARRATIVE: "narrative frame can feature the IP as a character without dominating the scene",
        IPPresenceType.SCENE_INTEGRATED: "opening establishing frame should keep the scene as the primary subject",
        IPPresenceType.LOW_INTRUSION: "protected subject should keep IP intrusion low",
        IPPresenceType.SYMBOLIC_ONLY: "landscape or cutaway should use only symbolic IP traces",
        IPPresenceType.ABSENT: "frame should omit the IP",
    }[presence_type]


def _visible_anchors(presence_type: IPPresenceType, ip_profile: IPProfile) -> tuple[str, ...]:
    """只返回纯视觉特征（identity_lock），不含 identity_anchors 中的角色标签。

    identity_anchors 可能包含"古城文旅向导"等角色职能描述，
    这些角色信息由 appearance_description 统一携带，不应作为独立锚点注入。
    """
    if presence_type is IPPresenceType.ABSENT:
        return ()
    if presence_type is IPPresenceType.SYMBOLIC_ONLY:
        return tuple(ip_profile.identity_lock[:1])
    return tuple(ip_profile.identity_lock)


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
    return tuple(_unique([*ip_profile.semantic_boundary, *ip_profile.negative_constraints]))


def _action_for_presence(presence_type: IPPresenceType) -> str | None:
    return None


def _expression_for_presence(presence_type: IPPresenceType) -> str | None:
    return None


def _camera_relationship_for_presence(presence_type: IPPresenceType) -> str | None:
    return {
        IPPresenceType.STRONG_IDENTITY: "foreground primary subject",
        IPPresenceType.BALANCED_NARRATIVE: "mid-ground narrative subject",
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
        return "keep IP presence minimal"
    return "IP should support the scene naturally"


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
_LOW_INTRUSION_GUIDANCE_KEYWORDS = (
    "低侵入",
    "不出现",
    "避免强露出",
    "只允许",
    "象征性",
    "symbolic",
    "low intrusion",
    "absent",
)
_PURE_LANDSCAPE_KEYWORDS = ("空镜", "纯风景", "风景切镜", "山水", "天空", "河流", "远山")
_NARRATIVE_KEYWORDS = ("讲述", "说明", "叙事", "介绍", "科普", "铺开")
_SERIOUS_STYLE_KEYWORDS = ("严肃纪实", "纪录片", "documentary", "serious documentary")
_NON_POSITIVE_STYLE_SIGNAL_KEYS = ("negative_prompt", "negative_rules", "raw_content")


class IPFrameAppearancePlanner:
    """逐帧 IP 出场规划器（LLM 驱动 + 规则回退）。

    核心职责：为每一帧决定 IP 的 role_slot（替代谁）、生成 appearance_description（场景化出场描述）。

    描述生成优先级：
      1. LLM 路径：_llm_role_selection() 直接输出自然语言的场景化 appearance_description
      2. 规则回退：_build_appearance_description() 仅输出 IP 纯视觉身份

    ── 使用方式 ──
    # 1. 无 LLM（规则回退）
    planner = IPFrameAppearancePlanner()
    packages = await planner.plan_batch(storyboard_plan=plan, ip_profile=profile)

    # 2. 有 LLM（LLM 批量决定角色分配 + 生成场景化出场描述）
    planner = IPFrameAppearancePlanner(llm_client=llm_service)
    packages = await planner.plan_batch(...)
    # LLM 成功 → 每帧角色 + 场景化描述由 LLM 动态生成
    # LLM 失败 → 自动回退到 _rule_based_role_selection() + _build_appearance_description()

    ── 产出 ──
    - role_slot:      IPRoleSlot（主角/配角/路人/不出镜）
    - appearance_description: 场景化出场描述，由 LLM 生成或规则回退
    """

    def __init__(self, *, llm_client: Any = None) -> None:
        """llm_client: 可选，传入 LLM service 启用 LLM 驱动角色分配。
           不传则始终走规则回退（_rule_based_role_selection）。"""
        self._deterministic = IPUsagePlanner()
        self._llm = llm_client

    async def plan_batch(
        self,
        *,
        storyboard_plan: StoryboardPlan,
        ip_profile: IPProfile,
        resolved_style: ResolvedStyleInput = None,
        scene_casts_by_frame: Mapping[str, Any] | None = None,
        generation_world_profile: ContentWorldInput = None,
    ) -> list[IPFrameAdaptationPackage]:
        scene_casts = scene_casts_by_frame or {}
        base_packages = self._deterministic.plan_batch(
            storyboard_plan=storyboard_plan,
            ip_profile=ip_profile,
            resolved_style=resolved_style,
            scene_casts_by_frame=scene_casts,
            generation_world_profile=generation_world_profile,
        )
        generation_notes = _generation_notes_from_profile(generation_world_profile)

        # Try LLM-driven role selection for the entire batch
        llm_roles = None
        if self._llm is not None:
            llm_roles = await self._llm_role_selection(
                storyboard_plan=storyboard_plan,
                ip_profile=ip_profile,
                base_packages=base_packages,
                generation_world_profile=generation_world_profile,
                scene_casts_by_frame=scene_casts,
            )

        enriched: list[IPFrameAdaptationPackage] = []
        prev_frame: StoryboardPlanFrame | None = None
        prev_package: IPFrameAdaptationPackage | None = None

        for i, (frame, base_pkg) in enumerate(zip(storyboard_plan.frames, base_packages)):
            if llm_roles is not None and i < len(llm_roles):
                raw_slot = llm_roles[i]["role_slot"]
                role_slot_override = IPRoleSlot(raw_slot) if isinstance(raw_slot, str) else raw_slot
                role_label_override = llm_roles[i]["role_label"]
                presence_desc_override = llm_roles[i]["presence_level"]
                appearance_desc_override = llm_roles[i].get("appearance_description", "")
            else:
                role_slot_override = None
                role_label_override = None
                presence_desc_override = None
                appearance_desc_override = None

            appearance = self.plan_frame_appearance(
                frame=frame,
                ip_profile=ip_profile,
                base_package=base_pkg,
                frame_index=i,
                total_frames=len(storyboard_plan.frames),
                generation_notes=generation_notes,
                prev_frame=prev_frame,
                prev_package=prev_package,
                role_slot_override=role_slot_override,
                role_label_override=role_label_override,
                presence_desc_override=presence_desc_override,
                appearance_desc_override=appearance_desc_override,
            )
            enriched.append(appearance)
            prev_frame = frame
            prev_package = appearance

        return enriched

    async def _llm_role_selection(
        self,
        *,
        storyboard_plan: StoryboardPlan,
        ip_profile: IPProfile,
        base_packages: list[IPFrameAdaptationPackage],
        generation_world_profile: ContentWorldInput = None,
        scene_casts_by_frame: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]] | None:
        """Call LLM to decide role_slot, role_label, presence_level, appearance_description per frame.

        Returns None on failure so caller falls back to rule-based selection.
        """
        from pixelle_video.prompts.ip_role_selection import (
            build_ip_role_selection_prompt,
            parse_ip_role_selection_response,
        )

        world_profile = _normalize_generation_world_profile(generation_world_profile)
        ip_profile_json = json.dumps(
            {
                "name": ip_profile.name,
                "identity_lock": list(ip_profile.identity_lock),
                "identity_anchors": list(ip_profile.identity_anchors),
                "visual_summary": ip_profile.visual_summary,
                "minimal_traits": list(ip_profile.minimal_traits),
                "semantic_boundary": list(ip_profile.semantic_boundary),
                "negative_constraints": list(ip_profile.negative_constraints),
                "role_presets": list(ip_profile.role_presets),
                "presence_spectrum": list(ip_profile.presence_spectrum),
                "adaptable_slots": list(ip_profile.adaptable_slots),
                "default_slot_preference": ip_profile.default_slot_preference,
                "style_hint": ip_profile.style_hint,
                "world_hint": ip_profile.world_hint,
                "generation_world_profile": world_profile.to_dict() if world_profile else {},
            },
            ensure_ascii=False,
            indent=2,
        )
        frames_json = json.dumps(
            [
                {
                    "frame_index": i,
                    "frame_id": frame.frame_id,
                    "source_text": frame.source_text,
                    "visual_goal": frame.visual_goal,
                    "shot_type": frame.shot_type,
                    "primary_subject": frame.primary_subject,
                    "presence_type": base.ip_presence_type.value,
                    "presence_mode": base.presence_mode,
                    "semantic_reason": base.semantic_reason,
                    "must_not_replace": list(base.must_not_replace),
                    "identity_anchors_visible": list(base.identity_anchors_visible),
                    "identity_anchors_suppressed": list(base.identity_anchors_suppressed),
                    "scene_cast_presence": _validated_scene_cast_presence(scene_cast),
                }
                for i, (frame, base) in enumerate(
                    zip(storyboard_plan.frames, base_packages)
                )
                for scene_cast in (
                    _scene_cast_for_frame(scene_casts_by_frame or {}, frame),
                )
            ],
            ensure_ascii=False,
            indent=2,
        )

        prompt = build_ip_role_selection_prompt(
            ip_profile_json=ip_profile_json,
            frames_json=frames_json,
        )

        try:
            raw_response = await self._llm(prompt)
        except Exception:
            logger.warning("LLM IP role selection failed, using rule-based fallback", exc_info=True)
            return None

        parsed = parse_ip_role_selection_response(raw_response)
        if parsed is None:
            logger.warning("LLM IP role selection parsing failed, using rule-based fallback")
        return parsed

    def plan_frame_appearance(
        self,
        *,
        frame: StoryboardPlanFrame,
        ip_profile: IPProfile,
        base_package: IPFrameAdaptationPackage,
        frame_index: int,
        total_frames: int,
        generation_notes: str | None = None,
        prev_frame: StoryboardPlanFrame | None = None,
        prev_package: IPFrameAdaptationPackage | None = None,
        role_slot_override: IPRoleSlot | None = None,
        role_label_override: str | None = None,
        presence_desc_override: str | None = None,
        appearance_desc_override: str | None = None,
    ) -> IPFrameAdaptationPackage:
        if role_slot_override is not None and role_label_override is not None:
            role_slot = role_slot_override
        else:
            role_slot, _, _ = _rule_based_role_selection(
                ip_profile, base_package.ip_presence_type
            )
        interaction = _select_interaction_target(frame)
        continuity = _build_continuity_note(prev_package)

        if appearance_desc_override and appearance_desc_override.strip():
            appearance_description = appearance_desc_override.strip()
        else:
            appearance_description = _build_appearance_description(
                ip_profile=ip_profile,
                role_slot=role_slot,
            )

        return IPFrameAdaptationPackage(
            frame_id=base_package.frame_id,
            ip_presence_type=base_package.ip_presence_type,
            presence_mode=base_package.presence_mode,
            semantic_reason=base_package.semantic_reason,
            must_not_replace=base_package.must_not_replace,
            identity_anchors_visible=base_package.identity_anchors_visible,
            identity_anchors_suppressed=base_package.identity_anchors_suppressed,
            identity_color_terms=base_package.identity_color_terms,
            outfit_theme=None,
            outfit_condition=None,
            accessories=(),
            action=None,
            expression=None,
            pose=None,
            camera_relationship=base_package.camera_relationship,
            depth_layer=base_package.depth_layer,
            interaction_target=interaction,
            continuity_from_previous=continuity,
            appearance_description=appearance_description,
            visual_identity=_build_visual_identity(ip_profile),
            role_slot=role_slot,
            shot_fit_notes=base_package.shot_fit_notes,
            image_text_plan=base_package.image_text_plan,
            prompt_weight=base_package.prompt_weight,
            negative_constraints=base_package.negative_constraints,
        )


# ── role selection ────────────────────────────────────────────────────

def _rule_based_role_selection(
    ip_profile: IPProfile,
    presence_type: IPPresenceType,
) -> tuple[IPRoleSlot, str, str]:
    """规则回退：按 presence_type → role_slot 映射决定角色槽位。

    返回 (role_slot, role_label, presence_desc)。
    """
    if presence_type is IPPresenceType.ABSENT:
        return (IPRoleSlot.ABSENT, "画外不出镜", "完全不出镜")
    if presence_type is IPPresenceType.SYMBOLIC_ONLY:
        return (IPRoleSlot.PASSERBY, "场景参与者", "局部细节")

    slot_map: dict[IPPresenceType, IPRoleSlot] = {
        IPPresenceType.STRONG_IDENTITY: IPRoleSlot.PROTAGONIST,
        IPPresenceType.BALANCED_NARRATIVE: IPRoleSlot.SUPPORTING,
        IPPresenceType.SCENE_INTEGRATED: IPRoleSlot.SUPPORTING,
        IPPresenceType.LOW_INTRUSION: IPRoleSlot.PASSERBY,
    }
    role_slot = slot_map.get(presence_type, IPRoleSlot.SUPPORTING)

    role_name = ip_profile.role_presets[0] if ip_profile.role_presets else "场景参与者"

    presence_map: dict[IPPresenceType, str] = {
        IPPresenceType.STRONG_IDENTITY: "全身出镜",
        IPPresenceType.BALANCED_NARRATIVE: "半身出镜",
        IPPresenceType.SCENE_INTEGRATED: "远景融入",
        IPPresenceType.LOW_INTRUSION: "远景融入",
    }
    presence_desc = presence_map.get(presence_type, "半身出镜")

    return (role_slot, role_name, presence_desc)


# ── interaction / continuity / appearance description ─────────────────

def _select_interaction_target(frame: StoryboardPlanFrame) -> str | None:
    if frame.primary_subject:
        return frame.primary_subject.split("、")[0].strip()
    return None


def _build_continuity_note(
    prev_package: IPFrameAdaptationPackage | None,
) -> str | None:
    if prev_package is None:
        return None
    prev_desc = prev_package.appearance_description or "无"
    return f"上一帧：{prev_desc}"


def _build_visual_identity(ip_profile: IPProfile) -> str:
    """构建纯视觉身份字符串，仅从 identity_lock 提取，不含角色标签。

    identity_lock 应为纯视觉特征（如"白色卡通兔子，蓝色领结，长耳朵"），
    角色标签（如"古城文旅向导"）属于 identity_anchors 不应混入。
    visual_summary 是用户策划的视觉摘要，优先使用；回退到 identity_lock 逗号拼接。
    """
    return (ip_profile.visual_summary or ", ".join(ip_profile.identity_lock)).rstrip(
        "。，,;；!！?？\n\r "
    )


def _build_appearance_description(
    *,
    ip_profile: IPProfile,
    role_slot: IPRoleSlot | None,
) -> str:
    """生成 IP 出场描述（规则回退）。

    仅输出 IP 的纯视觉身份——不猜测角色、动作、表情。
    具体融入方式由 image_generation.py 的 LLM 根据 ip_scene_description 自行编织。
    """
    if role_slot is IPRoleSlot.ABSENT:
        return ""
    return _build_visual_identity(ip_profile)


def _first_text(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


__all__ = [
    "IPFrameAppearancePlanner",
    "IPUsagePlanner",
    "_rule_based_role_selection",
]
