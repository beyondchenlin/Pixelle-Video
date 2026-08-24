from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from pixelle_video.models.prompt_plan import PromptPlan


def prompt_plan_public_projection_payload(prompt_plan: PromptPlan) -> dict[str, Any]:
    """Build the explicit public read model for prompt-plan projection APIs.

    The public API boundary must not depend on ``PromptPlan.to_dict()`` because
    that method is the persistence representation and may grow internal fields.
    """

    return {
        "prompt_plan_id": prompt_plan.prompt_plan_id,
        "storyboard_plan_id": prompt_plan.storyboard_plan_id,
        "frame_id": prompt_plan.frame_id,
        "image_prompt_draft_id": prompt_plan.image_prompt_draft_id,
        "prompt_sections": dict(prompt_plan.prompt_sections),
        "final_prompt": prompt_plan.final_prompt,
        "final_negative_prompt": prompt_plan.final_negative_prompt,
        "identity_content_sha256": prompt_plan.identity_content_sha256,
        "contract_content_sha256": prompt_plan.contract_content_sha256,
        "contract_version": prompt_plan.contract_version,
        "source_trace_id": prompt_plan.source_trace_id,
        "character_ids": list(prompt_plan.character_ids),
        "scene_id": prompt_plan.scene_id,
        "prop_ids": list(prompt_plan.prop_ids),
        "style_id": prompt_plan.style_id,
        "metadata": _json_safe_value(prompt_plan.metadata),
    }


def _json_safe_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_safe_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe_value(item) for item in value]
    return deepcopy(value)


__all__ = ["prompt_plan_public_projection_payload"]
