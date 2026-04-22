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
