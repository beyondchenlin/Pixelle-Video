import pytest
from pydantic import ValidationError

from api.routers.content import generate_image_prompt
from api.schemas.content import ImagePromptGenerateRequest
from pixelle_video.models.style_resolution import StyledImagePromptBatch


class _FakePixelleVideo:
    def __init__(self):
        self.llm = object()
        self.media = object()
        self.config = {
            "comfyui": {
                "image": {
                    "prompt_prefix": "legacy prefix",
                    "prompt_prefix_library": {"active_prefix_id": None, "items": []},
                }
            }
        }


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("content_mode", "bogus"),
        ("role_strategy", "bogus"),
        ("consistency_strength", "bogus"),
        ("role_locking_strength", "bogus"),
        ("shot_strategy", "bogus"),
    ],
)
def test_image_prompt_generate_request_rejects_invalid_storyboard_controls(field_name: str, value: str):
    with pytest.raises(ValidationError):
        ImagePromptGenerateRequest(
            narrations=["scene one"],
            **{field_name: value},
        )


@pytest.mark.parametrize(
    "frame_overrides",
    [
        [{"scene_id": "1"}],
        [
            {
                "scene_id": "1",
                "snapshot_identity": "snapshot:demo",
                "locked_fields": ["shot_type"],
                "shot_type": "medium_shot",
                "unexpected": "value",
            }
        ],
    ],
)
def test_image_prompt_generate_request_rejects_malformed_frame_overrides(frame_overrides: list[dict[str, str]]):
    with pytest.raises(ValidationError):
        ImagePromptGenerateRequest(
            narrations=["scene one"],
            frame_overrides=frame_overrides,
        )


def test_image_prompt_generate_request_accepts_text_rendering_policy():
    request = ImagePromptGenerateRequest(
        narrations=["scene one"],
        text_rendering={
            "overlay": {
                "enabled": True,
                "mode": "programmatic_only",
                "renderer_targets": ["hyperframes"],
            },
            "image_text": {
                "suppress_embedded_text": True,
                "positive_prompt": "no letters in image",
                "negative_prompt": "letters, watermark",
            },
        },
    )

    assert request.text_rendering.overlay.enabled is True
    assert request.text_rendering.image_text.suppress_embedded_text is True
    assert request.text_rendering.image_text.positive_prompt == "no letters in image"


def test_image_prompt_generate_request_rejects_legacy_text_fields():
    with pytest.raises(ValidationError):
        ImagePromptGenerateRequest(
            narrations=["scene one"],
            forbid_embedded_text_in_image=False,
        )

    with pytest.raises(ValidationError):
        ImagePromptGenerateRequest(
            narrations=["scene one"],
            text_layer={"enabled": True},
        )


@pytest.mark.parametrize(
    "text_rendering",
    [
        {"unexpected": {}},
        {"overlay": {"enabled": True, "unexpected": "x"}},
        {"image_text": {"suppress_embedded_text": True, "unexpected": "x"}},
    ],
)
def test_image_prompt_generate_request_rejects_unknown_text_rendering_keys(text_rendering: dict):
    with pytest.raises(ValidationError):
        ImagePromptGenerateRequest(narrations=["scene one"], text_rendering=text_rendering)


@pytest.mark.asyncio
async def test_generate_image_prompt_endpoint_uses_shared_styled_batch(monkeypatch):
    async def fake_generate_styled_image_prompt_batch(**kwargs):
        assert kwargs["prompt_prefix"] == "angry birds world"
        assert kwargs["workflow"] == "selfhost/image_z_image_turbo.json"
        assert kwargs["world_preset_id"] == "neutral_knowledge_storyboard"
        assert kwargs["shot_preset_id"] == "balanced_explainer"
        assert kwargs["consistency_strength"] == "strong"
        assert kwargs["content_mode"] == "concept_explainer"
        assert kwargs["role_strategy"] == "auto"
        assert kwargs["role_locking_strength"] == "strong"
        assert kwargs["shot_strategy"] == "strict"
        assert kwargs["frame_overrides"] == [
            {
                "scene_id": "scene-1",
                "snapshot_identity": "snapshot:scene-1",
                "locked_fields": ["shot_type"],
                "shot_type": "medium_shot",
            }
        ]
        return StyledImagePromptBatch(
            prompts=["styled prompt"],
            negative_prompt="photo realism",
            resolved_style=None,
        )

    monkeypatch.setattr(
        "api.routers.content.generate_styled_image_prompt_batch",
        fake_generate_styled_image_prompt_batch,
    )

    response = await generate_image_prompt(
        ImagePromptGenerateRequest(
            narrations=["scene one"],
            prompt_prefix="angry birds world",
            workflow="selfhost/image_z_image_turbo.json",
            world_preset_id="neutral_knowledge_storyboard",
            shot_preset_id="balanced_explainer",
            consistency_strength="strong",
            content_mode="concept_explainer",
            role_strategy="auto",
            role_locking_strength="strong",
            shot_strategy="strict",
            frame_overrides=[
                {
                    "scene_id": "scene-1",
                    "snapshot_identity": "snapshot:scene-1",
                    "locked_fields": ["shot_type"],
                    "shot_type": "medium_shot",
                }
            ],
        ),
        _FakePixelleVideo(),
    )

    assert response.image_prompts == ["styled prompt"]


@pytest.mark.asyncio
async def test_generate_image_prompt_endpoint_threads_text_rendering(monkeypatch):
    async def fake_generate_styled_image_prompt_batch(**kwargs):
        assert kwargs["text_rendering"]["overlay"] == {
            "enabled": True,
            "mode": "hybrid",
            "renderer_targets": ["hyperframes"],
            "density": "medium",
            "max_items_per_frame": 2,
        }
        image_text = kwargs["text_rendering"]["image_text"]
        assert image_text["suppress_embedded_text"] is True
        assert "no visible text" in image_text["positive_prompt"]
        assert "no watermark" in image_text["positive_prompt"]
        assert image_text["negative_prompt"] == "letters"
        return StyledImagePromptBatch(
            prompts=["styled prompt"],
            negative_prompt=None,
            resolved_style=None,
        )

    monkeypatch.setattr(
        "api.routers.content.generate_styled_image_prompt_batch",
        fake_generate_styled_image_prompt_batch,
    )

    response = await generate_image_prompt(
        ImagePromptGenerateRequest(
            narrations=["scene one"],
            text_rendering={
                "overlay": {
                    "enabled": True,
                    "mode": "hybrid",
                    "renderer_targets": ["hyperframes"],
                },
                "image_text": {
                    "suppress_embedded_text": True,
                    "negative_prompt": "letters",
                },
            },
        ),
        _FakePixelleVideo(),
    )

    assert response.image_prompts == ["styled prompt"]
