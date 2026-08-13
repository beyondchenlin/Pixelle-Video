from __future__ import annotations

from pixelle_video.services.visual_story_frame_services import (
    FrameVisualPlanBatchService,
)


class _WrappedFramePlanLLM:
    async def __call__(self, **_kwargs):
        return {
            "result": {
                "frame_plans": [
                    {
                        "frame_id": "frame-1",
                        "frame_index": 1,
                        "source_text": "source",
                        "local_claim": "claim",
                        "visual_task": "show claim",
                        "visual_logic": "use selected route",
                    }
                ]
            }
        }


class _RepairableFramePlanLLM:
    def __init__(self) -> None:
        self.calls = []

    async def __call__(self, **kwargs):
        self.calls.append(dict(kwargs))
        if len(self.calls) == 1:
            return {"unexpected": []}
        return {
            "frame_visual_plans": [
                {
                    "frame_id": "frame-1",
                    "frame_index": 1,
                    "source_text": "source",
                    "local_claim": "claim",
                    "visual_task": "show claim",
                    "visual_logic": "use selected route",
                }
            ]
        }


def _request_kwargs(llm_service):
    return {
        "llm_service": llm_service,
        "article_summary": {"summary": "article"},
        "selected_visual_route": {"route_id": "route-1"},
        "batch_payload": {
            "frame_contexts": [
                {
                    "frame_id": "frame-1",
                    "frame_index": 1,
                    "source_text": "source",
                }
            ]
        },
        "continuity_ledger": {},
    }


async def test_frame_plan_service_accepts_bounded_provider_wrapper_without_fallback():
    outcome = await FrameVisualPlanBatchService().plan_with_diagnostics(
        **_request_kwargs(_WrappedFramePlanLLM()),
    )

    assert outcome.fallback_used is False
    assert outcome.source == "model_content_only"
    assert [plan["frame_id"] for plan in outcome.plans] == ["frame-1"]


async def test_frame_plan_service_repairs_one_contract_failure_before_fallback():
    llm = _RepairableFramePlanLLM()

    outcome = await FrameVisualPlanBatchService().plan_with_diagnostics(
        **_request_kwargs(llm),
    )

    assert outcome.fallback_used is False
    assert outcome.source == "model_content_only"
    assert len(llm.calls) == 2
    assert [call["temperature"] for call in llm.calls] == [0.2, 0.0]
    assert "frame_visual_plans" in llm.calls[1]["prompt"]
    assert "missing_frame_collection" in llm.calls[1]["prompt"]
    assert "unexpected" not in llm.calls[1]["prompt"]
