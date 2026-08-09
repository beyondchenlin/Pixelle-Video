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


class SequenceLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.call_count = 0

    async def __call__(self, *args, **kwargs):
        response = self.responses[self.call_count]
        self.call_count += 1
        return response


@pytest.mark.asyncio
async def test_batch_orchestrator_returns_prompt_context_with_fallbacks():
    result = await VisualStoryBatchOrchestrator().prepare(
        llm_service=NoopLLM(),
        source_text="source",
        storyboard_plan=Storyboard(),
        visual_story_plan={
            "plan_id": "plan-1",
            "article": {"summary": "summary"},
            "selected_visual_route": {
                "route_id": "route-1",
                "recommended_ip_role": "silent_witness",
            },
            "style_harmonization": {"mode": "hybrid_layered"},
        },
        ip_profile={"name": "dog", "visual_summary": "spotty dog"},
        batch_size=2,
        trace_context=None,
        trace_recorder=None,
    )
    assert result.execution_plan.frame_count == 5
    assert len(result.frame_visual_plans) == 5
    assert len(result.frame_ip_fusion_plans) == 5
    assert result.prompt_context["selected_visual_route"]["route_id"] == "route-1"
    assert all(
        batch["visual_plan_fallback_used"] for batch in result.diagnostics["batch_diagnostics"]
    )


@pytest.mark.asyncio
async def test_batch_orchestrator_preserves_bare_single_frame_batch_response():
    first_batch_ids = [f"frame-{index}" for index in range(1, 5)]
    llm = SequenceLLM(
        [
            {
                "frame_visual_plans": [
                    {"frame_id": frame_id, "source_text": frame_id, "visual_task": "explain"}
                    for frame_id in first_batch_ids
                ]
            },
            {"frame_ip_fusion_plans": [{"frame_id": frame_id} for frame_id in first_batch_ids]},
            {"frame_id": "frame-5", "source_text": "frame-5", "visual_task": "explain"},
            {"frame_id": "frame-5"},
        ]
    )

    result = await VisualStoryBatchOrchestrator().prepare(
        llm_service=llm,
        source_text="source",
        storyboard_plan=Storyboard(),
        visual_story_plan={
            "plan_id": "plan-1",
            "article": {"summary": "summary"},
            "selected_visual_route": {
                "route_id": "route-1",
                "recommended_ip_role": "silent_witness",
            },
            "style_harmonization": {"mode": "hybrid_layered"},
        },
        ip_profile={"name": "dog", "visual_summary": "spotty dog"},
        batch_size=4,
    )

    assert llm.call_count == 4
    assert [item["frame_id"] for item in result.frame_visual_plans] == [
        "frame-1",
        "frame-2",
        "frame-3",
        "frame-4",
        "frame-5",
    ]
    assert [item["frame_id"] for item in result.frame_ip_fusion_plans] == [
        "frame-1",
        "frame-2",
        "frame-3",
        "frame-4",
        "frame-5",
    ]
    assert not any(
        batch["visual_plan_fallback_used"] for batch in result.diagnostics["batch_diagnostics"]
    )


@pytest.mark.asyncio
async def test_batch_orchestrator_rejects_duplicate_storyboard_frame_ids_before_model_call():
    storyboard = Storyboard()
    storyboard.frames = [Frame(0), Frame(1)]
    storyboard.frames[1].frame_id = "frame-1"
    llm = SequenceLLM([])

    with pytest.raises(ValueError, match="frame_id values must be unique"):
        await VisualStoryBatchOrchestrator().prepare(
            llm_service=llm,
            source_text="source",
            storyboard_plan=storyboard,
            visual_story_plan={
                "plan_id": "plan-1",
                "article": {"summary": "summary"},
                "selected_visual_route": {"route_id": "route-1"},
            },
        )

    assert llm.call_count == 0
