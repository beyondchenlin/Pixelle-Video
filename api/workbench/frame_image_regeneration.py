from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pixelle_video.models.progress import ProgressEvent, ProgressEventType
from pixelle_video.models.prompt_plan import PromptPlan
from pixelle_video.models.size_contract import GenerationSizeContract
from pixelle_video.models.storyboard_workbench import StoryboardFrameWorkbenchState
from pixelle_video.services.prompt_trace_artifacts import (
    media_workflow_trace_context,
    write_single_media_prompt_artifact,
)
from pixelle_video.utils.os_util import get_runtime_path


async def execute_frame_image_regeneration(
    *,
    core: Any,
    task_id: str,
    request_params: Mapping[str, Any],
    progress_dispatcher: Any | None = None,
) -> dict[str, Any]:
    workspace_id = _require_param(request_params, "workspace_id")
    storyboard_id = _require_param(request_params, "storyboard_id")
    frame_id = _require_param(request_params, "frame_id")
    prompt_plan_id = _require_param(request_params, "prompt_plan_id")
    artifact_id = _require_param(request_params, "artifact_id")

    service = _require_attr(core, "storyboard_workbench_service")
    state_store = _require_attr(core, "storyboard_workbench_state_store")
    prompt_plan_repository = _require_attr(core, "prompt_plan_repository")
    media = _require_attr(core, "media")

    state_payload = await state_store.load_frame_state(workspace_id, storyboard_id, frame_id)
    if state_payload is None:
        raise RuntimeError("storyboard frame workbench state was not found")
    state = (
        state_payload
        if isinstance(state_payload, StoryboardFrameWorkbenchState)
        else StoryboardFrameWorkbenchState.from_dict(state_payload)
    )
    prompt_plan = await _load_prompt_plan(
        prompt_plan_repository,
        workspace_id=workspace_id,
        storyboard_id=storyboard_id,
        prompt_plan_id=prompt_plan_id,
    )
    size_contract = GenerationSizeContract.from_params(request_params)
    workflow = request_params.get("model") or request_params.get("media_workflow")
    workflow_trace_context = media_workflow_trace_context(
        media,
        workflow=workflow,
        media_type="image",
    )
    negative_prompt = request_params.get("media_negative_prompt") or request_params.get(
        "negative_prompt"
    )
    if progress_dispatcher is not None:
        progress_dispatcher.emit(
            ProgressEvent(event_type=ProgressEventType.GENERATION, progress=0.0)
        )
    prompt_trace_root = getattr(core, "prompt_trace_output_dir", None)
    prompt_trace_output_dir = (
        Path(prompt_trace_root) / task_id
        if prompt_trace_root is not None
        else Path(get_runtime_path("media_prompt_traces", task_id))
    )
    write_single_media_prompt_artifact(
        prompt_trace_output_dir,
        task_id=task_id,
        prompt=prompt_plan.final_prompt,
        negative_prompt=str(negative_prompt or ""),
        frame_id=frame_id,
        generation_context={
            "source": "storyboard_workbench.frame_image_regeneration",
            "workspace_id": workspace_id,
            "storyboard_id": storyboard_id,
            "frame_id": frame_id,
            "prompt_plan_id": prompt_plan_id,
            "artifact_id": artifact_id,
            **workflow_trace_context,
            "media_type": "image",
            "width": size_contract.media_width,
            "height": size_contract.media_height,
        },
    )
    media_result = await media(
        prompt=prompt_plan.final_prompt,
        media_type="image",
        workflow=workflow,
        width=size_contract.media_width,
        height=size_contract.media_height,
        negative_prompt=negative_prompt,
    )
    source_path = _resolve_media_source_path(media_result.url)
    result = await service.record_frame_image_regeneration_result(
        workspace_id=workspace_id,
        task_id=task_id,
        state=state,
        artifact_id=artifact_id,
        source_path=source_path,
        project_id=request_params.get("project_id"),
        prompt_plan=prompt_plan,
        provider=request_params.get("provider"),
        provider_metadata=(
            {"workflow": workflow_trace_context["workflow"]}
            if workflow_trace_context.get("workflow")
            else {}
        ),
        width=size_contract.media_width,
        height=size_contract.media_height,
    )
    await state_store.save_frame_state(
        workspace_id,
        storyboard_id,
        frame_id,
        result.workbench_state.to_dict(),
    )
    if progress_dispatcher is not None:
        progress_dispatcher.emit(
            ProgressEvent(event_type=ProgressEventType.COMPLETED, progress=1.0)
        )
    return {
        "workspace_id": workspace_id,
        "storyboard_id": storyboard_id,
        "frame_id": frame_id,
        "artifact_id": artifact_id,
        "artifact_version_id": result.artifact_version.version_id,
        "storage_key": result.artifact_version.storage_key,
    }


async def _load_prompt_plan(
    prompt_plan_repository: Any,
    *,
    workspace_id: str,
    storyboard_id: str,
    prompt_plan_id: str,
) -> PromptPlan:
    payloads = await prompt_plan_repository.load_prompt_plans_by_storyboard(
        workspace_id,
        storyboard_id,
    )
    for payload in payloads:
        plan = payload if isinstance(payload, PromptPlan) else PromptPlan.from_dict(payload)
        if plan.prompt_plan_id == prompt_plan_id:
            return plan
    raise RuntimeError("prompt plan was not found")


def _resolve_media_source_path(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        raise RuntimeError("media generation did not return an image path")
    if raw.startswith("file://"):
        from urllib.parse import urlparse
        from urllib.request import url2pathname

        parsed = urlparse(raw)
        return str(Path(url2pathname(parsed.path)))
    return raw


def _require_param(params: Mapping[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        raise RuntimeError(f"{key} is required")
    return value


def _require_attr(target: Any, name: str) -> Any:
    value = getattr(target, name, None)
    if value is None:
        raise RuntimeError(f"{name} is not configured")
    return value


__all__ = ["execute_frame_image_regeneration"]
