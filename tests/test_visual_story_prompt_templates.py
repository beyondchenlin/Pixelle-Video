from __future__ import annotations

from pixelle_video.prompts.visual_story_engine import (
    render_article_visual_route_analysis_prompt,
    render_frame_ip_fusion_prompt,
    render_ip_route_compatibility_prompt,
    render_style_harmonization_prompt,
)


def test_visual_story_templates_render_without_accidental_variables():
    render_article_visual_route_analysis_prompt(
        source_text="百年孤独",
        title="百年孤独",
        ip_profile={"name": "spot dog"},
        channel_strategy={"channel": "book"},
        candidate_count=4,
        target_language="zh",
    )
    render_ip_route_compatibility_prompt(
        article_understanding={"summary": "x"},
        candidate_routes=[{"route_id": "safe"}],
        ip_profile={"name": "spot dog"},
        channel_strategy={},
    )
    render_style_harmonization_prompt(
        selected_route={"route_id": "safe"},
        compatibility_report={"route_id": "safe"},
        ip_profile={"name": "spot dog"},
    )
    render_frame_ip_fusion_prompt(
        selected_route={"route_id": "safe"},
        style_harmonization={"mode": "hybrid_layered"},
        frame_visual_plans=[{"frame_id": "frame-1"}],
        ip_profile={"name": "spot dog"},
        compatibility_report={"route_id": "safe"},
    )
