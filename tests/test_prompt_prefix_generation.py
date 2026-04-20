import pytest

from pixelle_video.prompts.prompt_prefix_generation import build_prompt_prefix_generation_prompt
from pixelle_video.utils.prompt_prefix_generation import (
    PromptPrefixGenerationResult,
    build_prompt_prefix_preview_batch,
    sanitize_prompt_prefix_candidates,
)


def test_build_prompt_prefix_generation_prompt_mentions_user_idea_and_allowed_categories():
    prompt = build_prompt_prefix_generation_prompt(
        user_idea="warm healing storybook style",
        language="en_US",
    )

    assert "warm healing storybook style" in prompt
    assert "storybook" in prompt
    assert "childrens_story" in prompt
    assert "JSON" in prompt


def test_sanitize_prompt_prefix_candidates_keeps_allowed_category_ids_and_trims_content():
    result = PromptPrefixGenerationResult.model_validate(
        {
            "items": [
                {
                    "name": "Warm Storybook",
                    "content": "  warm storybook illustration  ",
                    "style_category_id": "storybook",
                    "scene_category_id": "childrens_story",
                    "note": "soft and healing",
                }
            ]
        }
    )

    sanitized = sanitize_prompt_prefix_candidates(result)

    assert sanitized[0]["content"] == "warm storybook illustration"
    assert sanitized[0]["style_category_id"] == "storybook"
    assert sanitized[0]["scene_category_id"] == "childrens_story"


def test_sanitize_prompt_prefix_candidates_drops_invalid_category_ids():
    result = PromptPrefixGenerationResult.model_validate(
        {
            "items": [
                {
                    "name": "Broken",
                    "content": "broken",
                    "style_category_id": "unknown_style",
                    "scene_category_id": "childrens_story",
                    "note": "",
                }
            ]
        }
    )

    assert sanitize_prompt_prefix_candidates(result) == []


def test_sanitize_prompt_prefix_candidates_drops_blank_names():
    result = PromptPrefixGenerationResult.model_validate(
        {
            "items": [
                {
                    "name": "   ",
                    "content": "flat illustration",
                    "style_category_id": "flat_illustration",
                    "scene_category_id": "knowledge_sharing",
                    "note": "usable content but invalid empty title",
                }
            ]
        }
    )

    assert sanitize_prompt_prefix_candidates(result) == []


def test_build_prompt_prefix_preview_batch_limits_selection_count():
    with pytest.raises(ValueError, match="at most 4"):
        build_prompt_prefix_preview_batch(
            items_by_id={key: {"id": key} for key in ["a", "b", "c", "d", "e"]},
            selected_ids=["a", "b", "c", "d", "e"],
        )


def test_build_prompt_prefix_preview_batch_preserves_selected_order():
    preview_batch = build_prompt_prefix_preview_batch(
        items_by_id={
            "b": {"id": "b", "name": "B"},
            "a": {"id": "a", "name": "A"},
        },
        selected_ids=["a", "b"],
    )

    assert [item["id"] for item in preview_batch] == ["a", "b"]
