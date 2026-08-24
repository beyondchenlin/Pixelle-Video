from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from pixelle_video.models.storyboard_workbench import StoryboardFrameWorkbenchState
from pixelle_video.services.storyboard_workbench import (
    FrameImageRegenerationTaskRequest,
    StoryboardImageCandidate,
)
from tests.support.test_client import create_test_client


@dataclass
class FakeWorkbenchStateStore:
    states: dict[tuple[str, str, str], StoryboardFrameWorkbenchState]
    saved_states: list[tuple[str, str, str, dict[str, Any]]]

    async def load_frame_state(
        self,
        workspace_id: str,
        storyboard_id: str,
        frame_id: str,
    ) -> dict[str, Any] | None:
        state = self.states.get((workspace_id, storyboard_id, frame_id))
        return state.to_dict() if state else None

    async def save_frame_state(
        self,
        workspace_id: str,
        storyboard_id: str,
        frame_id: str,
        state: dict[str, Any],
    ) -> dict[str, Any]:
        self.saved_states.append((workspace_id, storyboard_id, frame_id, dict(state)))
        self.states[(workspace_id, storyboard_id, frame_id)] = (
            StoryboardFrameWorkbenchState.from_dict(state)
        )
        return state


@dataclass
class FakeWorkbenchService:
    listed_artifacts: list[tuple[str, str]]
    selected_versions: list[dict[str, Any]]
    regeneration_requests: list[dict[str, Any]]
    candidate_frame_id: str = "frame_0001"

    async def list_image_candidates(
        self,
        *,
        workspace_id: str,
        artifact_id: str,
    ) -> tuple[StoryboardImageCandidate, ...]:
        self.listed_artifacts.append((workspace_id, artifact_id))
        return (
            StoryboardImageCandidate(
                artifact_id=artifact_id,
                version_id="artifact_version_001",
                frame_id=self.candidate_frame_id,
                prompt_plan_id="prompt_plan_001",
                storage_key="artifacts/workspace_1/frame_0001/artifact_version_001.png",
                status="succeeded",
                provider="comfyui",
                url="https://cdn.pixelle.test/artifacts/workspace_1/frame_0001/artifact_version_001.png",
                width=1024,
                height=1024,
                trace_event_id="generation_event_001",
            ),
        )

    async def select_image_version(
        self,
        *,
        workspace_id: str,
        state: StoryboardFrameWorkbenchState,
        artifact_id: str,
        version_id: str,
        actor_id: str | None = None,
        allow_locked: bool = False,
    ) -> StoryboardFrameWorkbenchState:
        self.selected_versions.append(
            {
                "workspace_id": workspace_id,
                "frame_id": state.frame_id,
                "artifact_id": artifact_id,
                "version_id": version_id,
                "actor_id": actor_id,
                "allow_locked": allow_locked,
            }
        )
        return StoryboardFrameWorkbenchState(
            frame_id=state.frame_id,
            prompt_plan_id=state.prompt_plan_id,
            selected_image_artifact_id=artifact_id,
            selected_image_version_id=version_id,
            candidate_image_version_ids=(
                *state.candidate_image_version_ids,
                version_id,
            ),
        )

    def build_frame_image_regeneration_task_request(
        self,
        *,
        workspace_id: str,
        storyboard_id: str,
        state: StoryboardFrameWorkbenchState,
        artifact_id: str,
        provider: str | None = None,
        model: str | None = None,
    ) -> FrameImageRegenerationTaskRequest:
        self.regeneration_requests.append(
            {
                "workspace_id": workspace_id,
                "storyboard_id": storyboard_id,
                "frame_id": state.frame_id,
                "artifact_id": artifact_id,
                "provider": provider,
                "model": model,
            }
        )
        return FrameImageRegenerationTaskRequest(
            generation_fingerprint="fingerprint-frame-0001",
            request_params={
                "workspace_id": workspace_id,
                "storyboard_id": storyboard_id,
                "frame_id": state.frame_id,
                "prompt_plan_id": state.prompt_plan_id,
                "artifact_id": artifact_id,
                "provider": provider,
                "model": model,
                "generation_fingerprint": "fingerprint-frame-0001",
            },
        )


@dataclass
class FakeStoryboardWorkbenchTaskSubmitter:
    reserved: list[dict[str, Any]]

    async def get_capabilities(self):
        from api.workbench.task_submitter import StoryboardWorkbenchCapabilities

        return StoryboardWorkbenchCapabilities(
            can_regenerate_frame_image=True,
            regenerate_unavailable_reason=None,
        )

    async def reserve_frame_image_regeneration(
        self,
        *,
        generation_fingerprint: str,
        request_params: dict[str, Any],
    ):
        from api.workbench.task_submitter import StoryboardWorkbenchTaskSubmission

        self.reserved.append(
            {
                "generation_fingerprint": generation_fingerprint,
                "request_params": request_params,
            }
        )
        return StoryboardWorkbenchTaskSubmission(
            task_id="regen-task-1",
            task_type="frame_image_regeneration",
            created=True,
        )


def _state() -> StoryboardFrameWorkbenchState:
    return StoryboardFrameWorkbenchState(
        frame_id="frame_0001",
        prompt_plan_id="prompt_plan_001",
        selected_image_artifact_id="artifact_frame_0001_image",
        selected_image_version_id="artifact_version_001",
        candidate_image_version_ids=("artifact_version_001",),
    )


def _client(
    *,
    workbench_service: FakeWorkbenchService | None = None,
    state_store: FakeWorkbenchStateStore | None = None,
    task_submitter: FakeStoryboardWorkbenchTaskSubmitter | None = None,
) -> TestClient:
    from api.routers.storyboard_workbench import router as storyboard_workbench_router

    app = FastAPI()
    if workbench_service is not None:
        app.state.storyboard_workbench_service = workbench_service
    if state_store is not None:
        app.state.storyboard_workbench_state_store = state_store
    if task_submitter is not None:
        app.state.storyboard_workbench_task_submitter = task_submitter
    app.include_router(storyboard_workbench_router)
    return create_test_client(app)


def _state_store() -> FakeWorkbenchStateStore:
    return FakeWorkbenchStateStore(
        states={("workspace_1", "storyboard_001", "frame_0001"): _state()},
        saved_states=[],
    )


def test_storyboard_workbench_api_reports_capabilities_from_submitter():
    client = _client(task_submitter=FakeStoryboardWorkbenchTaskSubmitter(reserved=[]))

    response = client.get("/storyboards/workbench/capabilities")

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "message": "Success",
        "can_regenerate_frame_image": True,
        "regenerate_unavailable_reason": None,
    }


def test_storyboard_workbench_api_reports_regenerate_unavailable_without_submitter():
    client = _client()

    response = client.get("/storyboards/workbench/capabilities")

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "message": "Success",
        "can_regenerate_frame_image": False,
        "regenerate_unavailable_reason": "task submitter is not configured",
    }


def test_storyboard_workbench_api_lists_image_candidates_without_local_paths():
    service = FakeWorkbenchService(
        listed_artifacts=[],
        selected_versions=[],
        regeneration_requests=[],
    )
    client = _client(workbench_service=service)

    response = client.get(
        "/storyboards/storyboard_001/frames/frame_0001/images",
        params={
            "workspace_id": "workspace_1",
            "artifact_id": "artifact_frame_0001_image",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["storyboard_id"] == "storyboard_001"
    assert body["frame_id"] == "frame_0001"
    assert body["artifact_id"] == "artifact_frame_0001_image"
    assert body["candidates"][0]["version_id"] == "artifact_version_001"
    assert body["candidates"][0]["storage_key"] == (
        "artifacts/workspace_1/frame_0001/artifact_version_001.png"
    )
    assert body["candidates"][0]["url"].startswith("https://cdn.pixelle.test/")
    assert "local_path" not in str(body)
    assert service.listed_artifacts == [
        ("workspace_1", "artifact_frame_0001_image"),
    ]


def test_storyboard_workbench_api_selects_image_version_and_saves_state():
    service = FakeWorkbenchService(
        listed_artifacts=[],
        selected_versions=[],
        regeneration_requests=[],
    )
    state_store = _state_store()
    client = _client(workbench_service=service, state_store=state_store)

    response = client.post(
        "/storyboards/storyboard_001/frames/frame_0001/select-image",
        json={
            "workspace_id": "workspace_1",
            "artifact_id": "artifact_frame_0001_image",
            "version_id": "artifact_version_002",
            "actor_id": "user_1",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["state"]["selected_image_version_id"] == "artifact_version_002"
    assert state_store.saved_states[-1][0:3] == (
        "workspace_1",
        "storyboard_001",
        "frame_0001",
    )
    assert service.selected_versions == [
        {
            "workspace_id": "workspace_1",
            "frame_id": "frame_0001",
            "artifact_id": "artifact_frame_0001_image",
            "version_id": "artifact_version_002",
            "actor_id": "user_1",
            "allow_locked": False,
        }
    ]


def test_storyboard_workbench_api_requests_frame_image_regeneration_task():
    service = FakeWorkbenchService(
        listed_artifacts=[],
        selected_versions=[],
        regeneration_requests=[],
    )
    task_submitter = FakeStoryboardWorkbenchTaskSubmitter(reserved=[])
    client = _client(
        workbench_service=service,
        state_store=_state_store(),
        task_submitter=task_submitter,
    )

    response = client.post(
        "/storyboards/storyboard_001/frames/frame_0001/regenerate-image",
        json={
            "workspace_id": "workspace_1",
            "artifact_id": "artifact_frame_0001_image",
            "provider": "comfyui",
            "model": "z-image",
        },
    )

    assert response.status_code == 202
    body = response.json()
    assert body["success"] is True
    assert body["task_id"] == "regen-task-1"
    assert body["task_type"] == "frame_image_regeneration"
    assert body["created"] is True
    assert body["generation_fingerprint"] == "fingerprint-frame-0001"
    assert task_submitter.reserved == [
        {
            "generation_fingerprint": "fingerprint-frame-0001",
            "request_params": {
                "workspace_id": "workspace_1",
                "storyboard_id": "storyboard_001",
                "frame_id": "frame_0001",
                "prompt_plan_id": "prompt_plan_001",
                "artifact_id": "artifact_frame_0001_image",
                "provider": "comfyui",
                "model": "z-image",
                "generation_fingerprint": "fingerprint-frame-0001",
            },
        }
    ]


def test_storyboard_workbench_api_regenerate_fails_without_submitter():
    service = FakeWorkbenchService(
        listed_artifacts=[],
        selected_versions=[],
        regeneration_requests=[],
    )
    client = _client(workbench_service=service, state_store=_state_store())

    response = client.post(
        "/storyboards/storyboard_001/frames/frame_0001/regenerate-image",
        json={
            "workspace_id": "workspace_1",
            "artifact_id": "artifact_frame_0001_image",
        },
    )

    assert response.status_code == 503
    assert "task submitter is not configured" in response.json()["detail"]


def test_storyboard_workbench_api_regenerate_fails_when_execution_path_is_missing():
    class UnavailableSubmitter(FakeStoryboardWorkbenchTaskSubmitter):
        async def get_capabilities(self):
            from api.workbench.task_submitter import StoryboardWorkbenchCapabilities

            return StoryboardWorkbenchCapabilities(
                can_regenerate_frame_image=False,
                regenerate_unavailable_reason=(
                    "frame image regeneration execution is not configured"
                ),
            )

    service = FakeWorkbenchService(
        listed_artifacts=[],
        selected_versions=[],
        regeneration_requests=[],
    )
    client = _client(
        workbench_service=service,
        state_store=_state_store(),
        task_submitter=UnavailableSubmitter(reserved=[]),
    )

    response = client.post(
        "/storyboards/storyboard_001/frames/frame_0001/regenerate-image",
        json={
            "workspace_id": "workspace_1",
            "artifact_id": "artifact_frame_0001_image",
        },
    )

    assert response.status_code == 503
    assert "frame image regeneration execution is not configured" in response.json()["detail"]


def test_storyboard_workbench_api_fails_fast_without_injected_service():
    response = _client().get(
        "/storyboards/storyboard_001/frames/frame_0001/images",
        params={
            "workspace_id": "workspace_1",
            "artifact_id": "artifact_frame_0001_image",
        },
    )

    assert response.status_code == 503
    assert "storyboard workbench service is not configured" in response.json()["detail"]


def test_storyboard_workbench_api_rejects_path_like_resource_ids_before_service_call():
    service = FakeWorkbenchService(
        listed_artifacts=[],
        selected_versions=[],
        regeneration_requests=[],
    )
    client = _client(workbench_service=service)

    response = client.get(
        "/storyboards/storyboard_001/frames/frame_0001/images",
        params={
            "workspace_id": "workspace_1",
            "artifact_id": r"C:\tmp\frame.png",
        },
    )

    assert response.status_code == 422
    assert service.listed_artifacts == []


def test_storyboard_workbench_api_rejects_cross_frame_candidate_payloads():
    service = FakeWorkbenchService(
        listed_artifacts=[],
        selected_versions=[],
        regeneration_requests=[],
        candidate_frame_id="frame_9999",
    )
    client = _client(workbench_service=service)

    response = client.get(
        "/storyboards/storyboard_001/frames/frame_0001/images",
        params={
            "workspace_id": "workspace_1",
            "artifact_id": "artifact_frame_0001_image",
        },
    )

    assert response.status_code == 502
    assert "candidate image does not match requested frame" in response.json()["detail"]


def test_storyboard_workbench_router_does_not_reach_through_to_task_manager():
    from pathlib import Path

    source = Path("api/routers/storyboard_workbench.py").read_text(encoding="utf-8")

    assert "app.state.task_manager" not in source
    assert "reserve_or_reuse_generation_task" not in source
