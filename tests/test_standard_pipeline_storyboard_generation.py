import pytest

from pixelle_video.models.caption_speech_plan import CaptionSpeechPlan
from pixelle_video.models.prompt_plan import PromptPlanBundle
from pixelle_video.models.storyboard_plan import StoryboardPlan, StoryboardPlanFrame
from pixelle_video.models.style_resolution import StyledImagePromptBatch
from pixelle_video.pipelines.linear import PipelineContext
from pixelle_video.pipelines.standard import StandardPipeline
from pixelle_video.utils.template_util import get_template_orientation


class _DummyCore:
    def __init__(self, config=None):
        self.config = config or {"comfyui": {"image": {}, "video": {}}}
        self.llm = object()
        self.tts = None
        self.media = object()
        self.video = None


class _RecordingAssetBibleRepository:
    def __init__(self):
        self.load_calls = []
        self.list_scene_cast_calls = []

    async def load_asset_bible(self, workspace_id, asset_bible_id):
        self.load_calls.append((workspace_id, asset_bible_id))
        if asset_bible_id != "bible_demo":
            return None
        return {
            "asset_bible_id": "bible_demo",
            "workspace_id": workspace_id,
            "project_id": "project_1",
            "ip_profiles": [
                {
                    "ip_profile_id": "ip_main",
                    "workspace_id": workspace_id,
                    "project_id": "project_1",
                    "name": "正定向导兔",
                    "identity_lock": ["白色卡通兔子"],
                    "identity_anchors": ["蓝色领带"],
                }
            ],
        }

    async def list_scene_casts(self, workspace_id, project_id, asset_bible_id):
        self.list_scene_cast_calls.append((workspace_id, project_id, asset_bible_id))
        return [
            {
                "scene_cast_id": "cast_1",
                "workspace_id": workspace_id,
                "project_id": project_id,
                "storyboard_plan_id": "other_plan",
                "frame_id": "ignored_frame",
                "asset_bible_id": asset_bible_id,
                "metadata": {"ip_presence_type": "absent"},
            },
            {
                "scene_cast_id": "cast_2",
                "workspace_id": workspace_id,
                "project_id": project_id,
                "storyboard_plan_id": self.current_storyboard_plan_id,
                "frame_id": self.current_frame_id,
                "asset_bible_id": asset_bible_id,
                "metadata": {"ip_presence_type": "scene_integrated"},
            },
        ]


class _EmptyIPAssetBibleRepository(_RecordingAssetBibleRepository):
    async def load_asset_bible(self, workspace_id, asset_bible_id):
        payload = await super().load_asset_bible(workspace_id, asset_bible_id)
        if payload is None:
            return None
        payload["ip_profiles"][0]["identity_lock"] = []
        payload["ip_profiles"][0]["identity_anchors"] = []
        return payload


def _plan(source_text="第一句。第二句。", mode="smart"):
    return StoryboardPlan.build(
        mode=mode,
        count_mode="auto",
        requested_scene_count=None,
        source_text=source_text,
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


@pytest.mark.asyncio
async def test_generate_content_fixed_defaults_to_smart_storyboard(monkeypatch):
    captured = {}
    plan = _plan()

    async def fake_storyboard_generate(self, **kwargs):
        captured.update(kwargs)
        return plan

    monkeypatch.setattr(
        "pixelle_video.pipelines.standard.StoryboardGenerationService.generate",
        fake_storyboard_generate,
    )

    ctx = PipelineContext(input_text="第一句。第二句。", params={"mode": "fixed"})
    await StandardPipeline(_DummyCore()).generate_content(ctx)

    assert ctx.source_text == "第一句。第二句。"
    assert ctx.storyboard_plan is plan
    assert isinstance(ctx.caption_speech_plan, CaptionSpeechPlan)
    assert [unit.speech_text for unit in ctx.caption_speech_plan.units] == [
        "第一句。",
        "第二句。",
    ]
    assert captured["source_text"] == "第一句。第二句。"
    assert captured["storyboard_mode"] == "smart"
    assert captured["storyboard_count_mode"] == "auto"
    assert captured["storyboard_scene_count"] is None


@pytest.mark.asyncio
async def test_generate_content_fixed_punctuation_uses_storyboard_generation_service():
    ctx = PipelineContext(
        input_text="第一段，继续；结束。",
        params={"mode": "fixed", "storyboard_mode": "punctuation"},
    )

    await StandardPipeline(_DummyCore()).generate_content(ctx)

    assert ctx.source_text == "第一段，继续；结束。"
    assert ctx.storyboard_plan.mode.value == "punctuation"
    assert [unit.speech_text for unit in ctx.caption_speech_plan.units] == [
        "第一段，",
        "继续；",
        "结束。",
    ]


@pytest.mark.asyncio
async def test_generate_content_deterministic_modes_default_to_request_level_max_scene_count():
    ctx = PipelineContext(
        input_text="first, second.",
        params={"mode": "fixed", "storyboard_mode": "punctuation"},
    )
    core = _DummyCore(
        {
            "storyboard": {"min_scene_count": 1, "max_scene_count": 1},
            "comfyui": {"image": {}, "video": {}},
        }
    )

    await StandardPipeline(core).generate_content(ctx)

    assert ctx.storyboard_plan.mode.value == "punctuation"
    assert [frame.source_text for frame in ctx.storyboard_plan.frames] == [
        "first,",
        "second.",
    ]


@pytest.mark.asyncio
async def test_generate_content_respects_explicit_deterministic_max_scene_count():
    ctx = PipelineContext(
        input_text="first, second.",
        params={
            "mode": "fixed",
            "storyboard_mode": "punctuation",
            "storyboard_max_scene_count": 1,
        },
    )

    with pytest.raises(ValueError, match="too many storyboard frames"):
        await StandardPipeline(_DummyCore()).generate_content(ctx)


@pytest.mark.asyncio
async def test_generate_content_fixed_sentence_uses_storyboard_generation_service():
    ctx = PipelineContext(
        input_text="第一句。第二句！",
        params={"mode": "fixed", "storyboard_mode": "sentence"},
    )

    await StandardPipeline(_DummyCore()).generate_content(ctx)

    assert ctx.storyboard_plan.mode.value == "sentence"
    assert [unit.speech_text for unit in ctx.caption_speech_plan.units] == [
        "第一句。",
        "第二句！",
    ]


@pytest.mark.asyncio
async def test_generate_content_generate_mode_uses_complete_source_text(monkeypatch):
    captured = {}
    plan = _plan(source_text="第一句。第二句。")

    async def fake_script_generate(self, **kwargs):
        captured["script"] = kwargs
        return "第一句。第二句。"

    async def fake_storyboard_generate(self, **kwargs):
        captured["storyboard"] = kwargs
        return plan

    monkeypatch.setattr(
        "pixelle_video.pipelines.standard.ScriptGenerationService.generate",
        fake_script_generate,
    )
    monkeypatch.setattr(
        "pixelle_video.pipelines.standard.StoryboardGenerationService.generate",
        fake_storyboard_generate,
    )

    ctx = PipelineContext(
        input_text="自律主题",
        params={"mode": "generate", "script_length_mode": "custom", "script_target_words": 180},
    )
    await StandardPipeline(_DummyCore()).generate_content(ctx)

    assert ctx.source_text == "第一句。第二句。"
    assert ctx.storyboard_plan is plan
    assert [unit.speech_text for unit in ctx.caption_speech_plan.units] == [
        "第一句。",
        "第二句。",
    ]
    assert captured["script"]["topic"] == "自律主题"
    assert captured["script"]["script_length_mode"] == "custom"
    assert captured["script"]["script_target_words"] == 180
    assert captured["storyboard"]["source_text"] == "第一句。第二句。"


@pytest.mark.asyncio
async def test_plan_visuals_uses_image_prompt_composer(monkeypatch):
    captured = {}

    async def fake_compose(self, **kwargs):
        captured.update(kwargs)
        return StyledImagePromptBatch(
            prompts=["prompt one", "prompt two"],
            negative_prompt="bad anatomy",
            resolved_style=None,
            planning_snapshot={"storyboard_generation": kwargs["storyboard_plan"].to_dict()},
        )

    monkeypatch.setattr(
        "pixelle_video.pipelines.standard.ImagePromptComposer.compose",
        fake_compose,
    )

    ctx = PipelineContext(
        input_text="第一句。第二句。",
        params={"frame_template": "1080x1920/image_default.html"},
    )
    ctx.task_id = "task-1"
    ctx.storyboard_plan = _plan()

    await StandardPipeline(_DummyCore()).plan_visuals(ctx)

    assert captured["storyboard_plan"] is ctx.storyboard_plan
    assert ctx.image_prompts == ["prompt one", "prompt two"]
    assert ctx.media_negative_prompt == "bad anatomy"
    assert ctx.planning_snapshot["storyboard_generation"]["resolved_scene_count"] == 2


@pytest.mark.asyncio
async def test_plan_visuals_passes_ip_controls_to_image_prompt_composer(monkeypatch):
    captured = {}

    async def fake_compose(self, **kwargs):
        captured.update(kwargs)
        return StyledImagePromptBatch(
            prompts=["prompt one", "prompt two"],
            negative_prompt=None,
            resolved_style=None,
            planning_snapshot={"storyboard_generation": kwargs["storyboard_plan"].to_dict()},
        )

    monkeypatch.setattr(
        "pixelle_video.pipelines.standard.ImagePromptComposer.compose",
        fake_compose,
    )

    plan = _plan()
    repository = _RecordingAssetBibleRepository()
    repository.current_storyboard_plan_id = plan.plan_id
    repository.current_frame_id = plan.frames[0].frame_id
    core = _DummyCore()
    core.asset_bible_repository = repository
    ctx = PipelineContext(
        input_text="第一句。第二句。",
        params={
            "frame_template": "1080x1920/image_default.html",
            "workspace_id": "workspace_1",
            "project_id": "project_1",
            "ip_enabled": True,
            "ip_asset_bible_id": "bible_demo",
            "ip_profile_id": "ip_main",
        },
    )
    ctx.task_id = "task-ip-controls"
    ctx.storyboard_plan = plan

    await StandardPipeline(core).plan_visuals(ctx)

    assert repository.load_calls == [("workspace_1", "bible_demo")]
    assert repository.list_scene_cast_calls == [("workspace_1", "project_1", "bible_demo")]
    assert captured["ip_enabled"] is True
    assert captured["ip_profile"].ip_profile_id == "ip_main"
    scene_casts_by_frame = captured["scene_casts_by_frame"]
    assert list(scene_casts_by_frame) == [plan.frames[0].frame_id]
    assert scene_casts_by_frame[plan.frames[0].frame_id]["metadata"]["ip_presence_type"] == "scene_integrated"


@pytest.mark.asyncio
async def test_plan_visuals_rejects_enabled_ip_without_identity_anchors(monkeypatch):
    async def fake_compose(self, **_kwargs):
        raise AssertionError("IP readiness must be checked before prompt compose")

    monkeypatch.setattr(
        "pixelle_video.pipelines.standard.ImagePromptComposer.compose",
        fake_compose,
    )

    plan = _plan()
    repository = _EmptyIPAssetBibleRepository()
    repository.current_storyboard_plan_id = plan.plan_id
    repository.current_frame_id = plan.frames[0].frame_id
    core = _DummyCore()
    core.asset_bible_repository = repository
    ctx = PipelineContext(
        input_text="第一句。第二句。",
        params={
            "frame_template": "1080x1920/image_default.html",
            "workspace_id": "workspace_1",
            "project_id": "project_1",
            "ip_enabled": True,
            "ip_asset_bible_id": "bible_demo",
            "ip_profile_id": "ip_main",
        },
    )
    ctx.task_id = "task-ip-empty-anchors"
    ctx.storyboard_plan = plan

    with pytest.raises(ValueError, match="身份锚点|identity anchors"):
        await StandardPipeline(core).plan_visuals(ctx)


@pytest.mark.asyncio
async def test_plan_visuals_rejects_enabled_ip_without_asset_repository(monkeypatch):
    async def fake_compose(self, **_kwargs):
        raise AssertionError("IP resource loading must happen before prompt compose")

    monkeypatch.setattr(
        "pixelle_video.pipelines.standard.ImagePromptComposer.compose",
        fake_compose,
    )

    ctx = PipelineContext(
        input_text="第一句。第二句。",
        params={
            "frame_template": "1080x1920/image_default.html",
            "ip_enabled": True,
            "ip_asset_bible_id": "bible_demo",
            "ip_profile_id": "ip_main",
        },
    )
    ctx.task_id = "task-ip-missing-repository"
    ctx.storyboard_plan = _plan()

    with pytest.raises(ValueError, match="asset_bible_repository"):
        await StandardPipeline(_DummyCore()).plan_visuals(ctx)


@pytest.mark.asyncio
async def test_plan_visuals_persists_prompt_plan_bundle_to_repository(monkeypatch):
    class RecordingPromptPlanRepository:
        def __init__(self):
            self.saved_bundles = []

        async def save_prompt_plan_bundle(self, workspace_id, bundle):
            self.saved_bundles.append((workspace_id, dict(bundle)))
            return dict(bundle)

        async def load_prompt_plans_by_storyboard(self, workspace_id, storyboard_id):
            return []

        async def mark_prompt_plan_stale(self, workspace_id, prompt_plan_id, reason=None):
            return {"prompt_plan_id": prompt_plan_id}

    async def fake_compose(self, **kwargs):
        plan = kwargs["storyboard_plan"]
        return StyledImagePromptBatch(
            prompts=["prompt one", "prompt two"],
            negative_prompt=None,
            resolved_style=None,
            planning_snapshot={
                "storyboard_generation": plan.to_dict(),
                "prompt_plan_bundle_ref": {
                    "storyboard_plan_id": plan.plan_id,
                    "prompt_plan_count": 2,
                    "image_prompt_draft_count": 2,
                },
            },
            prompt_plan_bundle=PromptPlanBundle.from_dict(
                {
                    "storyboard_plan_id": plan.plan_id,
                    "image_prompt_drafts": [
                        {
                            "image_prompt_draft_id": "draft_frame_1",
                            "storyboard_plan_id": plan.plan_id,
                            "frame_id": plan.frames[0].frame_id,
                            "prompt_text": "prompt one",
                            "source_trace_id": None,
                            "metadata": {"frame_index": 1},
                        },
                        {
                            "image_prompt_draft_id": "draft_frame_2",
                            "storyboard_plan_id": plan.plan_id,
                            "frame_id": plan.frames[1].frame_id,
                            "prompt_text": "prompt two",
                            "source_trace_id": None,
                            "metadata": {"frame_index": 2},
                        },
                    ],
                    "prompt_plans": [
                        {
                            "prompt_plan_id": "prompt_plan_frame_1",
                            "storyboard_plan_id": plan.plan_id,
                            "frame_id": plan.frames[0].frame_id,
                            "image_prompt_draft_id": "draft_frame_1",
                            "prompt_sections": {"generated_prompt": "prompt one"},
                            "final_prompt": "prompt one",
                            "source_trace_id": None,
                            "character_ids": [],
                            "scene_id": None,
                            "prop_ids": [],
                            "style_id": None,
                            "metadata": {"frame_index": 1},
                        },
                        {
                            "prompt_plan_id": "prompt_plan_frame_2",
                            "storyboard_plan_id": plan.plan_id,
                            "frame_id": plan.frames[1].frame_id,
                            "image_prompt_draft_id": "draft_frame_2",
                            "prompt_sections": {"generated_prompt": "prompt two"},
                            "final_prompt": "prompt two",
                            "source_trace_id": None,
                            "character_ids": [],
                            "scene_id": None,
                            "prop_ids": [],
                            "style_id": None,
                            "metadata": {"frame_index": 2},
                        },
                    ],
                    "source_trace_id": None,
                    "metadata": {},
                }
            ),
        )

    monkeypatch.setattr(
        "pixelle_video.pipelines.standard.ImagePromptComposer.compose",
        fake_compose,
    )

    prompt_repository = RecordingPromptPlanRepository()
    core = _DummyCore()
    core.prompt_plan_repository = prompt_repository
    ctx = PipelineContext(
        input_text="first. second.",
        params={
            "frame_template": "1080x1920/image_default.html",
            "workspace_id": "workspace_demo",
        },
    )
    ctx.task_id = "task-persist-prompt-plan"
    ctx.storyboard_plan = _plan()

    await StandardPipeline(core).plan_visuals(ctx)

    assert len(prompt_repository.saved_bundles) == 1
    workspace_id, saved_bundle = prompt_repository.saved_bundles[0]
    assert workspace_id == "workspace_demo"
    assert saved_bundle == ctx.prompt_plan_bundle.to_dict()
    assert saved_bundle["prompt_plans"][0]["frame_id"] == ctx.storyboard_plan.frames[0].frame_id
    assert "prompt_plan_bundle" not in ctx.planning_snapshot
    assert ctx.planning_snapshot["prompt_plan_bundle_ref"] == {
        "storyboard_plan_id": ctx.storyboard_plan.plan_id,
        "prompt_plan_count": 2,
        "image_prompt_draft_count": 2,
    }


@pytest.mark.asyncio
async def test_plan_visuals_defaults_template_to_canvas_orientation(monkeypatch):
    captured_resolver = {}

    def fake_resolve_template(template_type, orientation):
        captured_resolver.update(
            {
                "template_type": template_type,
                "orientation": orientation,
            }
        )
        return "1920x1080/image_landscape_minimal.html"

    async def fake_compose(self, **kwargs):
        return StyledImagePromptBatch(
            prompts=["prompt one", "prompt two"],
            negative_prompt=None,
            resolved_style=None,
            planning_snapshot={"storyboard_generation": kwargs["storyboard_plan"].to_dict()},
        )

    monkeypatch.setattr(
        "pixelle_video.pipelines.standard.resolve_default_template_for_type_and_orientation",
        fake_resolve_template,
    )
    monkeypatch.setattr(
        "pixelle_video.pipelines.standard.ImagePromptComposer.compose",
        fake_compose,
    )

    ctx = PipelineContext(
        input_text="first. second.",
        params={
            "video_orientation": "landscape",
            "video_resolution_preset": "landscape_hd",
        },
    )
    ctx.task_id = "task-plan-visuals-default-template"
    ctx.storyboard_plan = _plan()

    await StandardPipeline(_DummyCore()).plan_visuals(ctx)

    assert captured_resolver == {
        "template_type": "image",
        "orientation": "landscape",
    }
    assert ctx.image_prompts == ["prompt one", "prompt two"]


@pytest.mark.asyncio
async def test_static_template_skips_media_but_keeps_storyboard_plan(monkeypatch):
    monkeypatch.setattr("pixelle_video.pipelines.standard.get_template_type", lambda template_name: "static")

    ctx = PipelineContext(
        input_text="第一句。第二句。",
        params={"frame_template": "1080x1920/default.html"},
    )
    ctx.task_id = "task-static"
    ctx.storyboard_plan = _plan()

    await StandardPipeline(_DummyCore()).plan_visuals(ctx)

    assert ctx.image_prompts == [None, None]
    assert ctx.planning_snapshot["storyboard_generation"]["resolved_scene_count"] == 2


@pytest.mark.asyncio
async def test_generate_content_builds_caption_speech_plan_from_source_not_storyboard_frames(monkeypatch):
    source_text = "Original wording, untouched."
    storyboard_plan = StoryboardPlan.build(
        mode="smart",
        count_mode="auto",
        requested_scene_count=None,
        source_text=source_text,
        frames=[
            StoryboardPlanFrame(
                index=1,
                source_text=source_text,
                visual_goal="Show the original idea.",
                prompt_intent="Visualize the unchanged script.",
                source_start=0,
                source_end=len(source_text),
            )
        ],
    )

    async def fake_script_generate(self, **kwargs):
        return source_text

    async def fake_storyboard_generate(self, **kwargs):
        return storyboard_plan

    monkeypatch.setattr(
        "pixelle_video.pipelines.standard.ScriptGenerationService.generate",
        fake_script_generate,
    )
    monkeypatch.setattr(
        "pixelle_video.pipelines.standard.StoryboardGenerationService.generate",
        fake_storyboard_generate,
    )

    ctx = PipelineContext(input_text="topic", params={"mode": "generate"})
    await StandardPipeline(_DummyCore()).generate_content(ctx)

    assert ctx.caption_speech_plan.source_text == source_text
    assert [unit.speech_text for unit in ctx.caption_speech_plan.units] == [
        "Original wording,",
        "untouched.",
    ]
    assert not hasattr(ctx.storyboard_plan.frames[0], "narration_text")


@pytest.mark.asyncio
async def test_initialize_storyboard_defaults_template_to_canvas_orientation():
    ctx = PipelineContext(
        input_text="first. second.",
        params={
            "video_orientation": "landscape",
            "video_resolution_preset": "landscape_hd",
        },
    )
    ctx.task_id = "task-size-default-template"
    ctx.title = "Size default template"
    ctx.storyboard_plan = _plan()
    ctx.image_prompts = ["prompt one", "prompt two"]

    await StandardPipeline(_DummyCore()).initialize_storyboard(ctx)

    assert (ctx.config.canvas_width, ctx.config.canvas_height) == (1280, 720)
    assert ctx.config.video_orientation == "landscape"
    assert get_template_orientation(ctx.config.frame_template) == "landscape"


@pytest.mark.asyncio
async def test_initialize_storyboard_defaults_template_to_explicit_canvas_orientation():
    ctx = PipelineContext(
        input_text="first. second.",
        params={
            "canvas_width": 1080,
            "canvas_height": 1920,
            "media_width": 768,
            "media_height": 768,
        },
    )
    ctx.task_id = "task-explicit-canvas-default-template"
    ctx.title = "Explicit canvas default template"
    ctx.storyboard_plan = _plan()
    ctx.image_prompts = ["prompt one", "prompt two"]

    await StandardPipeline(_DummyCore()).initialize_storyboard(ctx)

    assert (ctx.config.canvas_width, ctx.config.canvas_height) == (1080, 1920)
    assert get_template_orientation(ctx.config.frame_template) == "portrait"


@pytest.mark.asyncio
async def test_initialize_storyboard_uses_explicit_template_orientation_when_size_unset():
    ctx = PipelineContext(
        input_text="first. second.",
        params={"frame_template": "1080x1920/image_default.html"},
    )
    ctx.task_id = "task-template-derived-size"
    ctx.title = "Template derived size"
    ctx.storyboard_plan = _plan()
    ctx.image_prompts = ["prompt one", "prompt two"]

    await StandardPipeline(_DummyCore()).initialize_storyboard(ctx)

    assert ctx.config.video_orientation == "portrait"
    assert (ctx.config.canvas_width, ctx.config.canvas_height) == (720, 1280)
    assert ctx.config.frame_template == "1080x1920/image_default.html"


@pytest.mark.asyncio
async def test_initialize_storyboard_preserves_compatible_explicit_template():
    ctx = PipelineContext(
        input_text="first. second.",
        params={
            "frame_template": "1920x1080/image_landscape_minimal.html",
            "video_orientation": "landscape",
            "video_resolution_preset": "landscape_hd",
        },
    )
    ctx.task_id = "task-explicit-template"
    ctx.title = "Explicit template"
    ctx.storyboard_plan = _plan()
    ctx.image_prompts = ["prompt one", "prompt two"]

    await StandardPipeline(_DummyCore()).initialize_storyboard(ctx)

    assert ctx.config.frame_template == "1920x1080/image_landscape_minimal.html"


@pytest.mark.asyncio
async def test_initialize_storyboard_rejects_template_canvas_orientation_mismatch():
    ctx = PipelineContext(
        input_text="first. second.",
        params={
            "frame_template": "1080x1920/image_default.html",
            "video_orientation": "landscape",
            "video_resolution_preset": "landscape_hd",
        },
    )
    ctx.task_id = "task-mismatched-explicit-template"
    ctx.title = "Mismatched explicit template"
    ctx.storyboard_plan = _plan()
    ctx.image_prompts = ["prompt one", "prompt two"]

    with pytest.raises(ValueError, match="Template orientation"):
        await StandardPipeline(_DummyCore()).initialize_storyboard(ctx)
