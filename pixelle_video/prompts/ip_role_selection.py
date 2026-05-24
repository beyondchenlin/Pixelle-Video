"""LLM 驱动的批量逐帧 IP 角色分配 prompt。

── 用途 ──
由 IPFrameAppearancePlanner._llm_role_selection() 调用，
一次 LLM 调用为所有帧决定 role_slot / role_label / presence_level / appearance_description。

── 触发条件 ──
IPFrameAppearancePlanner 构造时传入 llm_client（非 None）。
LLM 调用失败 → 自动回退 _rule_based_role_selection()。

── 入口 ──
build_ip_role_selection_prompt(ip_profile_json=..., frames_json=...) → prompt 字符串
parse_ip_role_selection_response(raw_response) → list[dict] | None（None 触发回退）
"""

from __future__ import annotations

import json
from typing import Any

from pixelle_video.prompts.template_loader import RenderedPrompt, render_prompt_template
from pixelle_video.utils.json_parsing import parse_llm_json_response


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


def parse_ip_role_selection_response(raw_response: str) -> list[dict[str, Any]] | None:
    """Parse the LLM response to extract role selection results.

    Returns a list of per-frame dicts with keys:
        frame_index, role_slot, role_label, presence_level, appearance_description, reason
    Returns None if parsing fails (triggers rule-based fallback).
    """
    text = raw_response.strip()
    if not text:
        return None
    try:
        payload = parse_llm_json_response(text, allow_code_fence=True, allow_embedded_json=False)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(payload, list):
        return None
    valid_slots = {"protagonist", "supporting", "passerby", "absent"}
    results: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            return None
        slot = item.get("role_slot")
        if not isinstance(slot, str) or slot not in valid_slots:
            return None
        appearance_desc = item.get("appearance_description")
        if not isinstance(appearance_desc, str):
            appearance_desc = ""
        results.append(
            {
                "frame_index": item.get("frame_index", 0),
                "role_slot": slot,
                "role_label": item.get("role_label", "场景参与者"),
                "presence_level": item.get("presence_level", "半身出镜"),
                "appearance_description": appearance_desc,
                "reason": item.get("reason", ""),
            }
        )
    return results if results else None


__all__ = [
    "build_ip_role_selection_prompt",
    "parse_ip_role_selection_response",
    "render_ip_role_selection_prompt",
]



def build_ip_role_selection_prompt(
    *,
    ip_profile_json: str,
    frames_json: str,
) -> str:
    return render_ip_role_selection_prompt(
        ip_profile_json=ip_profile_json,
        frames_json=frames_json,
    ).text
