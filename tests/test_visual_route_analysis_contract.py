import pytest

from pixelle_video.models.visual_story_engine import VisualRouteCandidate
from pixelle_video.services.visual_route_analysis_contract import (
    parse_route_candidates,
    recognized_payload_keys,
    score_repair_candidate_context,
    validate_score_repairs,
)


def _scores(value: float = 0.5) -> dict[str, float]:
    return {
        "content_fit": value,
        "memorability": value,
        "channel_consistency": value,
        "production_reliability": value,
        "risk": value,
    }


def test_malformed_nested_scores_never_fall_back_to_flattened_fields() -> None:
    result = parse_route_candidates(
        [
            {
                "route_id": "route-a",
                "route_name": "Route A",
                "route_type": "structure_map",
                "visual_premise": "premise",
                "why_it_fits_article": "because",
                "scores": "content_fit",
                **_scores(0.9),
            }
        ]
    )

    assert result.accepted == ()
    assert [index for index, _ in result.repairable] == [0]
    assert result.rejected_count == 0


def test_duplicate_score_repair_indices_are_rejected_independently() -> None:
    payload = {
        "score_repairs": [
            {"candidate_index": 0, "scores": _scores(0.7)},
            {"candidate_index": 0, "scores": _scores(0.8)},
            {"candidate_index": 1, "scores": _scores(0.6)},
            {"candidate_index": 999, "scores": _scores(0.9)},
        ]
    }

    repairs = validate_score_repairs(payload, {0, 1})

    assert set(repairs) == {1}
    assert repairs[1].content_fit == 0.6


def test_model_numeric_strings_are_normalized_at_the_contract_boundary() -> None:
    result = parse_route_candidates(
        [
            {
                "route_id": "route-a",
                "route_name": "Route A",
                "route_type": "structure_map",
                "visual_premise": "premise",
                "why_it_fits_article": "because",
                "scores": {
                    field_name: "0.75"
                    for field_name in _scores()
                },
            }
        ]
    )

    assert len(result.accepted) == 1
    assert result.repairable == ()
    assert result.accepted[0][1].scores.content_fit == 0.75


def test_score_repair_normalizes_safe_flat_aliases_and_string_index() -> None:
    repairs = validate_score_repairs(
        {
            "score_repairs": [
                {
                    "candidate_index": "0",
                    "content_fit_score": "0.81",
                    "visual_memorability_score": "0.72",
                    "channel_fit": "0.73",
                    "production_reliability_score": "0.84",
                    "risk_score": "0.11",
                }
            ]
        },
        {0},
    )

    assert repairs[0].content_fit == 0.81
    assert repairs[0].risk == 0.11


@pytest.mark.parametrize("unsafe_value", ["NaN", "Infinity", "1_0", "score", "2"])
def test_score_normalization_rejects_non_json_or_out_of_range_values(
    unsafe_value: str,
) -> None:
    result = parse_route_candidates(
        [
            {
                "route_id": "route-a",
                "route_name": "Route A",
                "route_type": "structure_map",
                "visual_premise": "premise",
                "why_it_fits_article": "because",
                "scores": {
                    **_scores(),
                    "content_fit": unsafe_value,
                },
            }
        ]
    )

    assert result.accepted == ()
    assert [index for index, _ in result.repairable] == [0]


def test_score_repair_context_is_bounded_before_prompt_rendering() -> None:
    candidate = VisualRouteCandidate(
        route_id="route-a",
        route_name="x" * 500,
        route_type="structure_map",
        visual_premise="y" * 2000,
        why_it_fits_article="z" * 2000,
        frame_storytelling_logic="w" * 2000,
        risk_notes=("r" * 500,) * 10,
    )

    context = score_repair_candidate_context(0, candidate)

    assert len(context["route_name"]) == 240
    assert len(context["visual_premise"]) == 800
    assert len(context["why_it_fits_article"]) == 800
    assert len(context["frame_storytelling_logic"]) == 800
    assert len(context["risk_notes"]) == 1
    assert len(context["risk_notes"][0]) == 240


def test_recognized_payload_keys_never_echo_untrusted_key_names() -> None:
    payload = {
        "article_understanding": {},
        "candidates": [],
        "secret-token-value": "must not enter logs",
    }

    assert recognized_payload_keys(payload) == [
        "article_understanding",
        "candidates",
    ]
