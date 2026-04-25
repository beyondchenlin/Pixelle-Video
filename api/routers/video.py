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
)
from api.tasks import TaskType, task_manager
from pixelle_video.services.generation_coordinator import build_generation_fingerprint
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


def _serialize_frame_overrides(frame_overrides):
    if frame_overrides is None:
        return None
    return [override.model_dump(exclude_none=True) for override in frame_overrides]


def _copy_tts_text_policy_params(request_body: VideoGenerateRequest, video_params: dict) -> None:
    for name in TTS_TEXT_POLICY_PARAM_NAMES:
        value = getattr(request_body, name)
        if value is not None:
            video_params[name] = value


def resolve_video_media_size(frame_template: str | None) -> tuple[int, int]:
    """Resolve video dimensions from the selected frame template."""
    if not frame_template:
        raise ValueError("frame_template is required to determine media size")

    from pixelle_video.services.frame_html import HTMLFrameGenerator
    from pixelle_video.utils.template_util import resolve_template_path

    template_path = resolve_template_path(frame_template)
    generator = HTMLFrameGenerator(template_path)
    media_width, media_height = generator.get_media_size()
    logger.debug(f"Auto-determined media size from template: {media_width}x{media_height}")
    return media_width, media_height


def build_video_generation_params(
    request_body: VideoGenerateRequest,
    *,
    request_id: str,
    media_width: int,
    media_height: int,
    api_task_id: str | None = None,
) -> dict:
    """Build PixelleVideoCore.generate_video kwargs from an API request."""
    video_params = {
        "text": request_body.text,
        "mode": request_body.mode,
        "title": request_body.title,
        "n_scenes": request_body.n_scenes,
        "min_narration_words": request_body.min_narration_words,
        "max_narration_words": request_body.max_narration_words,
        "min_image_prompt_words": request_body.min_image_prompt_words,
        "max_image_prompt_words": request_body.max_image_prompt_words,
        "media_width": media_width,
        "media_height": media_height,
        "media_workflow": request_body.media_workflow,
        "video_fps": request_body.video_fps,
        "frame_template": request_body.frame_template,
        "prompt_prefix": request_body.prompt_prefix,
        "world_preset_id": request_body.world_preset_id,
        "shot_preset_id": request_body.shot_preset_id,
        "consistency_strength": request_body.consistency_strength or "standard",
        "content_mode": request_body.content_mode,
        "role_strategy": request_body.role_strategy,
        "role_locking_strength": request_body.role_locking_strength,
        "shot_strategy": request_body.shot_strategy,
        "frame_overrides": _serialize_frame_overrides(request_body.frame_overrides),
        "bgm_path": request_body.bgm_path,
        "bgm_volume": request_body.bgm_volume,
        "request_id": request_id,
    }

    if api_task_id is not None:
        video_params["api_task_id"] = api_task_id

    if request_body.tts_workflow:
        video_params["tts_workflow"] = request_body.tts_workflow

    if request_body.ref_audio:
        video_params["ref_audio"] = request_body.ref_audio

    if request_body.voice_id:
        logger.warning("voice_id parameter is deprecated, please use tts_workflow instead")
        video_params["voice_id"] = request_body.voice_id

    if request_body.template_params:
        video_params["template_params"] = request_body.template_params

    if request_body.render_backend is not None:
        video_params["render_backend"] = request_body.render_backend

    if request_body.text_rendering is not None:
        video_params["text_rendering"] = request_body.text_rendering.model_dump()

    _copy_tts_text_policy_params(request_body, video_params)
    copy_prompt_generation_performance_params(request_body, video_params)
    return video_params


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
        
        media_width, media_height = resolve_video_media_size(request_body.frame_template)
        video_params = build_video_generation_params(
            request_body,
            request_id=request_id,
            media_width=media_width,
            media_height=media_height,
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

        generation_fingerprint = build_generation_fingerprint(
            text=request_body.text,
            pipeline="standard",
            params=request_body.model_dump(exclude_none=True),
        )
        request_params = {
            **request_body.model_dump(),
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
            media_width, media_height = resolve_video_media_size(request_body.frame_template)
            video_params = build_video_generation_params(
                request_body,
                request_id=request_id,
                media_width=media_width,
                media_height=media_height,
                api_task_id=task.task_id,
            )
            
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
        
    except Exception as e:
        logger.error(f"Async video generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
