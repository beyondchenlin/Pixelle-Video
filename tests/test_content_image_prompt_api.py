import pytest
from pydantic import ValidationError

from api.routers.content import generate_image_prompt
from api.schemas.content import (
    ImagePromptGenerateRequest,
)
from api.schemas.content import (
    StoryboardFrameOverride as ContentStoryboardFrameOverride,
)
from api.schemas.video import StoryboardFrameOverride as VideoStoryboardFrameOverride
from pixelle_video.models.storyboard_plan import StoryboardPlan, StoryboardPlanFrame
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


def _storyboard_plan() -> StoryboardPlan:
    return StoryboardPlan.build(
        mode="sentence",
        count_mode="auto",
        requested_scene_count=None,
        source_text="第一句。第二句。",
        frames=[
            StoryboardPlanFrame(
                index=1,
                source_text="第一句。",
                visual_goal="Show idea one.",
                prompt_intent="Visual metaphor one.",
                source_start=0,
                source_end=4,
            ),
            StoryboardPlanFrame(
                index=2,
                source_text="第二句。",
                visual_goal="Show idea two.",
                prompt_intent="Visual metaphor two.",
                source_start=4,
                source_end=8,
            ),
        ],
    )


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


def test_content_and_video_api_share_storyboard_frame_override_contract():
    assert ContentStoryboardFrameOverride is VideoStoryboardFrameOverride


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


def test_image_prompt_generate_request_accepts_prompt_generation_performance_controls():
    request = ImagePromptGenerateRequest(
        narrations=["scene one"],
        llm_prompt_batch_size=8,
        llm_prompt_batch_concurrent_limit=3,
    )

    assert request.llm_prompt_batch_size == 8
    assert request.llm_prompt_batch_concurrent_limit == 3


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("llm_prompt_batch_size", 0),
        ("llm_prompt_batch_size", 51),
        ("llm_prompt_batch_concurrent_limit", 0),
        ("llm_prompt_batch_concurrent_limit", 11),
    ],
)
def test_image_prompt_generate_request_rejects_invalid_prompt_generation_performance_controls(
    field_name: str,
    value: int,
):
    with pytest.raises(ValidationError):
        ImagePromptGenerateRequest(
            narrations=["scene one"],
            **{field_name: value},
        )


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


def test_image_prompt_generate_request_example_uses_gguf_default_workflow():
    example = ImagePromptGenerateRequest.model_config["json_schema_extra"]["example"]

    assert example["workflow"] == "selfhost/image_z_image_turbo_gguf.json"


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
    plan = _storyboard_plan()

    async def fake_compose(self, **kwargs):
        assert kwargs["prompt_prefix"] == "angry birds world"
        assert kwargs["workflow"] == "selfhost/image_z_image_turbo.json"
        assert kwargs["batch_size"] == 8
        assert kwargs["max_concurrency"] == 3
        assert kwargs["prompt_language"] == "zh_CN"
        assert kwargs["world_preset_id"] == "neutral_knowledge_storyboard"
        assert kwargs["shot_preset_id"] == "balanced_explainer"
        assert kwargs["consistency_strength"] == "strong"
        assert kwargs["content_mode"] == "concept_explainer"
        assert kwargs["role_strategy"] == "auto"
        assert kwargs["role_locking_strength"] == "strong"
        assert kwargs["shot_strategy"] == "strict"
        assert kwargs["storyboard_plan"].plan_id == plan.plan_id
        assert kwargs["frame_overrides"] == [
            {
                "plan_id": plan.plan_id,
                "plan_revision": plan.revision,
                "frame_id": plan.frames[0].frame_id,
                "source_digest": plan.source_digest,
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
        "api.routers.content.ImagePromptComposer.compose",
        fake_compose,
    )

    response = await generate_image_prompt(
        ImagePromptGenerateRequest(
            narrations=plan.source_texts(),
            prompt_prefix="angry birds world",
            workflow="selfhost/image_z_image_turbo.json",
            llm_prompt_batch_size=8,
            llm_prompt_batch_concurrent_limit=3,
            storyboard_prompt_language="zh_CN",
            world_preset_id="neutral_knowledge_storyboard",
            shot_preset_id="balanced_explainer",
            consistency_strength="strong",
            content_mode="concept_explainer",
            role_strategy="auto",
            role_locking_strength="strong",
            shot_strategy="strict",
            storyboard_generation=plan.to_dict(),
            frame_overrides=[
                {
                    "plan_id": plan.plan_id,
                    "plan_revision": plan.revision,
                    "frame_id": plan.frames[0].frame_id,
                    "source_digest": plan.source_digest,
                    "locked_fields": ["shot_type"],
                    "shot_type": "medium_shot",
                }
            ],
        ),
        _FakePixelleVideo(),
    )

    assert response.image_prompts == ["styled prompt"]


def test_image_prompt_generate_request_accepts_storyboard_prompt_language():
    request = ImagePromptGenerateRequest(
        narrations=["scene one"],
        storyboard_prompt_language="en_US",
    )

    assert request.storyboard_prompt_language == "en_US"


def test_image_prompt_generate_request_defaults_storyboard_prompt_language_to_chinese_for_api_compatibility():
    request = ImagePromptGenerateRequest(
        narrations=["scene one"],
    )

    assert request.storyboard_prompt_language == "zh_CN"


def test_image_prompt_generate_request_accepts_storyboard_generation_contract():
    plan = _storyboard_plan()

    request = ImagePromptGenerateRequest(
        narrations=plan.source_texts(),
        storyboard_generation=plan.to_dict(),
        frame_overrides=[
            {
                "plan_id": plan.plan_id,
                "plan_revision": plan.revision,
                "frame_id": plan.frames[0].frame_id,
                "source_digest": plan.source_digest,
                "locked_fields": ["shot_type"],
                "shot_type": "medium_shot",
            }
        ],
    )

    assert request.storyboard_generation.plan_id == plan.plan_id
    assert request.frame_overrides[0].frame_id == plan.frames[0].frame_id


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
        assert "caption_style" not in kwargs["text_rendering"]
        assert "overlay_style" not in kwargs["text_rendering"]
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


@pytest.mark.asyncio
async def test_generate_image_prompt_endpoint_filters_render_style_payloads(monkeypatch):
    async def fake_generate_styled_image_prompt_batch(**kwargs):
        assert "title_style" not in kwargs["text_rendering"]
        assert "caption_style" not in kwargs["text_rendering"]
        assert "overlay_style" not in kwargs["text_rendering"]
        assert kwargs["text_rendering"]["overlay"]["enabled"] is False
        assert kwargs["text_rendering"]["image_text"]["suppress_embedded_text"] is True
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
                "title_style": {
                    "font_size": 96,
                },
                "caption_style": {
                    "font_size": 72,
                    "primary_color": "#FFFF00",
                },
                "overlay_style": {
                    "font_size": 88,
                    "position": "center",
                },
                "overlay": {"enabled": False},
                "image_text": {"suppress_embedded_text": True},
            },
        ),
        _FakePixelleVideo(),
    )

    assert response.image_prompts == ["styled prompt"]
