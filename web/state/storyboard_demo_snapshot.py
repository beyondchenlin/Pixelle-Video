from __future__ import annotations

from typing import Any

_DEMO_PLAN_ID = "demo_plan_0000000000000001"
_DEMO_SOURCE_DIGEST = "0" * 64
_DEMO_EDITABLE_FIELDS: tuple[str, ...] = (
    "shot_type",
    "shot_purpose",
    "primary_subject",
    "world_elements",
    "continuity_anchors",
    "focus_detail",
    "prompt_intent",
)

_DEMO_FRAMES: tuple[dict[str, Any], ...] = (
    {
        "shot_type": "medium_shot",
        "shot_purpose": "establishing",
        "primary_subject": "主角",
        "world_elements": ["天空", "山脉"],
        "continuity_anchors": ["红围巾"],
        "focus_detail": "主角的表情特写",
        "prompt_intent": "展示主角的决心与信念",
    },
    {
        "shot_type": "close_up",
        "shot_purpose": "revealing",
        "primary_subject": "反派角色",
        "world_elements": ["洞穴", "水晶"],
        "continuity_anchors": ["护身符"],
        "focus_detail": "反派手中的隐藏物品",
        "prompt_intent": "揭示隐藏的神器",
    },
    {
        "shot_type": "wide_shot",
        "shot_purpose": "climax",
        "primary_subject": "双方对峙",
        "world_elements": ["风暴", "废墟"],
        "continuity_anchors": ["断剑"],
        "focus_detail": "碰撞瞬间",
        "prompt_intent": "呈现史诗级的对抗场景",
    },
)


def build_demo_planning_snapshot() -> dict[str, Any]:
    """Build a demo planning_snapshot that satisfies build_storyboard_preview_rows() contract.

    Returns a stable, idempotent dict with 3 placeholder frames.  The demo snapshot
    uses a distinguishable plan_id prefix so downstream code can detect it is not a
    real generation result.
    """
    identity_frames: list[dict[str, Any]] = []
    display_frames: list[dict[str, Any]] = []
    for index, values in enumerate(_DEMO_FRAMES, start=1):
        frame_id = f"demo_frame_{index:04d}"
        identity_frames.append(
            {
                "frame_id": frame_id,
                "index": index,
                **_make_editable_dict(values),
            }
        )
        display_frames.append(
            {
                "scene_id": f"demo-scene-{index}",
                **_make_editable_dict(values),
            }
        )

    return {
        "storyboard_generation": {
            "plan_id": _DEMO_PLAN_ID,
            "revision": 1,
            "source_digest": _DEMO_SOURCE_DIGEST,
            "frames": identity_frames,
        },
        "frames": display_frames,
    }


def _make_editable_dict(values: dict[str, Any]) -> dict[str, Any]:
    return {field: values.get(field, "") for field in _DEMO_EDITABLE_FIELDS}
