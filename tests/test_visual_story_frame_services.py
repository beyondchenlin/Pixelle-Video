from __future__ import annotations

import pytest

from pixelle_video.services.frame_batch_contract import FrameBatchContractError
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
                        "required_subjects": ["worker"],
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
                    "required_subjects": ["worker"],
                }
            ]
        }


class _RepairableMissingSubjectsLLM:
    def __init__(self) -> None:
        self.calls = []

    async def __call__(self, **kwargs):
        self.calls.append(dict(kwargs))
        return {
            "frame_visual_plans": [
                {
                    "frame_id": "frame-1",
                    "frame_index": 1,
                    "source_text": "source",
                    "local_claim": "claim",
                    "visual_task": "show claim",
                    "visual_logic": "use selected route",
                    "required_subjects": (
                        [] if len(self.calls) == 1 else ["worker"]
                    ),
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


async def test_frame_plan_service_rejects_contract_failure_without_second_model_call():
    llm = _RepairableFramePlanLLM()

    with pytest.raises(FrameBatchContractError) as exc_info:
        await FrameVisualPlanBatchService().plan_with_diagnostics(
            **_request_kwargs(llm),
        )

    assert exc_info.value.code == "missing_frame_collection"
    assert len(llm.calls) == 1
    assert llm.calls[0]["temperature"] == 0.2


async def test_frame_plan_service_rejects_empty_subjects_without_second_model_call():
    llm = _RepairableMissingSubjectsLLM()

    with pytest.raises(FrameBatchContractError) as exc_info:
        await FrameVisualPlanBatchService().plan_with_diagnostics(
            **_request_kwargs(llm),
        )

    assert exc_info.value.code == "missing_required_subjects"
    assert len(llm.calls) == 1
