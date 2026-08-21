from __future__ import annotations

from collections.abc import Sequence

SINGLE_FACILITATOR_GROUP_ACTION = (
    "固定站在讨论桌旁的地面上，用一只前爪指向桌面中央同一份定稿方案"
)
SINGLE_FACILITATOR_GROUP_BINDING = (
    "一个指定角色固定站在讨论桌旁的地面上，只在一个位置主持；"
    "设计团队成员保持为人类，不采用指定角色外观"
)

_GROUP_SUBJECT_TOKENS = (
    "团队",
    "小组",
    "成员",
    "team",
    "group",
    "committee",
    "crew",
)
_GROUP_INTERACTION_TOKENS = (
    "讨论",
    "讨论桌",
    "圆桌",
    "会议",
    "协作",
    "推敲",
    "meeting",
    "workshop",
    "discussion",
    "collaboration",
    "review",
)
_DESIGN_REVISION_TOKENS = (
    "设计",
    "方案",
    "定稿",
    "修改",
    "修订",
    "design",
    "proposal",
    "draft",
    "revision",
)


def is_structured_group_scene(*values: str | Sequence[str]) -> bool:
    text = " ".join(_flatten_text(values)).casefold()
    return all(
        any(token.casefold() in text for token in tokens)
        for tokens in (
            _GROUP_SUBJECT_TOKENS,
            _GROUP_INTERACTION_TOKENS,
            _DESIGN_REVISION_TOKENS,
        )
    )


def _flatten_text(values: Sequence[str | Sequence[str]]) -> tuple[str, ...]:
    result: list[str] = []
    for value in values:
        if isinstance(value, str):
            result.append(value)
            continue
        result.extend(str(item or "") for item in value)
    return tuple(result)


__all__ = [
    "SINGLE_FACILITATOR_GROUP_ACTION",
    "SINGLE_FACILITATOR_GROUP_BINDING",
    "is_structured_group_scene",
]
