import pytest

from pixelle_video.services.visual_story_batch_orchestrator import VisualStoryBatchOrchestrator


class Frame:
    def __init__(self, index):
        self.frame_id = f"frame-{index + 1}"
        self.index = index
        self.source_text = f"source {index + 1}"
        self.visual_goal = f"goal {index + 1}"
        self.prompt_intent = f"intent {index + 1}"


class Storyboard:
    frames = [Frame(i) for i in range(5)]


class NoopLLM:
    async def __call__(self, *args, **kwargs):
        raise RuntimeError("force deterministic fallback")


@pytest.mark.asyncio
async def test_batch_orchestrator_returns_prompt_context_with_fallbacks():
    result = await VisualStoryBatchOrchestrator().prepare(
        llm_service=NoopLLM(),
        source_text="source",
        storyboard_plan=Storyboard(),
        visual_story_plan={"plan_id": "plan-1", "article": {"summary": "summary"}, "selected_visual_route": {"route_id": "route-1", "recommended_ip_role": "silent_witness"}, "style_harmonization": {"mode": "hybrid_layered"}},
        ip_profile={"name": "dog", "visual_summary": "spotty dog"},
        batch_size=2,
        trace_context=None,
        trace_recorder=None,
    )
    assert result.execution_plan.frame_count == 5
    assert len(result.frame_visual_plans) == 5
    assert len(result.frame_ip_fusion_plans) == 5
    assert result.prompt_context["selected_visual_route"]["route_id"] == "route-1"
