import pytest

from pixelle_video.services.tts_segmentation import (
    BoundaryType,
    build_external_tts_segmentation_plan,
)
from pixelle_video.tts_split_strategy import (
    DEFAULT_TTS_SPLIT_MODE,
    validate_tts_split_mode,
)


def test_default_tts_split_mode_is_internal_only():
    assert DEFAULT_TTS_SPLIT_MODE == "internal_only"
    assert validate_tts_split_mode("internal_only") == "internal_only"


def test_tts_split_mode_rejects_unknown_value():
    with pytest.raises(ValueError, match="tts_split_mode"):
        validate_tts_split_mode("legacy_phrase_regroup")


def test_tts_split_mode_does_not_expose_unimplemented_llm_mode():
    with pytest.raises(ValueError, match="tts_split_mode"):
        validate_tts_split_mode("llm_boundary_assisted")


def test_external_splitter_prefers_sentence_boundary_before_budget():
    text = (
        "清晨六点，城市还没有完全醒来，路灯在薄雾里发着淡黄色的光。"
        "她提着一袋刚买的面包，沿着河边慢慢往前走，鞋跟敲在石板路上。"
    )

    plan = build_external_tts_segmentation_plan(
        text,
        max_chars_per_segment=45,
        boundary_search_radius=20,
    )

    assert "".join(segment.text for segment in plan.segments) == text
    assert [segment.boundary_type for segment in plan.segments] == [
        BoundaryType.SENTENCE,
        BoundaryType.SENTENCE,
    ]
    assert [segment.is_continuation for segment in plan.segments] == [False, False]


def test_external_splitter_uses_clause_boundary_without_adding_terminal_punctuation():
    text = "她停下来，把围巾重新系紧，然后抬头看了一眼泛白的天空，像是在等什么"

    plan = build_external_tts_segmentation_plan(
        text,
        max_chars_per_segment=24,
        boundary_search_radius=12,
    )

    assert "".join(segment.text for segment in plan.segments) == text
    assert any(segment.boundary_type == BoundaryType.CLAUSE for segment in plan.segments)
    assert all("。" not in segment.text for segment in plan.segments)


def test_external_splitter_hard_limits_when_no_punctuation_exists():
    text = "abcdefghijklmnop"

    plan = build_external_tts_segmentation_plan(
        text,
        max_chars_per_segment=5,
        boundary_search_radius=2,
    )

    assert [segment.text for segment in plan.segments] == ["abcde", "fghij", "klmno", "p"]
    assert [segment.boundary_type for segment in plan.segments[:-1]] == [
        BoundaryType.HARD_LIMIT,
        BoundaryType.HARD_LIMIT,
        BoundaryType.HARD_LIMIT,
    ]


def test_external_splitter_error_policy_rejects_hard_limit_overflow():
    with pytest.raises(ValueError, match="hard limit"):
        build_external_tts_segmentation_plan(
            "abcdefghijklmnop",
            max_chars_per_segment=5,
            boundary_search_radius=2,
            overflow_policy="error",
        )
