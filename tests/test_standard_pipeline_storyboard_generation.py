import pytest

from pixelle_video.models.caption_speech_plan import CaptionSpeechPlan
from pixelle_video.models.storyboard_plan import StoryboardPlan, StoryboardPlanFrame
from pixelle_video.models.style_resolution import StyledImagePromptBatch
from pixelle_video.pipelines.linear import PipelineContext
from pixelle_video.pipelines.standard import StandardPipeline


class _DummyCore:
    def __init__(self, config=None):
        self.config = config or {"comfyui": {"image": {}, "video": {}}}
        self.llm = object()
        self.tts = None
        self.media = object()
        self.video = None


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
async def test_generate_content_uses_core_storyboard_limits_config():
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

    with pytest.raises(ValueError, match="too many storyboard frames"):
        await StandardPipeline(core).generate_content(ctx)


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
