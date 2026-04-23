from pixelle_video.models.style_resolution import ResolvedStyleSpec
from pixelle_video.utils.prompt_helper import (
    NO_TEXT_NEGATIVE_RULES,
    apply_no_text_policy,
    assemble_negative_prompt,
)


def test_apply_no_text_policy_appends_global_no_text_guidance():
    prompt = apply_no_text_policy("playful bird teacher explaining penicillin")

    assert "playful bird teacher explaining penicillin" in prompt
    assert "no visible text" in prompt
    assert "no Chinese characters" in prompt
    assert "no English letters" in prompt
    assert "instead of written text" in prompt


def test_assemble_negative_prompt_merges_style_negative_prompt_with_no_text_rules():
    resolved_style = ResolvedStyleSpec(
        style_kind="visual_only",
        prompt_template="",
        negative_prompt="photo realism, realistic fur",
        style_profile={},
        content_hash="hash",
        resolver_version="v1",
        source_identity="request:hash",
        raw_content="flat illustration",
    )

    negative_prompt = assemble_negative_prompt(
        resolved_style,
        supports_negative_prompt=True,
        extra_negative_rules=NO_TEXT_NEGATIVE_RULES,
    )

    assert negative_prompt is not None
    assert "photo realism" in negative_prompt
    assert "realistic fur" in negative_prompt
    assert "text" in negative_prompt
    assert "Chinese characters" in negative_prompt

