from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from pixelle_video.prompts.template_loader import RenderedPrompt, render_prompt_template


def render_frame_visual_plan_batch_prompt(
    *,
    article_summary: Mapping[str, Any] | None,
    selected_visual_route: Mapping[str, Any] | None,
    batch_payload: Mapping[str, Any],
    continuity_ledger: Mapping[str, Any] | None,
    target_language: str = "zh",
) -> RenderedPrompt:
    """Render article-bound frame visual planning only."""

    return render_prompt_template(
        "frame_visual_plan_batch",
        {
            "article_summary_json": json.dumps(
                dict(article_summary or {}),
                ensure_ascii=False,
                indent=2,
            ),
            "selected_visual_route_json": json.dumps(
                dict(selected_visual_route or {}),
                ensure_ascii=False,
                indent=2,
            ),
            "batch_payload_json": json.dumps(
                dict(batch_payload or {}),
                ensure_ascii=False,
                indent=2,
            ),
            "continuity_ledger_json": json.dumps(
                dict(continuity_ledger or {}),
                ensure_ascii=False,
                indent=2,
            ),
            "target_language_json": json.dumps(
                target_language,
                ensure_ascii=False,
            ),
        },
    )


__all__ = ["render_frame_visual_plan_batch_prompt"]
