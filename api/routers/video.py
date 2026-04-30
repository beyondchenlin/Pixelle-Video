# Copyright (C) 2025 AIDC-AI
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Video generation endpoints

Supports both synchronous and asynchronous video generation.
"""

import os

from fastapi import APIRouter, HTTPException, Request
from loguru import logger

from api.dependencies import PixelleVideoDep
from api.schemas.video import (
    VideoGenerateAsyncResponse,
    VideoGenerateRequest,
    VideoGenerateResponse,
    validate_raw_frame_template_orientation,
)
from api.tasks import TaskType, task_manager
from pixelle_video.models.size_contract import GenerationSizeContract
from pixelle_video.services.generation_coordinator import build_generation_fingerprint
from pixelle_video.services.resource_resolver import (
    ResourceIdInvalidError,
    ResourceNotFoundError,
    ResourceResolver,
    ResourceResolverError,
)
from pixelle_video.utils.logging_util import build_content_observability, new_correlation_id
from pixelle_video.utils.prompt_generation_performance import (
    copy_prompt_generation_performance_params,
)

router = APIRouter(prefix="/video", tags=["Video Generation"])

TTS_TEXT_POLICY_PARAM_NAMES = (
    "tts_split_mode",
    "max_chars_per_tts_segment",
    "tts_split_overflow_policy",
    "tts_boundary_search_radius",
    "tts_soft_overflow_chars",
    "tts_audio_boundary_fade_ms",
    "tts_sentence_joiner_mode",
    "caption_punctuation_mode",
    "preserve_natural_punctuation",
)

PUBLIC_RESOURCE_PARAM_NAMES = (
    "style_id",
    "template_id",
    "voice_id",
    "bgm_id",
    "workflow_preset_id",
)


def _serialize_frame_overrides(frame_overrides):
    if frame_overrides is None:
        return None
    return [override.model_dump(exclude_none=True) for override in frame_overrides]


def _copy_tts_text_policy_params(request_body: VideoGenerateRequest, video_params: dict) -> None:
    for name in TTS_TEXT_POLICY_PARAM_NAMES:
        value = getattr(request_body, name)
        if value is not None:
            video_params[name] = value


def build_video_generation_params(
    request_body: VideoGenerateRequest,
    *,
    request_id: str,
    api_task_id: str | None = None,
    resource_resolver: ResourceResolver | None = None,
) -> dict:
    """Build PixelleVideoCore.generate_video kwargs from an API request."""
    raw_resource_params = _build_raw_resource_params(
        request_body,
        resource_resolver=resource_resolver,
    )
    size_params = {
        "canvas_width": request_body.canvas_width,
        "canvas_height": request_body.canvas_height,
        "media_width": request_body.media_width,
        "media_height": request_body.media_height,
        "video_orientation": request_body.video_orientation,
        "video_resolution_preset": request_body.video_resolution_preset,
        "media_orientation": request_body.media_orientation,
        "media_resolution_preset": request_body.media_resolution_preset,
        "sync_media_size_to_canvas": request_body.sync_media_size_to_canvas,
    }
    video_orientation = validate_raw_frame_template_orientation(
        frame_template=raw_resource_params.get("frame_template"),
        video_orientation=request_body.video_orientation,
        size_params=size_params,
    )
    size_params["video_orientation"] = video_orientation
    size_contract = GenerationSizeContract.from_params(size_params)
    video_params = {
        "text": request_body.text,
        "mode": request_body.mode,
        "title": request_body.title,
        "storyboard_mode": request_body.storyboard_mode,
        "storyboard_count_mode": request_body.storyboard_count_mode,
        "storyboard_scene_count": request_body.storyboard_scene_count,
        "storyboard_max_scene_count": request_body.storyboard_max_scene_count,
        "script_length_mode": request_body.script_length_mode,
        "script_target_words": request_body.script_target_words,
        "min_image_prompt_words": request_body.min_image_prompt_words,
        "max_image_prompt_words": request_body.max_image_prompt_words,
        **size_contract.to_params(),
        "media_placement": request_body.media_placement.to_model().to_dict(),
        "media_workflow": raw_resource_params.get("media_workflow"),
        "video_fps": request_body.video_fps,
        "frame_template": raw_resource_params.get("frame_template"),
        "prompt_prefix": raw_resource_params.get("prompt_prefix"),
        "world_preset_id": request_body.world_preset_id,
        "shot_preset_id": request_body.shot_preset_id,
        "storyboard_prompt_language": request_body.storyboard_prompt_language,
        "consistency_strength": request_body.consistency_strength or "standard",
        "content_mode": request_body.content_mode,
        "role_strategy": request_body.role_strategy,
        "role_locking_strength": request_body.role_locking_strength,
        "shot_strategy": request_body.shot_strategy,
        "frame_overrides": _serialize_frame_overrides(request_body.frame_overrides),
        "bgm_path": raw_resource_params.get("bgm_path"),
        "bgm_volume": request_body.bgm_volume,
        "request_id": request_id,
    }

    if api_task_id is not None:
        video_params["api_task_id"] = api_task_id

    if raw_resource_params.get("tts_workflow"):
        video_params["tts_workflow"] = raw_resource_params["tts_workflow"]

    if raw_resource_params.get("ref_audio"):
        video_params["ref_audio"] = raw_resource_params["ref_audio"]

    if raw_resource_params.get("voice_id"):
        video_params["voice_id"] = raw_resource_params["voice_id"]

    if request_body.tts_audio_strategy is not None:
        video_params["tts_audio_strategy"] = request_body.tts_audio_strategy

    if request_body.template_params:
        video_params["template_params"] = request_body.template_params

    if request_body.render_backend is not None:
        video_params["render_backend"] = request_body.render_backend

    if request_body.text_rendering is not None:
        video_params["text_rendering"] = request_body.text_rendering.model_dump(
            exclude_none=True
        )

    _copy_tts_text_policy_params(request_body, video_params)
    copy_prompt_generation_performance_params(request_body, video_params)
    return video_params


def _build_raw_resource_params(
    request_body: VideoGenerateRequest,
    *,
    resource_resolver: ResourceResolver | None,
) -> dict[str, str | None]:
    raw_params = {
        "prompt_prefix": getattr(request_body, "prompt_prefix", None),
        "frame_template": getattr(request_body, "frame_template", None),
        "voice_id": getattr(request_body, "voice_id", None),
        "bgm_path": getattr(request_body, "bgm_path", None),
        "media_workflow": getattr(request_body, "media_workflow", None),
        "tts_workflow": getattr(request_body, "tts_workflow", None),
        "ref_audio": getattr(request_body, "ref_audio", None),
    }
    if not _has_public_resource_ids(request_body):
        return raw_params
    if resource_resolver is None:
        raise ResourceResolverError("resource resolver is required for public resource IDs")

    if request_body.style_id:
        raw_params["prompt_prefix"] = resource_resolver.resolve_style_id(
            request_body.style_id
        ).resolved_value
    if request_body.template_id:
        raw_params["frame_template"] = resource_resolver.resolve_template_id(
            request_body.template_id
        ).resolved_value
    if request_body.voice_id:
        raw_params["voice_id"] = resource_resolver.resolve_voice_id(
            request_body.voice_id
        ).resolved_value
    if request_body.bgm_id:
        raw_params["bgm_path"] = resource_resolver.resolve_bgm_id(
            request_body.bgm_id
        ).resolved_value
    if request_body.workflow_preset_id:
        raw_params["media_workflow"] = resource_resolver.resolve_workflow_preset_id(
            request_body.workflow_preset_id
        ).resolved_value
    return raw_params


def _has_public_resource_ids(request_body: VideoGenerateRequest) -> bool:
    return any(
        getattr(request_body, name, None)
        for name in PUBLIC_RESOURCE_PARAM_NAMES
    )


def _get_resource_resolver(
    request: Request,
    request_body: VideoGenerateRequest,
) -> ResourceResolver | None:
    if not _has_public_resource_ids(request_body):
        return None
    resolver = getattr(request.app.state, "resource_resolver", None)
    if resolver is None:
        raise HTTPException(status_code=503, detail="resource resolver is not configured")
    return resolver


def _resource_resolver_http_exception(exc: ResourceResolverError) -> HTTPException:
    if isinstance(exc, ResourceIdInvalidError):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, ResourceNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))


def path_to_storage_key(file_path: str) -> str:
    """Convert a local output path into a storage key under output/."""
    from pathlib import Path

    normalized = file_path.replace("\\", "/")
    is_absolute = os.path.isabs(normalized) or Path(normalized).is_absolute()

    if is_absolute:
        parts = normalized.split("/")
        try:
            output_idx = parts.index("output")
            return "/".join(parts[output_idx + 1:])
        except ValueError:
            return Path(normalized).name

    if normalized.startswith("output/"):
        return normalized[7:]
    return normalized


def path_to_url(request: Request, file_path: str) -> str:
    """
    Convert file path to accessible URL
    
    Handles both absolute and relative paths, extracting the path relative
    to the output directory for URL construction.
    
    Args:
        request: FastAPI Request object (provides base_url from actual request)
        file_path: Absolute or relative file path
    
    Returns:
        Full URL to access the file
    
    Examples:
        Windows: G:\\...\\output\\20251205_233630_c939\\final.mp4
              -> http://localhost:8000/api/files/20251205_233630_c939/final.mp4
        
        Linux:   /home/user/.../output/20251205_233630_c939/final.mp4
              -> http://localhost:8000/api/files/20251205_233630_c939/final.mp4
        
        Domain:  With domain request -> https://your-domain.com/api/files/...
    """
    # Build URL using request's base_url (automatically matches the request host)
    base_url = str(request.base_url).rstrip('/')
    return f"{base_url}/api/files/{path_to_storage_key(file_path)}"


@router.post("/generate/sync", response_model=VideoGenerateResponse)
async def generate_video_sync(
    request_body: VideoGenerateRequest,
    pixelle_video: PixelleVideoDep,
    request: Request
):
    """
    Generate video synchronously
    
    This endpoint blocks until video generation is complete.
    Suitable for small videos (< 30 seconds).
    
    **Note**: May timeout for large videos. Use `/generate/async` instead.
    
    Request body includes all video generation parameters.
    See VideoGenerateRequest schema for details.
    
    Returns path to generated video, duration, and file size.
    """
    try:
        request_id = new_correlation_id("req")
        logger.bind(
            channel="runtime",
            request_id=request_id,
            content=build_content_observability(request_body.text),
        ).info("sync video generation request received")

        resource_resolver = _get_resource_resolver(request, request_body)
        video_params = build_video_generation_params(
            request_body,
            request_id=request_id,
            resource_resolver=resource_resolver,
        )
        
        # Call video generator service
        result = await pixelle_video.generate_video(**video_params)
        
        # Get file size
        file_size = os.path.getsize(result.video_path) if os.path.exists(result.video_path) else 0
        
        # Convert path to URL
        video_url = path_to_url(request, result.video_path)
        
        return VideoGenerateResponse(
            video_url=video_url,
            duration=result.duration,
            file_size=file_size
        )
        
    except HTTPException:
        raise
    except ResourceResolverError as e:
        raise _resource_resolver_http_exception(e)
    except Exception as e:
        logger.error(f"Sync video generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate/async", response_model=VideoGenerateAsyncResponse)
async def generate_video_async(
    request_body: VideoGenerateRequest,
    pixelle_video: PixelleVideoDep,
    request: Request
):
    """
    Generate video asynchronously
    
    Creates a background task for video generation.
    Returns immediately with a task_id for tracking progress.
    
    **Workflow:**
    1. Submit video generation request
    2. Receive task_id in response
    3. Poll `/api/tasks/{task_id}` to check status
    4. When status is "completed", retrieve video from result
    
    Request body includes all video generation parameters.
    See VideoGenerateRequest schema for details.
    
    Returns task_id for tracking progress.
    """
    try:
        request_id = new_correlation_id("req")
        logger.bind(
            channel="runtime",
            request_id=request_id,
            content=build_content_observability(request_body.text),
        ).info("async video generation request received")

        resource_resolver = _get_resource_resolver(request, request_body)
        generation_params = build_video_generation_params(
            request_body,
            request_id=request_id,
            resource_resolver=resource_resolver,
        )
        generation_fingerprint = build_generation_fingerprint(
            text=request_body.text,
            pipeline="standard",
            params=generation_params,
        )
        request_params = {
            **generation_params,
            "request_id": request_id,
            "generation_fingerprint": generation_fingerprint,
        }
        outcome = await task_manager.reserve_or_reuse_generation_task(
            task_type=TaskType.VIDEO_GENERATION,
            generation_fingerprint=generation_fingerprint,
            request_params=request_params,
        )
        task = outcome.task
        if not outcome.created:
            logger.info(f"Reusing async video generation task: {task.task_id}")
            message = (
                "Task already completed"
                if outcome.reused_reason == "recent_completed"
                else "Task already running"
            )
            return VideoGenerateAsyncResponse(
                task_id=task.task_id,
                message=message,
            )

        # Define async execution function
        async def execute_video_generation():
            """Execute video generation in background"""
            video_params = {
                **generation_params,
                "api_task_id": task.task_id,
            }
            
            result = await pixelle_video.generate_video(**video_params)
            
            # Get file size
            file_size = os.path.getsize(result.video_path) if os.path.exists(result.video_path) else 0
            
            # Convert path to URL
            video_url = path_to_url(request, result.video_path)
            
            return {
                "video_url": video_url,
                "duration": result.duration,
                "file_size": file_size,
                "storage_key": path_to_storage_key(result.video_path),
            }
        
        if getattr(task_manager, "execution_mode", "embedded") == "embedded":
            await task_manager.execute_task(
                task_id=task.task_id,
                coro_func=execute_video_generation
            )
        
        return VideoGenerateAsyncResponse(
            task_id=task.task_id
        )
        
    except HTTPException:
        raise
    except ResourceResolverError as e:
        raise _resource_resolver_http_exception(e)
    except Exception as e:
        logger.error(f"Async video generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
