from __future__ import annotations

from dataclasses import replace

from pixelle_video.models.prompt_plan import PromptPlan
from pixelle_video.models.scene_cast import SceneCast


def apply_scene_cast_to_prompt_plan(
    prompt_plan: PromptPlan,
    scene_cast: SceneCast,
) -> PromptPlan:
    if prompt_plan.storyboard_plan_id != scene_cast.storyboard_plan_id:
        raise ValueError("scene_cast storyboard_plan_id must match prompt_plan")
    if prompt_plan.frame_id != scene_cast.frame_id:
        raise ValueError("scene_cast frame_id must match prompt_plan")

    metadata = {
        **dict(prompt_plan.metadata),
        "scene_cast_id": scene_cast.scene_cast_id,
        "asset_bible_id": scene_cast.asset_bible_id,
    }
    return replace(
        prompt_plan,
        character_ids=scene_cast.character_ids,
        scene_id=scene_cast.scene_id,
        prop_ids=scene_cast.prop_ids,
        style_id=scene_cast.style_id,
        metadata=metadata,
    )


__all__ = ["apply_scene_cast_to_prompt_plan"]
