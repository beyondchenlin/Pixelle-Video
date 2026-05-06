"""LLM 驱动的批量逐帧 IP 角色分配 prompt。

── 用途 ──
由 IPFrameAppearancePlanner._llm_role_selection() 调用，
一次 LLM 调用为所有帧决定 role_slot / role_label / presence_level。

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

from pixelle_video.utils.json_parsing import parse_llm_json_response


IP_ROLE_SELECTION_PROMPT = """# Role
You are a casting director for an animated video. An IP mascot character needs to be placed into each frame.

## IP Character Profile
{ip_profile_json}

## Frame Sequence
{frames_json}

## Instructions
For each frame, decide:
1. **role_slot**: Which narrative role does the IP fill?
   - "protagonist": The IP is the MAIN SUBJECT. Replace the frame's protagonist.
   - "supporting": The IP is a SECONDARY character alongside the main subject.
   - "passerby": The IP is a BACKGROUND element blended into the environment.
   - "absent": The IP does NOT appear.

2. **role_label**: A concise Chinese label describing the IP's function in this frame
   (e.g., "导游讲解者", "情感陪伴者", "路人观察者", "画面主角", "画外不出镜")

3. **presence_level**: How visible is the IP?
   - "全身出镜", "半身出镜", "局部细节", "远景融入", "完全不出镜"

4. **reason**: One sentence explaining WHY this choice fits the frame content.

Rules:
- Frame 1 (opening) typically uses "supporting" or "protagonist" for scene establishment
- Vary roles across frames — do NOT use the same role for all frames
- PROTECTED subjects (historical buildings, religious figures, real people) → use "passerby" or "absent"
- Pure landscape/nature frames → use "passerby" or "absent"
- Emotional/climax frames → use "supporting" for companionship, not "protagonist"
- Balance the IP's prominence so it doesn't dominate every frame

Return a JSON array with one object per frame:
```json
[
  {{
    "frame_index": 0,
    "role_slot": "supporting",
    "role_label": "导游讲解者",
    "presence_level": "半身出镜",
    "reason": "..."
  }}
]
```

Only output the JSON array. No other text.
"""


def build_ip_role_selection_prompt(
    *,
    ip_profile_json: str,
    frames_json: str,
) -> str:
    return IP_ROLE_SELECTION_PROMPT.format(
        ip_profile_json=ip_profile_json,
        frames_json=frames_json,
    )


def parse_ip_role_selection_response(raw_response: str) -> list[dict[str, Any]] | None:
    """Parse the LLM response to extract role selection results.

    Returns a list of per-frame dicts with keys:
        frame_index, role_slot, role_label, presence_level, reason
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
        results.append(
            {
                "frame_index": item.get("frame_index", 0),
                "role_slot": slot,
                "role_label": item.get("role_label", "场景参与者"),
                "presence_level": item.get("presence_level", "半身出镜"),
                "reason": item.get("reason", ""),
            }
        )
    return results if results else None


__all__ = [
    "build_ip_role_selection_prompt",
    "parse_ip_role_selection_response",
    "IP_ROLE_SELECTION_PROMPT",
]
