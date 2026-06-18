"""Prompt helpers for batch IP role selection."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from pixelle_video.models.ip_prompt_planning import IPRoleSlot
from pixelle_video.models.ip_role_selection import IPRoleSelectionResponse
from pixelle_video.prompts.template_loader import RenderedPrompt, render_prompt_template
from pixelle_video.utils.json_parsing import parse_llm_json_response

_VALID_ROLE_SLOTS = {"protagonist", "supporting", "passerby", "absent"}
_WRAPPER_KEYS = (
    "role_selections",
    "ip_role_selections",
    "role_selection",
    "selections",
    "decisions",
    "results",
    "items",
    "data",
    "frames",
    "roles",
    "output",
    "result",
)
_SLOT_KEYS = (
    "role_slot",
    "roleSlot",
    "role",
    "ip_role",
    "ipRole",
    "slot",
    "role_type",
    "roleType",
    "role_choice",
    "character_role",
    "presence_role",
    "ip_presence_role",
)
_FRAME_INDEX_KEYS = ("frame_index", "frameIndex", "index", "frame", "frame_id", "frameId")
_ROLE_LABEL_KEYS = (
    "role_label",
    "roleLabel",
    "label",
    "role_name",
    "roleName",
    "role_title",
    "character_label",
    "function",
)
_PRESENCE_LEVEL_KEYS = (
    "presence_level",
    "presenceLevel",
    "presence",
    "visibility",
    "visibility_level",
    "shot_presence",
    "framing",
    "composition",
)
_APPEARANCE_KEYS = (
    "appearance_description",
    "appearanceDescription",
    "appearance",
    "visual_description",
    "ip_description",
    "scene_description",
    "image_prompt",
    "prompt_fragment",
    "description",
)
_REASON_KEYS = ("reason", "rationale", "explanation", "justification")

_ROLE_SLOT_ALIASES = {
    "protagonist": {
        "hero",
        "lead",
        "main",
        "main_character",
        "primary",
        "foreground",
        "central",
        "center",
        "strong_identity",
        "primary_subject",
        "protagonist",
        "主角",
        "主视觉",
        "核心角色",
        "主体",
        "前景",
        "强出镜",
        "高出镜",
    },
    "supporting": {
        "support",
        "supporting",
        "supporting_character",
        "secondary",
        "side",
        "side_character",
        "companion",
        "guide",
        "assistant",
        "scene_integrated",
        "balanced_narrative",
        "co_host",
        "配角",
        "辅助",
        "陪伴",
        "导游",
        "讲解",
        "旁侧",
        "场景参与者",
        "平衡叙事",
    },
    "passerby": {
        "passerby",
        "background",
        "background_extra",
        "extra",
        "ambient",
        "cameo",
        "minor",
        "low_intrusion",
        "symbolic",
        "symbolic_only",
        "distant",
        "路人",
        "背景",
        "点缀",
        "旁观",
        "低侵入",
        "符号",
        "远景",
        "弱出镜",
    },
    "absent": {
        "absent",
        "none",
        "no_ip",
        "not_present",
        "offscreen",
        "hidden",
        "omit",
        "do_not_show",
        "no_show",
        "缺席",
        "不出现",
        "不出镜",
        "不入镜",
        "画外",
        "无",
        "无ip",
        "不要出现",
        "完全不出镜",
    },
}

_ROLE_SLOT_MARKERS = (
    ("absent", ("not present", "do not show", "no ip", "no character", "不出现", "不出镜", "不入镜", "不要出现")),
    ("passerby", ("background", "passerby", "low intrusion", "symbolic", "cameo", "路人", "背景", "低侵入", "点缀")),
    ("protagonist", ("main character", "primary subject", "hero", "lead", "主角", "主视觉", "核心角色")),
    ("supporting", ("supporting", "secondary", "side character", "companion", "guide", "配角", "辅助", "陪伴", "导游")),
)


def render_ip_role_selection_prompt(
    *,
    ip_profile_json: str,
    frames_json: str,
) -> RenderedPrompt:
    return render_prompt_template(
        "ip_role_selection",
        {
            "ip_profile_json": ip_profile_json,
            "frames_json": frames_json,
        },
    )


def build_ip_role_selection_prompt(
    *,
    ip_profile_json: str,
    frames_json: str,
) -> str:
    return render_ip_role_selection_prompt(
        ip_profile_json=ip_profile_json,
        frames_json=frames_json,
    ).text


def parse_ip_role_selection_response(raw_response: Any) -> list[dict[str, Any]] | None:
    """Parse per-frame IP role selections from tolerant LLM JSON output."""
    if isinstance(raw_response, IPRoleSelectionResponse):
        return raw_response.to_role_dicts()

    payload = _parse_role_selection_payload(raw_response)
    if isinstance(payload, IPRoleSelectionResponse):
        return payload.to_role_dicts()

    items = _coerce_role_selection_items(payload)
    if not items:
        return None

    role_selections: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        normalized = _normalize_role_selection_item(item, fallback_index=index)
        if normalized is None:
            return None
        role_selections.append(normalized)
    if not role_selections:
        return None

    try:
        return IPRoleSelectionResponse.model_validate(
            {"role_selections": role_selections}
        ).to_role_dicts()
    except ValidationError:
        return None


def _parse_role_selection_payload(raw_response: Any) -> Any | None:
    if isinstance(raw_response, IPRoleSelectionResponse):
        return raw_response
    if isinstance(raw_response, (list, dict)):
        return raw_response
    if not isinstance(raw_response, str):
        return None

    text = raw_response.strip()
    if not text:
        return None
    try:
        return parse_llm_json_response(
            text,
            allow_code_fence=True,
            allow_embedded_json=True,
        )
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


def _coerce_role_selection_items(payload: Any) -> list[Any] | None:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, str):
        nested_payload = _parse_role_selection_payload(payload)
        if nested_payload is not None and nested_payload is not payload:
            return _coerce_role_selection_items(nested_payload)
        return None
    if not isinstance(payload, Mapping):
        return None

    if _looks_like_role_selection_item(payload):
        return [payload]

    for key in _WRAPPER_KEYS:
        if key in payload:
            nested_items = _coerce_role_selection_items(payload[key])
            if nested_items:
                return nested_items

    if _is_keyed_role_selection_mapping(payload):
        return [
            value
            for _, value in sorted(
                payload.items(),
                key=lambda item: _sortable_frame_key(item[0]),
            )
        ]

    for value in payload.values():
        if isinstance(value, (list, dict, str)):
            nested_items = _coerce_role_selection_items(value)
            if nested_items:
                return nested_items

    return None


def _looks_like_role_selection_item(item: Mapping[Any, Any]) -> bool:
    return _get_first(item, _SLOT_KEYS) is not None


def _is_keyed_role_selection_mapping(payload: Mapping[Any, Any]) -> bool:
    values = list(payload.values())
    return bool(values) and all(
        isinstance(value, Mapping) and _looks_like_role_selection_item(value)
        for value in values
    )


def _normalize_role_selection_item(
    item: Any,
    *,
    fallback_index: int,
) -> dict[str, Any] | None:
    if not isinstance(item, Mapping):
        return None

    slot = _normalize_role_slot(_get_first(item, _SLOT_KEYS))
    if slot is None:
        return None

    role_label = _coerce_text(_get_first(item, _ROLE_LABEL_KEYS), default="")
    presence_level = _coerce_text(_get_first(item, _PRESENCE_LEVEL_KEYS), default="")
    appearance_desc = _coerce_text(_get_first(item, _APPEARANCE_KEYS), default="")
    reason = _coerce_text(_get_first(item, _REASON_KEYS), default="")
    frame_index = _coerce_int(_get_first(item, _FRAME_INDEX_KEYS), default=fallback_index)

    if not role_label:
        role_label = _default_role_label(slot)
    if not presence_level:
        presence_level = _default_presence_level(slot)
    if slot == "absent":
        appearance_desc = ""

    return {
        "frame_index": frame_index,
        "role_slot": slot,
        "role_label": role_label,
        "presence_level": presence_level,
        "appearance_description": appearance_desc,
        "reason": reason,
    }


def _normalize_role_slot(value: Any) -> str | None:
    if isinstance(value, IPRoleSlot):
        return value.value

    text = _coerce_text(value, default="").strip()
    if not text:
        return None

    lowered = text.lower()
    token = re.sub(r"[^0-9a-zA-Z_\u4e00-\u9fff]+", "_", lowered).strip("_")
    token = token.removeprefix("iproleslot_").removeprefix("ip_role_slot_")
    if token in _VALID_ROLE_SLOTS:
        return token

    compact_text = re.sub(r"\s+", "", lowered)
    for slot, aliases in _ROLE_SLOT_ALIASES.items():
        if token in aliases or compact_text in aliases:
            return slot

    readable_text = re.sub(r"[_-]+", " ", lowered)
    for slot, markers in _ROLE_SLOT_MARKERS:
        if any(marker in readable_text or marker in text for marker in markers):
            return slot

    return None


def _get_first(item: Mapping[Any, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in item:
            return item[key]

    normalized_items = {
        _normalize_field_key(key): value
        for key, value in item.items()
        if isinstance(key, str)
    }
    for key in keys:
        normalized_key = _normalize_field_key(key)
        if normalized_key in normalized_items:
            return normalized_items[normalized_key]
    return None


def _normalize_field_key(key: str) -> str:
    return re.sub(r"[^0-9a-z]+", "", key.lower())


def _coerce_text(value: Any, *, default: str) -> str:
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (list, tuple)):
        parts = [_coerce_text(item, default="") for item in value]
        return "; ".join(part for part in parts if part)
    if isinstance(value, Mapping):
        return json.dumps(value, ensure_ascii=False)
    return str(value).strip()


def _coerce_int(value: Any, *, default: int) -> int:
    if isinstance(value, bool) or value is None:
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        match = re.search(r"-?\d+", value)
        if match:
            return int(match.group(0))
    return default


def _sortable_frame_key(key: Any) -> tuple[int, str]:
    text = str(key)
    match = re.search(r"-?\d+", text)
    if match:
        return (int(match.group(0)), text)
    return (10**9, text)


def _default_role_label(slot: str) -> str:
    return {
        "protagonist": "protagonist",
        "supporting": "supporting character",
        "passerby": "background passerby",
        "absent": "absent",
    }[slot]


def _default_presence_level(slot: str) -> str:
    return {
        "protagonist": "prominent presence",
        "supporting": "supporting presence",
        "passerby": "subtle background presence",
        "absent": "not visible",
    }[slot]


__all__ = [
    "build_ip_role_selection_prompt",
    "parse_ip_role_selection_response",
    "render_ip_role_selection_prompt",
]
