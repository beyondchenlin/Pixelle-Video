from __future__ import annotations

import json
from typing import Any, Sequence

from pixelle_video.prompts.template_loader import RenderedPrompt, render_prompt_template


def render_base_visual_brief_prompt(*, frames_json: Sequence[dict[str, Any]], style_profile: dict[str, Any] | None = None) -> RenderedPrompt:
    return render_prompt_template(
        "base_visual_brief",
        {
            "frames_json": json.dumps(list(frames_json), ensure_ascii=False, indent=2),
            "style_profile_json": json.dumps(style_profile or {}, ensure_ascii=False, indent=2),
        },
    )


__all__ = ["render_base_visual_brief_prompt"]
