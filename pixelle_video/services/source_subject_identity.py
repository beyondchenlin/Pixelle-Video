from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SourceSubjectIdentityHint:
    subject_id: str
    aliases: tuple[str, ...]
    positive_visual_anchors: tuple[str, ...]
    separation_rules: tuple[str, ...] = ()

    def prompt_clause(self) -> str:
        anchors = "，".join(self.positive_visual_anchors)
        rules = "，".join(self.separation_rules)
        if rules:
            return f"{self.subject_id}视觉锚点：{anchors}；区分规则：{rules}"
        return f"{self.subject_id}视觉锚点：{anchors}"


_BUILTIN_SOURCE_SUBJECT_HINTS: tuple[SourceSubjectIdentityHint, ...] = (
    SourceSubjectIdentityHint(
        subject_id="奥特曼",
        aliases=("奥特曼", "ultraman", "ultra man"),
        positive_visual_anchors=(
            "银红配色的巨大外星英雄",
            "椭圆黄色眼睛",
            "头部中线或头冠轮廓",
            "胸前圆形或宝石状能量计时器",
            "没有红色披风",
        ),
        separation_rules=(
            "不要画成蓝色紧身衣人类英雄",
            "不要给奥特曼添加红色披风",
        ),
    ),
    SourceSubjectIdentityHint(
        subject_id="超人",
        aliases=("超人", "superman", "super man"),
        positive_visual_anchors=(
            "人类男性超级英雄",
            "蓝色紧身战衣",
            "红色披风",
            "胸前盾形S标志或简化S徽章",
            "自然人类脸和黑发",
        ),
        separation_rules=(
            "不要画成银色外星面具",
            "不要画成奥特曼盔甲",
            "不要使用椭圆黄色发光眼睛",
        ),
    ),
)


def source_subject_identity_prompt(
    *,
    base_prompt: str = "",
    frame_context: Mapping[str, Any] | None = None,
    frame_plan: Any = None,
    generation_world_profile: Any = None,
) -> str:
    """Return concise image-facing visual anchors for named source subjects.

    This belongs in the final provider prompt because it describes visible form.
    It is not an internal instruction such as role_slot, priority, or layer policy.
    """
    signal_text = _source_signal_text(
        base_prompt=base_prompt,
        frame_context=frame_context,
        frame_plan=frame_plan,
        generation_world_profile=generation_world_profile,
    )
    if not signal_text:
        return ""

    matched = [
        hint
        for hint in _BUILTIN_SOURCE_SUBJECT_HINTS
        if _contains_any(signal_text, hint.aliases)
    ]
    if not matched:
        return ""

    return "；".join(hint.prompt_clause() for hint in matched)


def _source_signal_text(
    *,
    base_prompt: str,
    frame_context: Mapping[str, Any] | None,
    frame_plan: Any,
    generation_world_profile: Any,
) -> str:
    parts: list[str] = [base_prompt or ""]
    for container in (frame_context, frame_plan):
        for key in (
            "source_text",
            "frame_source_text",
            "visual_goal",
            "prompt_intent",
            "primary_subject",
            "secondary_subjects",
            "continuity_anchors",
            "world_elements",
        ):
            parts.extend(_read_sequence(container, key))
    for key in ("summary", "story_constraints", "ip_integration_guidance"):
        parts.extend(_read_sequence(generation_world_profile, key))
    return " ".join(part for part in parts if part).lower()


def _read_sequence(container: Any, key: str) -> tuple[str, ...]:
    if container is None:
        return ()
    if isinstance(container, Mapping):
        value = container.get(key)
    else:
        value = getattr(container, key, None)
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Sequence):
        return tuple(str(item) for item in value if str(item).strip())
    return (str(value),)


def _contains_any(text: str, aliases: Sequence[str]) -> bool:
    lowered = text.lower()
    return any(alias.lower() in lowered for alias in aliases)


__all__ = ["SourceSubjectIdentityHint", "source_subject_identity_prompt"]
