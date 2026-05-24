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
Image generation endpoints
"""

from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from loguru import logger

from api.dependencies import PixelleVideoDep
from api.schemas.image import ImageGenerateRequest, ImageGenerateResponse
from pixelle_video.services.prompt_trace_artifacts import write_single_media_prompt_artifact
from pixelle_video.utils.os_util import get_runtime_path

router = APIRouter(prefix="/image", tags=["Basic Services"])


@router.post("/generate", response_model=ImageGenerateResponse)
async def image_generate(
    request: ImageGenerateRequest,
    pixelle_video: PixelleVideoDep
):
    """
    Image generation endpoint
    
    Generate image from text prompt using ComfyKit.
    
    - **prompt**: Image description/prompt
    - **width**: Image width (512-2048)
    - **height**: Image height (512-2048)
    - **workflow**: Optional custom workflow filename
    
    Returns path to generated image.
    """
    try:
        logger.info(f"Image generation request: {request.prompt[:50]}...")
        trace_task_id = f"image_generate_{uuid4().hex[:12]}"
        prompt_trace_output_dir = getattr(
            pixelle_video,
            "prompt_trace_output_dir",
            None,
        )
        output_dir = (
            Path(prompt_trace_output_dir) / trace_task_id
            if prompt_trace_output_dir is not None
            else get_runtime_path("media_prompt_traces", trace_task_id)
        )
        prompt_trace_path = write_single_media_prompt_artifact(
            output_dir,
            task_id=trace_task_id,
            prompt=request.prompt,
            generation_context={
                "source": "api.image.generate",
                "workflow": request.workflow,
                "media_type": "image",
                "width": request.width,
                "height": request.height,
            },
        )
        logger.info(f"Image prompt trace artifact written: {prompt_trace_path}")
        
        # Call media service (backward compatible with image API)
        media_result = await pixelle_video.media(
            prompt=request.prompt,
            width=request.width,
            height=request.height,
            workflow=request.workflow
        )
        
        # For backward compatibility, only support image results in /image endpoint
        if media_result.is_video:
            raise HTTPException(
                status_code=400,
                detail="Video workflow used. Please use /media/generate endpoint for video generation."
            )
        
        return ImageGenerateResponse(
            image_path=media_result.url
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Image generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

