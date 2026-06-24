from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pixelle_video.models.base_visual_brief import BaseVisualBrief
from pixelle_video.models.visual_style_contract import VisualLayerTarget, VisualStyleLayerContract
from pixelle_video.services.source_subject_identity import source_subject_identity_prompt
from pixelle_video.services.visual_anchor_policy import infer_scene_anchor_affordances


@dataclass(frozen=True)
class BaseVisualBriefPlanner:
    """Build subject-first visual briefs from anchor-free base prompts.

    This planner also extracts scene affordances for later visual-signature integration.
    It does not insert the recurring anchor; it only describes safe physical carriers.
    """

    def plan_batch(
        self,
        *,
        base_prompts: Sequence[str],
        frame_contexts: Sequence[Mapping[str, Any]],
        frame_plans: Sequence[Any] = (),
        visual_style_contract: VisualStyleLayerContract | None = None,
        generation_world_profile: Any = None,
        world_preset: Mapping[str, Any] | None = None,
    ) -> tuple[BaseVisualBrief, ...]:
        return tuple(
            self.plan_frame(
                base_prompt=base_prompt,
                frame_context=frame_contexts[index] if index < len(frame_contexts) else {},
                frame_plan=frame_plans[index] if index < len(frame_plans) else None,
                visual_style_contract=visual_style_contract,
                generation_world_profile=generation_world_profile,
                world_preset=world_preset,
            )
            for index, base_prompt in enumerate(base_prompts)
        )

    def plan_frame(
        self,
        *,
        base_prompt: str,
        frame_context: Mapping[str, Any] | None = None,
        frame_plan: Any = None,
        visual_style_contract: VisualStyleLayerContract | None = None,
        generation_world_profile: Any = None,
        world_preset: Mapping[str, Any] | None = None,
    ) -> BaseVisualBrief:
        frame_context = frame_context or {}
        frame_id = str(_read_value(frame_context, "frame_id") or _read_value(frame_plan, "scene_id") or "frame")
        subject_anchors = _split_identity_hints(
            source_subject_identity_prompt(
                base_prompt=base_prompt,
                frame_context=frame_context,
                frame_plan=frame_plan,
                generation_world_profile=generation_world_profile,
            )
        )
        main_subjects = _dedupe([
            *_read_sequence(frame_context, "primary_subject"),
            *_read_sequence(frame_context, "secondary_subjects"),
            *_read_sequence(frame_plan, "primary_subject"),
            *_read_sequence(frame_plan, "secondary_subjects"),
        ])
        key_props_symbols = tuple(_read_sequence(frame_context, "world_elements") or _read_sequence(frame_plan, "world_elements"))
        anchor_affordances = infer_scene_anchor_affordances(
            base_prompt=str(base_prompt or ""),
            main_subjects=tuple(main_subjects),
            key_props=key_props_symbols,
        )
        camera_plan = _sentence(
            _read_value(frame_context, "shot_type") or _read_value(frame_plan, "shot_type"),
            _read_value(frame_context, "shot_purpose") or _read_value(frame_plan, "shot_purpose"),
        )
        visual_story_ip_fusion_plan = _read_mapping(frame_context, "visual_story_ip_fusion_plan") or _read_mapping(frame_plan, "visual_story_ip_fusion_plan")
        return BaseVisualBrief(
            frame_id=frame_id,
            core_message=str(_read_value(frame_context, "frame_source_text") or _read_value(frame_context, "source_text") or _read_value(frame_plan, "narration_fragment") or "").strip(),
            visual_moment=str(base_prompt or "").strip(),
            main_subjects=tuple(main_subjects),
            subject_identity_anchors=tuple(subject_anchors),
            subject_relationship=_infer_subject_relationship(base_prompt, main_subjects),
            setting=_infer_setting(base_prompt),
            spatial_layout=_infer_spatial_layout(base_prompt),
            camera_plan=camera_plan,
            composition_rules=_infer_composition_rules(
                base_prompt=base_prompt,
                main_subjects=main_subjects,
                shot_purpose=str(_read_value(frame_context, "shot_purpose") or _read_value(frame_plan, "shot_purpose") or ""),
            ),
            lighting_mood=_infer_lighting_mood(base_prompt),
            style_surface=_style_surface(
                visual_style_contract=visual_style_contract,
                world_preset=world_preset,
                base_prompt=base_prompt,
            ),
            key_props_symbols=key_props_symbols,
            readability_constraints=tuple(_readability_constraints(main_subjects, subject_anchors)),
            anchor_affordances=anchor_affordances.carriers,
            anchor_forbidden_zones=anchor_affordances.forbidden_zones,
            anchor_integration_notes=anchor_affordances.notes,
            base_image_prompt=str(base_prompt or "").strip(),
            metadata={
                "planner": "BaseVisualBriefPlanner",
                "uses_visual_anchor": False,
                "visual_story_ip_fusion_plan": visual_story_ip_fusion_plan,
            },
        )


def _read_mapping(source: Any, key: str) -> dict[str, Any]:
    value = _read_value(source, key)
    return dict(value) if isinstance(value, Mapping) else {}


def _split_identity_hints(value: str) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(part.strip() for part in value.split("；") if part.strip())


def _infer_spatial_layout(base_prompt: str) -> str:
    text = base_prompt or ""
    signals = [keyword for keyword in ("前景", "中景", "背景", "左侧", "右侧", "中央", "远处", "近处", "上方", "下方") if keyword in text]
    if signals:
        return "画面已有明确空间层次：" + "、".join(_dedupe(signals))
    return "保持主体、环境、道具之间的前景/中景/背景层次清晰"


def _infer_composition_rules(*, base_prompt: str, main_subjects: Sequence[str], shot_purpose: str) -> str:
    if len(main_subjects) >= 2 or any(word in base_prompt for word in ("对比", "对峙", "左右", "两位", "两个")):
        return "使用清晰的双主体构图，主体之间保持可读距离，避免外观和轮廓互相污染"
    if "特写" in base_prompt or "细节" in shot_purpose:
        return "主体细节清楚，背景简化，避免多余元素分散注意力"
    return "主体视觉重心清晰，构图干净，保留必要环境信息"


def _infer_lighting_mood(base_prompt: str) -> str:
    text = base_prompt or ""
    if any(word in text for word in ("夜", "暗", "阴影", "霓虹")):
        return "环境光线与叙事情绪一致，主体轮廓清晰"
    if any(word in text for word in ("课堂", "讲解", "书页", "教学")):
        return "柔和均匀的教育类光线，画面安静清晰"
    return "光线服务主体可读性，避免强烈杂乱阴影"


def _infer_setting(base_prompt: str) -> str:
    text = base_prompt or ""
    for keyword in ("城市", "街道", "课堂", "教室", "书页", "电视", "房间", "宇宙", "森林", "山", "海", "桌面", "讲解板"):
        if keyword in text:
            return f"主体画面环境包含{keyword}相关空间"
    return "根据文案自然形成的主体场景"


def _infer_subject_relationship(base_prompt: str, subjects: Sequence[str]) -> str:
    text = base_prompt or ""
    if any(word in text for word in ("对比", "相比", "左右", "两种", "哪个")):
        return "主体之间形成清晰对比关系"
    if any(word in text for word in ("对峙", "战斗", "冲突")):
        return "主体之间形成戏剧性对峙关系"
    if len(subjects) >= 2:
        return "多个主体同框但主次关系清晰"
    return "单一主体或主题焦点清晰"


def _style_surface(*, visual_style_contract: VisualStyleLayerContract | None, world_preset: Mapping[str, Any] | None, base_prompt: str) -> str:
    parts = []
    if world_preset:
        style_core = world_preset.get("style_core") if isinstance(world_preset, Mapping) else None
        if style_core:
            parts.append(str(style_core))
    if visual_style_contract:
        clause = visual_style_contract.prompt_layer_clause(
            VisualLayerTarget.NON_IP_WORLD,
            VisualLayerTarget.ALL_NON_HUMAN,
            VisualLayerTarget.ENVIRONMENT,
            VisualLayerTarget.BACKGROUND,
        )
        if clause:
            parts.append(clause)
    if _contains_any(base_prompt, ("黑白", "灰", "线条", "扁平", "插画")):
        parts.append("黑白灰扁平插画，线条简洁，二维无纹理")
    return "，".join(_dedupe(parts))


def _readability_constraints(subjects: Sequence[str], subject_anchors: Sequence[str]) -> list[str]:
    constraints = ["主体轮廓清楚", "关键标志清晰可见", "背景服务主体"]
    if len(subjects) >= 2:
        constraints.append("多个主体外观必须清楚区分")
    constraints.extend(subject_anchors)
    return _dedupe(constraints)


def _read_value(container: Any, key: str, default: Any = "") -> Any:
    if container is None:
        return default
    if isinstance(container, Mapping):
        return container.get(key, default)
    return getattr(container, key, default)


def _read_sequence(container: Any, key: str) -> tuple[str, ...]:
    value = _read_value(container, key, ())
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,) if value.strip() else ()
    if isinstance(value, Sequence):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return (str(value).strip(),)


def _sentence(*values: Any) -> str:
    return "，".join(_dedupe(str(value).strip() for value in values if str(value or "").strip()))


def _contains_any(text: str, values: Sequence[str]) -> bool:
    return any(value in text for value in values)


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


__all__ = ["BaseVisualBriefPlanner"]
