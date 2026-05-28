from __future__ import annotations

import json
from typing import Any, Sequence

from pixelle_video.prompts.template_loader import RenderedPrompt, render_prompt_template


def render_visual_anchor_integration_prompt(
    *,
    base_visual_briefs_json: Sequence[dict[str, Any]],
    anchor_profile_json: dict[str, Any],
    visual_signature_policy_json: dict[str, Any] | None = None,
    cadence_plan_json: Sequence[dict[str, Any]] = (),
) -> RenderedPrompt:
    return render_prompt_template(
        "visual_anchor_integration",
        {
            "base_visual_briefs_json": json.dumps(
                list(base_visual_briefs_json), ensure_ascii=False, indent=2
            ),
            "anchor_profile_json": json.dumps(anchor_profile_json, ensure_ascii=False, indent=2),
            "visual_signature_policy_json": json.dumps(
                dict(visual_signature_policy_json or {}), ensure_ascii=False, indent=2
            ),
            "cadence_plan_json": json.dumps(list(cadence_plan_json), ensure_ascii=False, indent=2),
        },
    )


__all__ = ["render_visual_anchor_integration_prompt"]
