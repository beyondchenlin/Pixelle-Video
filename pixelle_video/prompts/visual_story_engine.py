from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from pixelle_video.prompts.template_loader import RenderedPrompt, render_prompt_template


def render_article_visual_route_analysis_prompt(
    *,
    source_text: str,
    title: str | None = None,
    ip_profile: Mapping[str, Any] | None = None,
    channel_strategy: Mapping[str, Any] | None = None,
    user_intent_hint: str | None = None,
    candidate_count: int = 5,
    target_language: str = "zh",
) -> RenderedPrompt:
    return render_prompt_template(
        "article_visual_route_analysis",
        {
            "source_text_json": json.dumps(source_text, ensure_ascii=False),
            "title_json": json.dumps(title, ensure_ascii=False),
            "ip_profile_json": json.dumps(dict(ip_profile or {}), ensure_ascii=False, indent=2),
            "channel_strategy_json": json.dumps(dict(channel_strategy or {}), ensure_ascii=False, indent=2),
            "user_intent_hint_json": json.dumps(user_intent_hint, ensure_ascii=False),
            "candidate_count": int(candidate_count),
            "target_language_json": json.dumps(target_language, ensure_ascii=False),
        },
    )


def render_ip_route_compatibility_prompt(
    *,
    article_understanding: Mapping[str, Any],
    candidate_routes: Sequence[Mapping[str, Any]],
    ip_profile: Mapping[str, Any] | None,
    channel_strategy: Mapping[str, Any] | None = None,
    target_language: str = "zh",
) -> RenderedPrompt:
    return render_prompt_template(
        "ip_route_compatibility",
        {
            "article_understanding_json": json.dumps(dict(article_understanding), ensure_ascii=False, indent=2),
            "candidate_routes_json": json.dumps([dict(route) for route in candidate_routes], ensure_ascii=False, indent=2),
            "ip_profile_json": json.dumps(dict(ip_profile or {}), ensure_ascii=False, indent=2),
            "channel_strategy_json": json.dumps(dict(channel_strategy or {}), ensure_ascii=False, indent=2),
            "target_language_json": json.dumps(target_language, ensure_ascii=False),
        },
    )


def render_style_harmonization_prompt(
    *,
    selected_route: Mapping[str, Any],
    compatibility_report: Mapping[str, Any] | None,
    ip_profile: Mapping[str, Any] | None,
    image_config: Mapping[str, Any] | None = None,
    target_language: str = "zh",
) -> RenderedPrompt:
    return render_prompt_template(
        "style_harmonization",
        {
            "selected_route_json": json.dumps(dict(selected_route), ensure_ascii=False, indent=2),
            "compatibility_report_json": json.dumps(dict(compatibility_report or {}), ensure_ascii=False, indent=2),
            "ip_profile_json": json.dumps(dict(ip_profile or {}), ensure_ascii=False, indent=2),
            "image_config_json": json.dumps(dict(image_config or {}), ensure_ascii=False, indent=2),
            "target_language_json": json.dumps(target_language, ensure_ascii=False),
        },
    )


def render_frame_ip_fusion_prompt(
    *,
    selected_route: Mapping[str, Any],
    style_harmonization: Mapping[str, Any],
    frame_visual_plans: Sequence[Mapping[str, Any]],
    ip_profile: Mapping[str, Any] | None,
    compatibility_report: Mapping[str, Any] | None,
    target_language: str = "zh",
) -> RenderedPrompt:
    return render_prompt_template(
        "frame_ip_fusion",
        {
            "selected_route_json": json.dumps(dict(selected_route), ensure_ascii=False, indent=2),
            "style_harmonization_json": json.dumps(dict(style_harmonization), ensure_ascii=False, indent=2),
            "frame_visual_plans_json": json.dumps([dict(plan) for plan in frame_visual_plans], ensure_ascii=False, indent=2),
            "ip_profile_json": json.dumps(dict(ip_profile or {}), ensure_ascii=False, indent=2),
            "compatibility_report_json": json.dumps(dict(compatibility_report or {}), ensure_ascii=False, indent=2),
            "target_language_json": json.dumps(target_language, ensure_ascii=False),
        },
    )


__all__ = [
    "render_article_visual_route_analysis_prompt",
    "render_ip_route_compatibility_prompt",
    "render_style_harmonization_prompt",
    "render_frame_ip_fusion_prompt",
]
