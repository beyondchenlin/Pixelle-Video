from __future__ import annotations

import re
from collections.abc import Sequence

_SUBJECT_SPLIT_PATTERN = re.compile(r"[,，、;；|/]+")
_COLLECTIVE_SUBJECT_TOKENS = (
    "团队",
    "小组",
    "成员",
    "人群",
    "观众",
    "城市",
    "公司",
    "产品",
    "系统",
    "team",
    "group",
    "crowd",
    "audience",
    "company",
    "system",
)
_PROTAGONIST_ACTIONS = (
    "站在",
    "坐在",
    "走在",
    "走向",
    "面对",
    "凝视",
    "演讲",
    "展示",
    "思考",
    "手持",
    "stands",
    "sits",
    "walks",
    "faces",
    "watches",
    "presents",
    "speaks",
    "holds",
)
_DAWN_TOKENS = (
    "破晓",
    "日出",
    "升起的太阳",
    "黎明",
    "dawn",
    "sunrise",
    "rising sun",
)


def protected_protagonist_subject(
    required_subjects: Sequence[str],
    *scene_values: str | Sequence[str],
) -> str:
    scene = " ".join(_flatten_text(scene_values)).casefold()
    for label in required_subjects:
        for candidate in _subject_candidates(label):
            lowered = candidate.casefold()
            if any(token.casefold() in lowered for token in _COLLECTIVE_SUBJECT_TOKENS):
                continue
            if any(
                f"{lowered}{action.casefold()}" in scene
                or f"{lowered} {action.casefold()}" in scene
                for action in _PROTAGONIST_ACTIONS
            ):
                return candidate
    return ""


def protected_protagonist_action(
    subject: str,
    *scene_values: str | Sequence[str],
) -> str:
    subject = " ".join(str(subject or "").split())
    scene = " ".join(_flatten_text(scene_values)).casefold()
    target = (
        f"{subject}身后的同一处破晓日出"
        if any(token.casefold() in scene for token in _DAWN_TOKENS)
        else f"{subject}面对的同一处关键转折"
    )
    return f"固定站在{subject}侧后方的地面上，用一只前爪指向{target}"


def protected_protagonist_binding(subject: str) -> str:
    subject = " ".join(str(subject or "").split())
    return (
        f"{subject}保持为画面中央唯一人类主角；"
        "一个指定角色固定站在侧后方地面，只在一个位置提供指引，"
        f"不替代或复制{subject}"
    )


def _subject_candidates(label: str) -> tuple[str, ...]:
    return tuple(
        candidate
        for part in _SUBJECT_SPLIT_PATTERN.split(str(label or ""))
        if (candidate := " ".join(part.split()))
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
    "protected_protagonist_action",
    "protected_protagonist_binding",
    "protected_protagonist_subject",
]
