import pytest

from pixelle_video.models.storyboard_plan import StoryboardPlan, StoryboardPlanFrame
from pixelle_video.pipelines.linear import PipelineContext
from pixelle_video.pipelines.standard import StandardPipeline


@pytest.mark.asyncio
async def test_generate_content_routes_complete_script_before_storyboard_planning(monkeypatch):
    captured = {}

    class _FakeCore:
        config = {
            "render": {
                "timing": {
                    "preserve_natural_punctuation": False,
                },
            },
        }
        llm = object()
        tts = None
        media = None
        video = None

    async def fake_script_generate(self, **kwargs):
        captured["script"] = kwargs
        return "完整文案第一句。完整文案第二句。"

    async def fake_storyboard_generate(self, **kwargs):
        captured["storyboard"] = kwargs

        return StoryboardPlan.build(
            mode="smart",
            count_mode="auto",
            requested_scene_count=None,
            source_text=kwargs["source_text"],
            frames=[
                StoryboardPlanFrame(
                    index=1,
                    source_text=kwargs["source_text"],
                    narration_text=kwargs["source_text"],
                    visual_goal="Show the generated source text.",
                    prompt_intent="Use the complete generated script as storyboard source.",
                    source_start=0,
                    source_end=len(kwargs["source_text"]),
                )
            ],
        )

    monkeypatch.setattr(
        "pixelle_video.pipelines.standard.ScriptGenerationService.generate",
        fake_script_generate,
    )
    monkeypatch.setattr(
        "pixelle_video.pipelines.standard.StoryboardGenerationService.generate",
        fake_storyboard_generate,
    )

    pipeline = StandardPipeline(_FakeCore())
    ctx = PipelineContext(input_text="topic", params={"mode": "generate"})

    await pipeline.generate_content(ctx)

    assert captured["script"]["topic"] == "topic"
    assert captured["storyboard"]["source_text"] == "完整文案第一句。完整文案第二句。"
    assert "preserve_natural_punctuation" not in captured["storyboard"]
    assert ctx.narrations == ["完整文案第一句。完整文案第二句。"]
