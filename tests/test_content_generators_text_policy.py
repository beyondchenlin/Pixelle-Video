import pytest

from pixelle_video.models.native_prompt import NativePromptHint
from pixelle_video.models.text_overlay import TextRenderingPolicy
from pixelle_video.utils import prompt_helper
from pixelle_video.utils.content_generators import generate_styled_image_prompt_batch
from pixelle_video.utils.prompt_helper import (
    NO_TEXT_POSITIVE_RULE,
    apply_image_text_policy,
    apply_text_rendering_policy,
    select_image_text_negative_prompt,
    select_negative_text_rules,
)


def test_policy_keeps_legacy_no_text_behavior_without_native_hints():
    policy = TextRenderingPolicy()

    prompt = apply_text_rendering_policy(
        "a clean desk",
        policy=policy,
        has_native_hints=False,
    )

    assert NO_TEXT_POSITIVE_RULE in prompt
    assert "text" in select_negative_text_rules(policy=policy, has_native_hints=False)


def test_policy_uses_planned_only_guard_when_native_hints_exist():
    policy = TextRenderingPolicy(
        image_text_mode="native_hint",
        enabled_targets=("native_prompt",),
        allow_native_text_in_image=True,
    )

    prompt = apply_text_rendering_policy(
        'a sign, render the planned text "Pixelle"',
        policy=policy,
        has_native_hints=True,
    )

    assert "render the planned text" in prompt
    assert NO_TEXT_POSITIVE_RULE not in prompt
    assert "no extra captions" in prompt
    assert "text" not in select_negative_text_rules(policy=policy, has_native_hints=True)


def test_visible_text_whitelist_clause_does_not_use_generic_no_text_rule():
    helper = getattr(prompt_helper, "build_visible_text_whitelist_clause", None)
    assert helper is not None

    clause = helper(["从长乐门出发", "长乐门"])

    assert "从长乐门出发" in clause
    assert "长乐门" in clause
    assert "白名单" in clause or "only whitelisted text" in clause.lower()
    assert "no visible text" not in clause


def test_visible_text_whitelist_clause_is_not_used_when_helper_gets_empty_input():
    helper = getattr(prompt_helper, "build_visible_text_whitelist_clause", None)
    assert helper is not None

    assert helper([]) == ""


def test_image_text_policy_routes_custom_positive_and_negative_prompts():
    policy = {
        "suppress_embedded_text": True,
        "positive_prompt": "avoid any generated lettering",
        "negative_prompt": "signage, captions",
    }

    prompt = apply_image_text_policy("a clean desk", policy)

    assert prompt == "a clean desk, avoid any generated lettering"
    assert select_image_text_negative_prompt(policy) == ("signage", "captions")


def test_native_prompt_hint_to_dict_is_lightweight():
    hint = NativePromptHint(
        prompt_fragment='render the planned text "Pixelle"',
        source_candidate_ids=("c1",),
    )

    assert hint.to_dict() == {
        "prompt_fragment": 'render the planned text "Pixelle"',
        "role": "model_native_hint",
        "source_candidate_ids": ["c1"],
    }


@pytest.mark.asyncio
async def test_generate_styled_image_prompt_batch_injects_native_hints_before_text_policy(
    monkeypatch,
):
    async def fake_generate_image_prompts(*args, **kwargs):
        return ["a clean hanging sign"]

    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.generate_image_prompts",
        fake_generate_image_prompts,
    )
    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.resolve_style_source",
        lambda image_config, prompt_prefix_override=None: None,
    )
    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.get_media_workflow_capabilities",
        lambda *args, **kwargs: type("Caps", (), {"supports_negative_prompt": True})(),
    )
    result = await generate_styled_image_prompt_batch(
        llm_service=object(),
        narrations=["scene one"],
        image_config={},
        media_service=object(),
        workflow="selfhost/image_z_image_turbo.json",
        native_prompt_hints_by_frame={
            0: [
                NativePromptHint(
                    prompt_fragment='render the planned text "Pixelle"',
                    source_candidate_ids=("candidate-1",),
                )
            ]
        },
        text_rendering={
            "overlay": {
                "enabled": True,
                "mode": "native_hint",
                "renderer_targets": ["native_prompt"],
            }
        },
    )

    policy = TextRenderingPolicy(
        image_text_mode="native_hint",
        enabled_targets=("native_prompt",),
        allow_native_text_in_image=True,
    )
    assert result.prompts == [
        'a clean hanging sign, render the planned text "Pixelle", '
        "only render the explicitly requested planned text, no extra captions, "
        "no extra subtitles, no watermark, no logo text, no random letters"
    ]
    assert result.negative_prompt is not None
    assert "random letters" in result.negative_prompt
    assert "Chinese characters" not in result.negative_prompt
    assert result.planning_snapshot == {
        "text_rendering_policy": policy.to_dict(),
        "native_prompt_hint_count": 1,
        "frames_with_native_hints": [0],
        "native_prompt_source_candidate_ids": ["candidate-1"],
    }


@pytest.mark.asyncio
async def test_generate_styled_image_prompt_batch_does_not_conflict_native_text_with_image_text_suppression(
    monkeypatch,
):
    async def fake_generate_image_prompts(*args, **kwargs):
        return ["a clean hanging sign"]

    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.generate_image_prompts",
        fake_generate_image_prompts,
    )
    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.resolve_style_source",
        lambda image_config, prompt_prefix_override=None: None,
    )
    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.get_media_workflow_capabilities",
        lambda *args, **kwargs: type("Caps", (), {"supports_negative_prompt": True})(),
    )

    result = await generate_styled_image_prompt_batch(
        llm_service=object(),
        narrations=["scene one"],
        image_config={},
        media_service=object(),
        workflow="selfhost/image_z_image_turbo.json",
        native_prompt_hints_by_frame={
            0: [
                NativePromptHint(
                    prompt_fragment='render the planned text "Pixelle"',
                    source_candidate_ids=("candidate-1",),
                )
            ]
        },
        text_rendering={
            "overlay": {
                "enabled": True,
                "mode": "native_hint",
                "renderer_targets": ["native_prompt"],
            },
            "image_text": {
                "suppress_embedded_text": True,
                "negative_prompt": "forbid all typography",
            },
        },
    )

    assert 'render the planned text "Pixelle"' in result.prompts[0]
    assert NO_TEXT_POSITIVE_RULE not in result.prompts[0]
    assert result.negative_prompt is not None
    assert "unplanned text" in result.negative_prompt
    assert "random letters" in result.negative_prompt
    assert "forbid all typography" not in result.negative_prompt


@pytest.mark.asyncio
async def test_generate_styled_image_prompt_batch_defaults_to_no_image_text_suppression(
    monkeypatch,
):
    async def fake_generate_image_prompts(*args, **kwargs):
        return ["a clean desk"]

    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.generate_image_prompts",
        fake_generate_image_prompts,
    )
    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.resolve_style_source",
        lambda image_config, prompt_prefix_override=None: None,
    )
    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.get_media_workflow_capabilities",
        lambda *args, **kwargs: type("Caps", (), {"supports_negative_prompt": True})(),
    )

    result = await generate_styled_image_prompt_batch(
        llm_service=object(),
        narrations=["scene one"],
        image_config={},
        media_service=object(),
        workflow="selfhost/image_z_image_turbo.json",
    )

    assert result.prompts == ["a clean desk"]
    assert NO_TEXT_POSITIVE_RULE not in result.prompts[0]
    assert result.negative_prompt is None


@pytest.mark.asyncio
async def test_generate_styled_image_prompt_batch_uses_image_text_policy_prompts(
    monkeypatch,
):
    async def fake_generate_image_prompts(*args, **kwargs):
        return ["a clean desk"]

    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.generate_image_prompts",
        fake_generate_image_prompts,
    )
    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.resolve_style_source",
        lambda image_config, prompt_prefix_override=None: None,
    )
    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.get_media_workflow_capabilities",
        lambda *args, **kwargs: type("Caps", (), {"supports_negative_prompt": True})(),
    )

    result = await generate_styled_image_prompt_batch(
        llm_service=object(),
        narrations=["scene one"],
        image_config={},
        media_service=object(),
        workflow="selfhost/image_z_image_turbo.json",
        text_rendering={
            "image_text": {
                "suppress_embedded_text": True,
                "positive_prompt": "avoid generated lettering",
                "negative_prompt": "signage, captions",
            }
        },
    )

    assert result.prompts == ["a clean desk, avoid generated lettering"]
    assert result.negative_prompt == "signage, captions"
