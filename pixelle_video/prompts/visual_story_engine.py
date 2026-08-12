from __future__ import annotations

import json
from collections.abc import Mapping, Sequence

from pixelle_video.prompts.template_loader import RenderedPrompt, render_prompt_template


def render_article_visual_route_analysis_prompt(
    *,
    source_text: str,
    title: str | None = None,
    channel_strategy: Mapping[str, object] | None = None,
    user_intent_hint: str | None = None,
    candidate_count: int = 5,
    target_language: str = "zh",
) -> RenderedPrompt:
    """Render the content-only visual route analysis prompt.

    Recurring IP/visual-signature data is intentionally not accepted by this
    boundary, so callers cannot accidentally reintroduce identity-aware route
    selection through a compatibility argument.
    """

    return render_prompt_template(
        "article_visual_route_analysis",
        {
            "source_text_json": json.dumps(source_text, ensure_ascii=False),
            "title_json": json.dumps(title, ensure_ascii=False),
            "channel_strategy_json": json.dumps(
                dict(channel_strategy or {}),
                ensure_ascii=False,
                indent=2,
            ),
            "user_intent_hint_json": json.dumps(
                user_intent_hint,
                ensure_ascii=False,
            ),
            "candidate_count": int(candidate_count),
            "target_language_json": json.dumps(
                target_language,
                ensure_ascii=False,
            ),
        },
    )


def render_article_visual_route_score_repair_prompt(
    *,
    article_understanding: Mapping[str, object],
    candidates: Sequence[Mapping[str, object]],
) -> RenderedPrompt:
    """Render bounded score-only repair without resending the full source text."""

    return render_prompt_template(
        "article_visual_route_score_repair",
        {
            "article_understanding_json": json.dumps(
                dict(article_understanding),
                ensure_ascii=False,
                indent=2,
            ),
            "candidates_json": json.dumps(
                [dict(candidate) for candidate in candidates],
                ensure_ascii=False,
                indent=2,
            ),
        },
    )


__all__ = [
    "render_article_visual_route_analysis_prompt",
    "render_article_visual_route_score_repair_prompt",
]
