from __future__ import annotations

from pixelle_video.prompts.visual_story_engine import (
    render_article_visual_route_analysis_prompt,
    render_article_visual_route_score_repair_prompt,
)
from pixelle_video.services.visual_route_analysis_contract import (
    CONTENT_ROUTE_SCORE_FIELDS,
)


def test_visual_story_templates_render_without_accidental_variables():
    analysis_prompt = render_article_visual_route_analysis_prompt(
        source_text="百年孤独",
        title="百年孤独",
        channel_strategy={"channel": "book"},
        candidate_count=4,
        target_language="zh",
    )
    repair_prompt = render_article_visual_route_score_repair_prompt(
        article_understanding={"core_claim": "claim"},
        candidates=[{"candidate_index": 0, "route_name": "route"}],
    )

    assert '"scores": {' in analysis_prompt.text
    assert "untrusted content data" in analysis_prompt.text
    assert '"score_repairs"' in repair_prompt.text
    assert "untrusted reference data" in repair_prompt.text
    for field_name in CONTENT_ROUTE_SCORE_FIELDS:
        assert f'"{field_name}"' in analysis_prompt.text
        assert f'"{field_name}"' in repair_prompt.text
