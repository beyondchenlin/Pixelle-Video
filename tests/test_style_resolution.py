import json

import pytest
from pydantic import ValidationError

import pixelle_video.utils.style_resolution as style_resolution_module
from pixelle_video.models.style_resolution import (
    StyleResolutionProfileResponse,
    StyleResolutionResponse,
    StyleSourceSpec,
)
from pixelle_video.prompts.style_resolution import build_style_resolution_prompt
from pixelle_video.utils.style_resolution import (
    RESOLVER_VERSION,
    build_style_resolution_cache_key,
    reset_style_resolution_cache,
    resolve_style_source,
    resolve_style_spec,
)


def test_resolve_style_source_prefers_request_override():
    image_config = {
        "prompt_prefix": "legacy prefix",
        "prompt_prefix_library": {
            "active_prefix_id": "warm-story",
            "items": [
                {
                    "id": "warm-story",
                    "content": "warm storybook illustration",
                }
            ],
        },
    }

    source = resolve_style_source(image_config, prompt_prefix_override="  angry birds world  ")

    assert source.origin == "request"
    assert source.raw_content == "angry birds world"
    assert source.item_id is None
    assert source.source_identity.startswith("request:")


def test_build_style_resolution_cache_key_distinguishes_library_and_request():
    library_source = StyleSourceSpec(
        origin="library",
        raw_content="warm storybook illustration",
        content_hash="hash-lib",
        source_identity="library:warm-story",
        item_id="warm-story",
    )
    request_source = StyleSourceSpec(
        origin="request",
        raw_content="warm storybook illustration",
        content_hash="hash-req",
        source_identity="request:hash-req",
        item_id=None,
    )

    assert build_style_resolution_cache_key(library_source) == (
        f"library:warm-story:hash-lib:{RESOLVER_VERSION}"
    )
    assert build_style_resolution_cache_key(request_source) == (
        f"request:hash-req:{RESOLVER_VERSION}"
    )


def test_build_style_resolution_prompt_embeds_response_schema():
    prompt = json.loads(build_style_resolution_prompt("  warm storybook illustration  "))

    assert prompt["task"] == "resolve_style_prefix"
    assert prompt["raw_prefix"] == "warm storybook illustration"
    assert prompt["required_output"] == StyleResolutionResponse.model_json_schema()
    assert any(
        "Validate the final payload against required_output before returning it." in instruction
        for instruction in prompt["instructions"]
    )


def test_style_resolution_response_rejects_mismatched_nested_style_kind():
    with pytest.raises(ValidationError, match="style_profile.style_kind must match top-level style_kind"):
        StyleResolutionResponse(
            style_kind="ip_world",
            prompt_template="{prompt}, same playful bird-universe silhouette",
            negative_prompt="photo realism, realistic fur",
            style_profile=StyleResolutionProfileResponse(
                style_kind="visual_only",
                subject_policy="keep subject semantics",
                shape_language="rounded geometric cartoon forms",
                material="clean game-like cartoon surface",
                palette="high saturation reds and yellows",
                lighting="bright playful lighting",
                world_elements="destructible wooden obstacles and game-like props",
                consistency_anchor="all frames belong to the same playful bird universe",
                negative_rules="do not revert to realistic anatomy",
            ),
        )


def test_style_resolution_response_rejects_invalid_prompt_template():
    with pytest.raises(ValidationError, match="prompt_template must contain \\{prompt\\} exactly once"):
        StyleResolutionResponse(
            style_kind="visual_only",
            prompt_template="storybook frame without placeholder",
            negative_prompt="",
            style_profile=StyleResolutionProfileResponse(
                style_kind="visual_only",
                subject_policy="preserve subject semantics",
                shape_language="soft rounded shapes",
                material="flat illustration",
                palette="warm pastels",
                lighting="soft daylight",
                world_elements="storybook props",
                consistency_anchor="consistent warm storybook world",
                negative_rules="avoid photorealism",
            ),
        )


@pytest.mark.asyncio
async def test_resolve_style_spec_reuses_runtime_cache_with_structured_output():
    reset_style_resolution_cache()
    calls = {"count": 0}

    async def fake_llm(*, prompt, **kwargs):
        calls["count"] += 1
        assert kwargs["response_type"] is StyleResolutionResponse
        return StyleResolutionResponse(
            style_kind="ip_world",
            prompt_template="{prompt}, same playful bird-universe silhouette",
            negative_prompt="photo realism, realistic fur",
            style_profile=StyleResolutionProfileResponse(
                style_kind="ip_world",
                subject_policy="keep_subject_semantics_but_restyle_into_world",
                shape_language="rounded geometric cartoon forms",
                material="clean game-like cartoon surface",
                palette="high saturation reds and yellows",
                lighting="bright playful lighting",
                world_elements="destructible wooden obstacles and game-like props",
                consistency_anchor="all frames belong to the same playful bird universe",
                negative_rules="do not revert to realistic anatomy",
            ),
        )

    source = StyleSourceSpec(
        origin="request",
        raw_content="angry birds world",
        content_hash="hash-123",
        source_identity="request:hash-123",
        item_id=None,
    )

    first = await resolve_style_spec(fake_llm, source)
    second = await resolve_style_spec(fake_llm, source)

    assert first.style_kind == "ip_world"
    assert second == first
    assert calls["count"] == 1


@pytest.mark.asyncio
async def test_resolve_style_spec_uses_structured_output_contract():
    captured_response_type: list[object] = []
    captured_prompt: list[str] = []

    async def fake_llm(*, prompt, **kwargs):
        captured_prompt.append(prompt)
        captured_response_type.append(kwargs.get("response_type"))
        return StyleResolutionResponse(
            style_kind="visual_only",
            prompt_template="{prompt}",
            negative_prompt="",
            style_profile=StyleResolutionProfileResponse(
                style_kind="visual_only",
                subject_policy="preserve subject semantics",
                shape_language="soft rounded shapes",
                material="flat illustration",
                palette="warm pastels",
                lighting="soft daylight",
                world_elements="storybook props",
                consistency_anchor="consistent warm storybook world",
                negative_rules="avoid photorealism",
            ),
        )

    source = StyleSourceSpec(
        origin="request",
        raw_content="warm storybook illustration",
        content_hash="hash-structured",
        source_identity="request:hash-structured",
        item_id=None,
    )

    resolved = await resolve_style_spec(fake_llm, source)

    assert captured_response_type == [StyleResolutionResponse]
    assert '"task": "resolve_style_prefix"' in captured_prompt[0]
    assert resolved.prompt_template == "{prompt}"


@pytest.mark.asyncio
async def test_resolve_style_spec_evicts_oldest_cache_entries(monkeypatch):
    reset_style_resolution_cache()
    monkeypatch.setattr(style_resolution_module, "_STYLE_RESOLUTION_CACHE_MAX_SIZE", 1)
    calls: list[str] = []

    async def fake_llm(*, prompt, **kwargs):
        source_identity = prompt.split('"raw_prefix": "')[1].split('"', 1)[0]
        calls.append(source_identity)
        return StyleResolutionResponse(
            style_kind="visual_only",
            prompt_template="{prompt}",
            negative_prompt="",
            style_profile=StyleResolutionProfileResponse(
                style_kind="visual_only",
                subject_policy="preserve subject semantics",
                shape_language="soft rounded shapes",
                material="flat illustration",
                palette="warm pastels",
                lighting="soft daylight",
                world_elements="storybook props",
                consistency_anchor="consistent warm storybook world",
                negative_rules="avoid photorealism",
            ),
        )

    first_source = StyleSourceSpec(
        origin="request",
        raw_content="first style",
        content_hash="hash-first",
        source_identity="request:hash-first",
        item_id=None,
    )
    second_source = StyleSourceSpec(
        origin="request",
        raw_content="second style",
        content_hash="hash-second",
        source_identity="request:hash-second",
        item_id=None,
    )

    await resolve_style_spec(fake_llm, first_source)
    await resolve_style_spec(fake_llm, second_source)
    await resolve_style_spec(fake_llm, first_source)

    assert calls == ["first style", "second style", "first style"]
