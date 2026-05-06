from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pixelle_video.models.asset_bible import IPProfile
from pixelle_video.models.content_world import ContentWorldProfile
from pixelle_video.models.ip_prompt_planning import (
    IPFrameAdaptationPackage,
    IPImageTextPlan,
    IPPresenceType,
)
from pixelle_video.models.storyboard_plan import StoryboardPlan, StoryboardPlanFrame
from pixelle_video.models.style_resolution import ResolvedStyleSpec

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
        ("开篇", "出发", "建立场景", "建立空间", "入口", "第一站", "旅程", "南大门"),
    )


def _is_ip_hero_frame(frame_text: str, ip_profile: IPProfile) -> bool:
    return ip_profile.name in frame_text or _contains_any(
        frame_text,
        ("IP主角", "IP 主角", "品牌主角", "吉祥物主画面", "角色主画面", "强露出"),
    )


def _landmark_terms(frame: StoryboardPlanFrame, *, world_profile_text: str = "") -> list[str]:
    candidates = [
        "长乐门",
        "古寺",
        "佛像",
        "佛祖",
        "古寺壁画",
        "壁画",
        "历史建筑",
        "宗教人物",
    ]
    text = _frame_text(frame)
    terms = [term for term in candidates if term in text or term in world_profile_text]
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
_NARRATIVE_KEYWORDS = ("讲述", "说明", "叙事", "介绍", "导览", "科普", "铺开")
_SERIOUS_STYLE_KEYWORDS = ("严肃纪实", "纪录片", "documentary", "serious documentary")
_NON_POSITIVE_STYLE_SIGNAL_KEYS = ("negative_prompt", "negative_rules", "raw_content")


class IPFrameAppearancePlanner:
    """LLM-driven per-frame IP appearance planner with deterministic fallback.

    Generates natural-language appearance descriptions and populates the
    previously-unused fields of IPFrameAdaptationPackage (outfit_theme,
    accessories, pose, expression, action, interaction_target).
    """

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
        base_planner = IPUsagePlanner()
        base_packages = base_planner.plan_batch(
            storyboard_plan=storyboard_plan,
            ip_profile=ip_profile,
            resolved_style=resolved_style,
            scene_casts_by_frame=scene_casts,
            generation_world_profile=generation_world_profile,
        )
        generation_notes = _generation_notes_from_profile(generation_world_profile)
        enriched: list[IPFrameAdaptationPackage] = []
        prev_frame: StoryboardPlanFrame | None = None
        prev_package: IPFrameAdaptationPackage | None = None

        for i, (frame, base_pkg) in enumerate(zip(storyboard_plan.frames, base_packages)):
            appearance = self.plan_frame_appearance(
                frame=frame,
                ip_profile=ip_profile,
                base_package=base_pkg,
                frame_index=i,
                total_frames=len(storyboard_plan.frames),
                generation_notes=generation_notes,
                prev_frame=prev_frame,
                prev_package=prev_package,
            )
            enriched.append(appearance)
            prev_frame = frame
            prev_package = appearance

        return enriched

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
    ) -> IPFrameAdaptationPackage:
        frame_text = _frame_text(frame)
        domain = _detect_content_domain(
            frame_text=frame_text,
            generation_notes=_first_text(generation_notes),
        )
        role = _select_role(ip_profile, domain, base_package.ip_presence_type)
        presence_desc = _select_presence_description(
            ip_profile, base_package.ip_presence_type, frame_index, total_frames
        )
        outfit = _select_outfit_theme(ip_profile, domain)
        accessories = _select_accessories(ip_profile, domain)
        pose = _select_pose(ip_profile, domain, base_package.ip_presence_type)
        expression = _select_expression(domain, base_package.ip_presence_type)
        action = _select_action(ip_profile, domain, base_package.ip_presence_type)
        interaction = _select_interaction_target(frame)
        continuity = _build_continuity_note(prev_package)

        appearance_description = _build_appearance_description(
            ip_profile=ip_profile,
            role=role,
            presence_desc=presence_desc,
            outfit=outfit,
            accessories=accessories,
            pose=pose,
            expression=expression,
            action=action,
            interaction=interaction,
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
            outfit_theme=outfit,
            outfit_condition=_domain_outfit_condition(domain),
            accessories=tuple(accessories),
            action=action,
            expression=expression,
            pose=pose,
            camera_relationship=base_package.camera_relationship,
            depth_layer=base_package.depth_layer,
            interaction_target=interaction,
            continuity_from_previous=continuity,
            appearance_description=appearance_description,
            shot_fit_notes=base_package.shot_fit_notes,
            image_text_plan=base_package.image_text_plan,
            prompt_weight=base_package.prompt_weight,
            negative_constraints=base_package.negative_constraints,
        )


# ── content domain detection ──────────────────────────────────────────

_CONTENT_DOMAIN_PATTERNS: dict[str, tuple[str, ...]] = {
    "文旅": ("古城", "城墙", "古寺", "碑刻", "历史", "遗迹", "导游", "讲解", "景区", "名胜"),
    "爱情": ("情侣", "爱情", "牵手", "约会", "心动", "告白", "依偎", "婚礼", "恋人"),
    "美食": ("美食", "烹饪", "食物", "餐厅", "菜肴", "火锅", "甜点", "咖啡", "料理"),
    "科技": ("科技", "AI", "数据", "代码", "芯片", "数字", "智能", "屏幕"),
    "日常": ("日常", "生活", "工作", "通勤", "家庭", "周末", "朋友", "聚会"),
    "自然": ("自然", "山水", "森林", "海洋", "日落", "日出", "天空", "田野"),
}


def _detect_content_domain(
    *,
    frame_text: str,
    generation_notes: str = "",
) -> str:
    combined = f"{frame_text} {generation_notes}"
    scores: dict[str, int] = {}
    for domain, keywords in _CONTENT_DOMAIN_PATTERNS.items():
        score = sum(1 for kw in keywords if kw in combined)
        if score:
            scores[domain] = score
    if scores:
        return max(scores, key=scores.get)
    return "通用"


# ── role selection ────────────────────────────────────────────────────

def _select_role(
    ip_profile: IPProfile,
    domain: str,
    presence_type: IPPresenceType,
) -> str:
    if presence_type is IPPresenceType.ABSENT:
        return "画外不出镜"
    if presence_type is IPPresenceType.SYMBOLIC_ONLY:
        return "路人观察者"

    domain_role_map: dict[str, str] = {
        "文旅": "导游讲解者",
        "爱情": "情感陪伴者",
        "美食": "路人观察者",
        "科技": "路人观察者",
        "日常": "情感陪伴者",
        "自然": "路人观察者",
    }
    role_name = domain_role_map.get(domain, "情感陪伴者")

    for preset in ip_profile.role_presets:
        if preset.startswith(role_name):
            return preset
    return role_name


# ── presence description ──────────────────────────────────────────────

def _select_presence_description(
    ip_profile: IPProfile,
    presence_type: IPPresenceType,
    frame_index: int,
    total_frames: int,
) -> str:
    if presence_type is IPPresenceType.ABSENT:
        return "完全不出镜"

    position = frame_index / max(total_frames, 1)
    presence_map = {
        IPPresenceType.STRONG_IDENTITY: "全身出镜",
        IPPresenceType.BALANCED_NARRATIVE: "半身出镜",
        IPPresenceType.SCENE_INTEGRATED: "远景融入" if position > 0.7 else "半身出镜",
        IPPresenceType.LOW_INTRUSION: "局部细节",
        IPPresenceType.SYMBOLIC_ONLY: "局部细节",
    }
    presence_name = presence_map.get(presence_type, "半身出镜")

    for preset in ip_profile.presence_spectrum:
        if preset.startswith(presence_name):
            return preset
    return presence_name


# ── outfit / accessories / pose / expression / action ─────────────────

def _select_outfit_theme(ip_profile: IPProfile, domain: str) -> str | None:
    if not _ip_supports_adaptable_slot(ip_profile, "服装"):
        return None
    themes: dict[str, str] = {
        "文旅": "轻便文旅休闲装，保持角色可识别",
        "爱情": "柔和色系便装，温暖亲和",
        "美食": "厨师围裙或休闲用餐装，保持角色可识别",
        "科技": "简约现代科技感服装，干净利落",
        "日常": "日常休闲服装",
        "自然": "轻便户外装",
    }
    return themes.get(domain)


def _domain_outfit_condition(domain: str) -> str | None:
    conditions: dict[str, str] = {
        "美食": "室内暖光，保持领结和耳朵清晰可见",
        "科技": "冷色调环境光，蓝色领结与屏幕光呼应",
        "自然": "自然光照，角色融入环境色调",
    }
    return conditions.get(domain)


def _select_accessories(ip_profile: IPProfile, domain: str) -> list[str]:
    if not _ip_supports_adaptable_slot(ip_profile, "道具"):
        return []
    domain_accessories: dict[str, list[str]] = {
        "文旅": ["导览旗", "地图"],
        "爱情": ["花束", "小礼物"],
        "美食": ["菜单", "餐具"],
        "科技": ["平板电脑", "耳机"],
        "日常": ["背包", "手机"],
        "自然": ["望远镜", "水壶"],
        "通用": [],
    }
    return domain_accessories.get(domain, [])


def _select_pose(
    ip_profile: IPProfile,
    domain: str,
    presence_type: IPPresenceType,
) -> str | None:
    if not _ip_supports_adaptable_slot(ip_profile, "动作姿势"):
        return None
    if presence_type is IPPresenceType.STRONG_IDENTITY:
        return "面向镜头，占据画面主体位置"
    domain_poses: dict[str, str] = {
        "文旅": "侧身站立，手指向场景重点",
        "爱情": "安静坐着或依靠，温和注视",
        "美食": "坐在餐桌旁，好奇观看食物",
        "科技": "站立在设备旁，注视屏幕",
        "日常": "自然放松的站姿",
        "自然": "面朝风景，背对镜头或侧身",
    }
    return domain_poses.get(domain)


def _select_expression(domain: str, presence_type: IPPresenceType) -> str | None:
    if presence_type in {IPPresenceType.LOW_INTRUSION, IPPresenceType.SYMBOLIC_ONLY}:
        return "安静平和的微表情"
    expressions: dict[str, str] = {
        "文旅": "温和好奇，面带微笑",
        "爱情": "温柔安静，表情柔和",
        "美食": "好奇惊喜，开心",
        "科技": "专注认真",
        "日常": "轻松自然",
        "自然": "惬意放松",
    }
    return expressions.get(domain)


def _select_action(
    ip_profile: IPProfile,
    domain: str,
    presence_type: IPPresenceType,
) -> str | None:
    if presence_type is IPPresenceType.ABSENT:
        return None
    if not _ip_supports_adaptable_slot(ip_profile, "动作姿势"):
        return None
    actions: dict[str, str] = {
        "文旅": "做介绍手势，与场景内容互动",
        "爱情": "安静陪伴，与画面主体保持微妙的情感距离",
        "美食": "好奇查看食物，或轻松用餐",
        "科技": "观看屏幕或操作设备",
        "日常": "自然参与场景活动",
        "自然": "静静欣赏风景",
    }
    return actions.get(domain)


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


def _build_appearance_description(
    *,
    ip_profile: IPProfile,
    role: str,
    presence_desc: str,
    outfit: str | None,
    accessories: list[str],
    pose: str | None,
    expression: str | None,
    action: str | None,
    interaction: str | None,
) -> str:
    visual_core = ip_profile.visual_summary or ", ".join(
        [*ip_profile.identity_lock, *ip_profile.identity_anchors]
    )
    visual_core = visual_core.rstrip("。，,;；!！?？\n\r ")
    role_name = role.split("：")[0] if "：" in role else role
    presence_name = presence_desc.split("：")[0] if "：" in presence_desc else presence_desc

    parts: list[str] = [visual_core] if visual_core else []

    if outfit:
        parts.append(f"穿着{outfit}")
    if accessories:
        parts.append(f"手持{'、'.join(accessories)}")
    if pose:
        parts.append(pose)
    if expression:
        parts.append(expression)
    if action:
        parts.append(action)
    if interaction:
        parts.append(f"与{interaction}自然互动")

    desc = "，".join(parts)
    if desc:
        return f"作为{role_name}，{desc}，{presence_name}"
    return f"作为{role_name}，{presence_name}"


def _ip_supports_adaptable_slot(ip_profile: IPProfile, keyword: str) -> bool:
    """Check whether the IP profile has an adaptable slot containing the given keyword."""
    for slot in ip_profile.adaptable_slots:
        if keyword in slot:
            return True
    return False


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
]
