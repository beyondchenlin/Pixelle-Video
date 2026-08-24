from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from api.dependencies import get_pixelle_video
from api.routers.content import (
    generate_image_prompt,
    generate_narration,
    generate_world_hint_draft,
)
from api.routers.content import router as content_router
from api.schemas.content import (
    ImagePromptGenerateRequest,
    NarrationGenerateRequest,
    WorldHintDraftGenerateRequest,
)
from api.schemas.content import (
    StoryboardFrameOverride as ContentStoryboardFrameOverride,
)
from api.schemas.video import StoryboardFrameOverride as VideoStoryboardFrameOverride
from pixelle_video.models.storyboard_plan import StoryboardPlan, StoryboardPlanFrame
from pixelle_video.models.style_resolution import StyledImagePromptBatch
from pixelle_video.services.prompt_plan_service import build_prompt_plan_bundle


class _FakePixelleVideo:
    def __init__(self):
        self.llm = object()
        self.media = object()
        self.config = {
            "comfyui": {
                "image": {
                    "prompt_prefix": "retired config value",
                    "prompt_prefix_library": {"active_prefix_id": None, "items": []},
                }
            },
            "storyboard_world_preset_library": {
                "default_world_preset_id": "neutral_knowledge_storyboard",
                "items": [
                    {
                        "preset_id": "neutral_knowledge_storyboard",
                        "display_name": "Neutral Knowledge Storyboard",
                    }
                ],
            },
        }


def _fake_http_request() -> SimpleNamespace:
    return SimpleNamespace(
        headers={"x-task-id": "task-content-api-test"},
        app=SimpleNamespace(
            state=SimpleNamespace(
                trace_repository=object(),
                raw_payload_store=object(),
            )
        ),
    )


def test_world_hint_draft_request_rejects_blank_source_text():
    with pytest.raises(ValidationError):
        WorldHintDraftGenerateRequest(source_text="   ")


@pytest.mark.asyncio
async def test_generate_world_hint_draft_endpoint_uses_content_world_planner(monkeypatch):
    captured = {}

    class FakePlanner:
        async def plan(self, **kwargs):
            captured.update(kwargs)
            from pixelle_video.models.content_world import (
                ContentWorldHintSource,
                ContentWorldProfile,
            )

            return ContentWorldProfile(
                summary="正定古城清晨漫游",
                story_constraints="不能替代真实古建筑",
                ip_integration_guidance="IP 作为陪伴式向导",
                hint_source=ContentWorldHintSource.GENERATED_FROM_SCRIPT,
            )

    monkeypatch.setattr("api.routers.content.ContentWorldPlanner", lambda: FakePlanner())

    response = await generate_world_hint_draft(
        WorldHintDraftGenerateRequest(
            source_text="从长乐门出发，这是正定的南大门。",
            title="正定漫游",
            world_preset_id="neutral_knowledge_storyboard",
            ip_default_world_hint="适合亲切文旅讲解世界。",
            storyboard_prompt_language="zh_CN",
        ),
        _fake_http_request(),
        _FakePixelleVideo(),
    )

    assert captured["ip_world_hint"] == "适合亲切文旅讲解世界。"
    assert "标题：正定漫游" in captured["source_text"]
    assert "正定古城清晨漫游" in response.world_hint_draft
    assert response.generation_world_profile["summary"] == "正定古城清晨漫游"
    assert response.hint_source == "generated_from_script"


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


def test_image_prompt_generate_request_accepts_upstream_llm_trace_refs():
    request = ImagePromptGenerateRequest(
        narrations=["scene one"],
        upstream_llm_trace_refs=[
            {"trace_id": "trace-narration-1", "stage": "api_narration_generation"}
        ],
    )

    assert request.upstream_llm_trace_refs == [
        {"trace_id": "trace-narration-1", "stage": "api_narration_generation"}
    ]


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("prompt_prefix", "angry birds world"),
        ("workflow", "selfhost/image_z_image_turbo_gguf.json"),
    ],
)
def test_image_prompt_generate_request_rejects_raw_api_boundary_fields(field_name: str, value: str):
    with pytest.raises(ValidationError):
        ImagePromptGenerateRequest(
            narrations=["scene one"],
            **{field_name: value},
        )


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("prompt_prefix", "angry birds world"),
        ("workflow", "selfhost/image_z_image_turbo_gguf.json"),
    ],
)
def test_image_prompt_endpoint_rejects_raw_api_boundary_fields(field_name: str, value: str):
    app = FastAPI()
    app.dependency_overrides[get_pixelle_video] = lambda: _FakePixelleVideo()
    app.include_router(content_router)
    client = TestClient(app)

    response = client.post(
        "/content/image-prompt",
        json={
            "narrations": ["scene one"],
            field_name: value,
        },
    )

    assert response.status_code == 422


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


def test_image_prompt_generate_request_example_omits_raw_api_boundary_fields():
    example = ImagePromptGenerateRequest.model_config["json_schema_extra"]["example"]

    assert "prompt_prefix" not in example
    assert "workflow" not in example


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
async def test_generate_narration_endpoint_returns_llm_trace_refs(monkeypatch):
    async def fake_generate_narrations_from_topic(**kwargs):
        kwargs["trace_recorder"].records.append(
            SimpleNamespace(
                trace_id="trace-narration-1",
                context=SimpleNamespace(stage="api_narration_generation"),
                status="success",
            )
        )
        return ["scene one"]

    monkeypatch.setattr(
        "api.routers.content.generate_narrations_from_topic",
        fake_generate_narrations_from_topic,
    )

    response = await generate_narration(
        NarrationGenerateRequest(text="source text", n_scenes=1),
        _fake_http_request(),
        _FakePixelleVideo(),
    )

    assert response.narrations == ["scene one"]
    assert response.llm_trace_refs == [
        {"trace_id": "trace-narration-1", "stage": "api_narration_generation"}
    ]


@pytest.mark.asyncio
async def test_generate_image_prompt_endpoint_uses_shared_styled_batch(monkeypatch):
    plan = _storyboard_plan()

    async def fake_compose(self, **kwargs):
        assert kwargs["prompt_prefix"] is None
        assert kwargs["workflow"] is None
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
        assert kwargs["upstream_llm_trace_refs"] == [
            {"trace_id": "trace-narration-1", "stage": "api_narration_generation"}
        ]
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

    request = ImagePromptGenerateRequest(
        narrations=plan.source_texts(),
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
        upstream_llm_trace_refs=[
            {"trace_id": "trace-narration-1", "stage": "api_narration_generation"}
        ],
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
    object.__setattr__(request, "prompt_prefix", "angry birds world")
    object.__setattr__(request, "workflow", "selfhost/image_z_image_turbo.json")

    response = await generate_image_prompt(request, _fake_http_request(), _FakePixelleVideo())

    assert response.image_prompts == ["styled prompt"]


@pytest.mark.asyncio
async def test_generate_image_prompt_endpoint_returns_prompt_provenance(monkeypatch):
    plan = _storyboard_plan()
    llm_trace_refs = [{"trace_id": "trace-image-1", "stage": "image_prompt_batch"}]
    template_metadata = {
        "prompt_id": "final_visual_prompt",
        "version": "1",
        "stage": "final_visual_prompt_assembly",
        "path": "pixelle_video/prompts/templates/final_visual_prompt.md",
    }
    prompt_plan_bundle = build_prompt_plan_bundle(
        storyboard_plan=plan,
        image_prompts=("styled prompt one", "styled prompt two"),
        planning_snapshot={
            "llm_trace_refs": llm_trace_refs,
            "final_visual_prompt_template": template_metadata,
        },
    )

    async def fake_compose(self, **_kwargs):
        return StyledImagePromptBatch(
            prompts=["styled prompt one", "styled prompt two"],
            negative_prompt="blur",
            resolved_style=None,
            planning_snapshot={
                "llm_trace_refs": llm_trace_refs,
                "final_visual_prompt_template": template_metadata,
            },
            prompt_plan_bundle=prompt_plan_bundle,
        )

    monkeypatch.setattr(
        "api.routers.content.ImagePromptComposer.compose",
        fake_compose,
    )

    response = await generate_image_prompt(
        ImagePromptGenerateRequest(
            narrations=plan.source_texts(),
            storyboard_generation=plan.to_dict(),
        ),
        _fake_http_request(),
        _FakePixelleVideo(),
    )

    assert response.image_prompts == ["styled prompt one", "styled prompt two"]
    assert response.negative_prompt == "blur"
    assert response.llm_trace_refs == llm_trace_refs
    assert response.planning_snapshot["final_visual_prompt_template"]["prompt_id"] == (
        "final_visual_prompt"
    )
    assert response.prompt_plan_bundle["prompt_plans"][0]["final_prompt"] == (
        "styled prompt one"
    )
    assert response.prompt_plan_bundle["prompt_plans"][0]["metadata"][
        "final_visual_prompt_template"
    ]["prompt_id"] == "final_visual_prompt"


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
        _fake_http_request(),
        _FakePixelleVideo(),
    )

    assert response.image_prompts == ["styled prompt"]


@pytest.mark.asyncio
async def test_generate_image_prompt_endpoint_threads_upstream_refs_without_storyboard(
    monkeypatch,
):
    async def fake_generate_styled_image_prompt_batch(**kwargs):
        assert kwargs["upstream_llm_trace_refs"] == [
            {"trace_id": "trace-narration-1", "stage": "api_narration_generation"}
        ]
        return StyledImagePromptBatch(
            prompts=["styled prompt"],
            negative_prompt=None,
            resolved_style=None,
            planning_snapshot={
                "llm_trace_refs": [
                    {
                        "trace_id": "trace-narration-1",
                        "stage": "api_narration_generation",
                    }
                ]
            },
        )

    monkeypatch.setattr(
        "api.routers.content.generate_styled_image_prompt_batch",
        fake_generate_styled_image_prompt_batch,
    )

    response = await generate_image_prompt(
        ImagePromptGenerateRequest(
            narrations=["scene one"],
            upstream_llm_trace_refs=[
                {"trace_id": "trace-narration-1", "stage": "api_narration_generation"}
            ],
        ),
        _fake_http_request(),
        _FakePixelleVideo(),
    )

    assert response.image_prompts == ["styled prompt"]
    assert response.llm_trace_refs == [
        {"trace_id": "trace-narration-1", "stage": "api_narration_generation"}
    ]


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
        _fake_http_request(),
        _FakePixelleVideo(),
    )

    assert response.image_prompts == ["styled prompt"]
