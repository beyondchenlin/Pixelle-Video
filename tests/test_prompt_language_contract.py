from inspect import signature
from typing import get_type_hints

from pixelle_video.prompt_language import DEFAULT_PROMPT_LANGUAGE, PromptLanguage
from pixelle_video.services.visual_prompt_composer import VisualPromptComposer
from pixelle_video.utils.content_generators import (
    generate_styled_image_prompt_batch,
    generate_video_prompts,
)


def test_prompt_language_helpers_use_canonical_contract():
    cases = [
        generate_styled_image_prompt_batch,
        generate_video_prompts,
        VisualPromptComposer.compose,
    ]

    for callable_obj in cases:
        assert get_type_hints(callable_obj)["prompt_language"] == PromptLanguage
        assert signature(callable_obj).parameters["prompt_language"].default == DEFAULT_PROMPT_LANGUAGE
