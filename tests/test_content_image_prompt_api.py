import pytest

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


@pytest.mark.asyncio
async def test_generate_image_prompt_endpoint_uses_shared_styled_batch(monkeypatch):
    async def fake_generate_styled_image_prompt_batch(**kwargs):
        assert kwargs["prompt_prefix"] == "angry birds world"
        assert kwargs["workflow"] == "selfhost/image_z_image_turbo.json"
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
        ),
        _FakePixelleVideo(),
    )

    assert response.image_prompts == ["styled prompt"]
