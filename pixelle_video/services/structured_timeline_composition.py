from __future__ import annotations

from collections.abc import Sequence

SINGLE_ACTOR_TIMELINE_ACTION = (
    "在整条时间线左下方的单一位置，用一只前爪指向贯穿全部阶段的同一条总线"
)
SINGLE_ACTOR_TIMELINE_BINDING = (
    "角色固定在整条时间线左下方的一个位置，只指向同一条总线，"
    "不在各年代或阶段重复出现"
)

_TIMELINE_TOKENS = (
    "时间轴",
    "时间线",
    "timeline",
    "chronology",
)
_MULTI_STAGE_TOKENS = (
    "不同年代",
    "多个年代",
    "各年代",
    "不同阶段",
    "多个阶段",
    "各阶段",
    "职业生涯",
    "发展历程",
    "演变历程",
    "career stages",
)


def is_structured_timeline_scene(*values: str | Sequence[str]) -> bool:
    text = " ".join(_flatten_text(values)).casefold()
    return any(token.casefold() in text for token in (*_TIMELINE_TOKENS, *_MULTI_STAGE_TOKENS))


def _flatten_text(values: Sequence[str | Sequence[str]]) -> tuple[str, ...]:
    result: list[str] = []
    for value in values:
        if isinstance(value, str):
            result.append(value)
            continue
        result.extend(str(item or "") for item in value)
    return tuple(result)


__all__ = [
    "SINGLE_ACTOR_TIMELINE_ACTION",
    "SINGLE_ACTOR_TIMELINE_BINDING",
    "is_structured_timeline_scene",
]
