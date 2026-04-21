import pytest

from pixelle_video.models.style_resolution import StyleSourceSpec
from pixelle_video.utils.style_resolution import (
    RESOLVER_VERSION,
    build_style_resolution_cache_key,
    resolve_style_source,
    resolve_style_spec,
    reset_style_resolution_cache,
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


@pytest.mark.asyncio
async def test_resolve_style_spec_reuses_runtime_cache():
    reset_style_resolution_cache()
    calls = {"count": 0}

    async def fake_llm(prompt, temperature, max_tokens):
        calls["count"] += 1
        return """
        {
          "style_kind": "ip_world",
          "prompt_template": "{prompt}, same playful bird-universe silhouette",
          "negative_prompt": "photo realism, realistic fur",
          "style_profile": {
            "style_kind": "ip_world",
            "subject_policy": "keep_subject_semantics_but_restyle_into_world",
            "shape_language": "rounded geometric cartoon forms",
            "material": "clean game-like cartoon surface",
            "palette": "high saturation reds and yellows",
            "lighting": "bright playful lighting",
            "world_elements": "destructible wooden obstacles and game-like props",
            "consistency_anchor": "all frames belong to the same playful bird universe",
            "negative_rules": "do not revert to realistic anatomy"
          }
        }
        """

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
async def test_resolve_style_spec_rejects_invalid_style_kind():
    async def fake_llm(prompt, temperature, max_tokens):
        return """
        {
          "style_kind": "unknown_kind",
          "prompt_template": "{prompt}",
          "negative_prompt": "",
          "style_profile": {
            "style_kind": "unknown_kind",
            "subject_policy": "keep subject",
            "shape_language": "soft rounded shapes",
            "material": "flat illustration",
            "palette": "warm pastels",
            "lighting": "soft daylight",
            "world_elements": "storybook props",
            "consistency_anchor": "consistent warm storybook world",
            "negative_rules": "avoid photorealism"
          }
        }
        """

    source = StyleSourceSpec(
        origin="request",
        raw_content="warm storybook illustration",
        content_hash="hash-invalid",
        source_identity="request:hash-invalid",
        item_id=None,
    )

    with pytest.raises(ValueError, match="Invalid style_kind"):
        await resolve_style_spec(fake_llm, source)
