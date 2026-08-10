from __future__ import annotations

from pixelle_video.models.visual_story_engine import VisualRouteScores


def test_external_final_score_cannot_override_content_score() -> None:
    base = VisualRouteScores(
        content_fit=0.8,
        memorability=0.7,
        channel_consistency=0.6,
        production_reliability=0.9,
        risk=0.2,
        final=0.01,
    )
    poisoned = VisualRouteScores(
        content_fit=base.content_fit,
        memorability=base.memorability,
        channel_consistency=base.channel_consistency,
        production_reliability=base.production_reliability,
        risk=base.risk,
        final=0.99,
    )

    assert base.computed_final() == poisoned.computed_final()
    assert base.to_dict()["final"] == base.computed_final()
    assert poisoned.to_dict()["final"] == poisoned.computed_final()


def test_ip_compatibility_cannot_influence_route_ranking() -> None:
    low_ip = VisualRouteScores(
        content_fit=0.7,
        memorability=0.6,
        ip_compatibility=0.0,
        channel_consistency=0.8,
        production_reliability=0.9,
        risk=0.1,
    )
    high_ip = VisualRouteScores(
        content_fit=low_ip.content_fit,
        memorability=low_ip.memorability,
        ip_compatibility=1.0,
        channel_consistency=low_ip.channel_consistency,
        production_reliability=low_ip.production_reliability,
        risk=low_ip.risk,
    )

    assert low_ip.computed_final() == high_ip.computed_final()


def test_content_only_formula_is_deterministic() -> None:
    scores = VisualRouteScores(
        content_fit=0.8,
        memorability=0.5,
        channel_consistency=0.7,
        production_reliability=0.9,
        risk=0.2,
    )

    expected = round(
        0.8 * 0.38
        + 0.5 * 0.22
        + 0.7 * 0.17
        + 0.9 * 0.23
        - 0.2 * 0.22,
        4,
    )
    assert scores.computed_final() == expected
