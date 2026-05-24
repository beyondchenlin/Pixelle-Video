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
Content generation endpoints

Endpoints for generating narrations, image prompts, and titles.
"""

from fastapi import APIRouter, HTTPException, Request, status
from loguru import logger

from api.dependencies import PixelleVideoDep
from api.llm_trace import build_api_llm_trace_context, build_api_llm_trace_recorder
from api.schemas.content import (
    ImagePromptGenerateRequest,
    ImagePromptGenerateResponse,
    NarrationGenerateRequest,
    NarrationGenerateResponse,
    TitleGenerateRequest,
    TitleGenerateResponse,
    WorldHintDraftGenerateRequest,
    WorldHintDraftGenerateResponse,
)
from pixelle_video.config.storyboard_preset_library import lookup_world_preset
from pixelle_video.models.text_overlay import project_prompt_text_rendering_request
from pixelle_video.services.content_world_hint_draft_builder import build_world_hint_draft
from pixelle_video.services.content_world_planner import ContentWorldPlanner
from pixelle_video.services.image_prompt_composer import ImagePromptComposer
from pixelle_video.services.llm_trace_refs import (
    LLMTraceCollector,
    llm_trace_refs_from_records,
)
from pixelle_video.utils.content_generators import (
    generate_narrations_from_topic,
    generate_styled_image_prompt_batch,
    generate_title,
)
from pixelle_video.utils.prompt_generation_performance import (
    LLM_PROMPT_BATCH_CONCURRENT_LIMIT_PARAM,
    LLM_PROMPT_BATCH_SIZE_PARAM,
)

router = APIRouter(prefix="/content", tags=["Content Generation"])


def _serialize_frame_overrides(frame_overrides):
    if frame_overrides is None:
        return None
    return [override.model_dump(exclude_none=True) for override in frame_overrides]


def _image_prompt_response_provenance(batch) -> dict[str, object]:
    planning_snapshot = dict(batch.planning_snapshot or {})
    prompt_plan_bundle = (
        batch.prompt_plan_bundle.to_dict()
        if batch.prompt_plan_bundle is not None
        else None
    )
    llm_trace_refs = planning_snapshot.get("llm_trace_refs")
    if not isinstance(llm_trace_refs, list):
        llm_trace_refs = []
    if prompt_plan_bundle is not None:
        bundle_refs = prompt_plan_bundle.get("metadata", {}).get("llm_trace_refs", [])
        if isinstance(bundle_refs, list):
            seen = {
                (
                    str(ref.get("trace_id") or ""),
                    str(ref.get("stage") or ""),
                )
                for ref in llm_trace_refs
                if isinstance(ref, dict)
            }
            for ref in bundle_refs:
                if not isinstance(ref, dict):
                    continue
                identity = (
                    str(ref.get("trace_id") or ""),
                    str(ref.get("stage") or ""),
                )
                if identity in seen or not all(identity):
                    continue
                seen.add(identity)
                llm_trace_refs.append(ref)

    return {
        "negative_prompt": batch.negative_prompt,
        "planning_snapshot": planning_snapshot or None,
        "prompt_plan_bundle": prompt_plan_bundle,
        "llm_trace_refs": llm_trace_refs,
    }


@router.post("/world-hint-draft", response_model=WorldHintDraftGenerateResponse)
async def generate_world_hint_draft(
    request: WorldHintDraftGenerateRequest,
    http_request: Request,
    pixelle_video: PixelleVideoDep,
):
    """Generate an editable world-hint draft without triggering the formal generation pipeline."""
    try:
        world_library = pixelle_video.config.get("storyboard_world_preset_library", {})
        world_preset = lookup_world_preset(world_library, request.world_preset_id)
        source_text = (
            f"标题：{request.title}\n正文：{request.source_text}"
            if request.title
            else request.source_text
        )
        trace_recorder = build_api_llm_trace_recorder(
            http_request,
            route="/content/world-hint-draft",
        )
        trace_context = build_api_llm_trace_context(
            http_request,
            route="/content/world-hint-draft",
            operation="api_world_hint_draft",
            stage="api_world_hint_draft",
        )
        profile = await ContentWorldPlanner().plan(
            llm_service=pixelle_video.llm,
            source_text=source_text,
            generation_world_hint=None,
            ip_world_hint=request.ip_default_world_hint,
            world_preset=world_preset,
            trace_context=trace_context,
            trace_recorder=trace_recorder,
        )
        draft = build_world_hint_draft(
            profile,
            prompt_language=request.storyboard_prompt_language,
        )
        return WorldHintDraftGenerateResponse(
            world_hint_draft=draft,
            generation_world_profile=profile.to_dict(),
            hint_source=profile.hint_source.value,
        )
    except ValueError as e:
        error_msg = str(e)
        logger.warning(f"World hint draft validation error: {error_msg}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=error_msg,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"World hint draft generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/narration", response_model=NarrationGenerateResponse)
async def generate_narration(
    request: NarrationGenerateRequest,
    http_request: Request,
    pixelle_video: PixelleVideoDep,
):
    """
    Generate narrations from text
    
    Uses LLM to break down text into multiple narration segments.
    
    - **text**: Source text
    - **n_scenes**: Number of narrations to generate
    - **min_words**: Minimum words per narration
    - **max_words**: Maximum words per narration
    
    Returns list of narration strings.
    """
    try:
        logger.info(f"Generating {request.n_scenes} narrations from text")
        trace_recorder = build_api_llm_trace_recorder(
            http_request,
            route="/content/narration",
        )
        trace_context = build_api_llm_trace_context(
            http_request,
            route="/content/narration",
            operation="api_narration_generation",
            stage="api_narration_generation",
        )
        trace_collector = LLMTraceCollector(trace_recorder)
        
        # Call narration generator utility function
        narrations = await generate_narrations_from_topic(
            llm_service=pixelle_video.llm,
            topic=request.text,
            n_scenes=request.n_scenes,
            min_words=request.min_words,
            max_words=request.max_words,
            trace_context=trace_context,
            trace_recorder=trace_collector,
        )
        
        return NarrationGenerateResponse(
            narrations=narrations,
            llm_trace_refs=llm_trace_refs_from_records(trace_collector.records),
        )
        
    except Exception as e:
        logger.error(f"Narration generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/image-prompt", response_model=ImagePromptGenerateResponse)
async def generate_image_prompt(
    request: ImagePromptGenerateRequest,
    http_request: Request,
    pixelle_video: PixelleVideoDep,
):
    """
    Generate image prompts from narrations
    
    Uses LLM to create detailed image generation prompts.
    
    - **narrations**: List of narration texts
    - **min_words**: Minimum words per prompt
    - **max_words**: Maximum words per prompt
    
    Returns list of image prompts.
    """
    try:
        logger.info(f"Generating image prompts for {len(request.narrations)} narrations")
        trace_recorder = build_api_llm_trace_recorder(
            http_request,
            route="/content/image-prompt",
        )
        trace_context = build_api_llm_trace_context(
            http_request,
            route="/content/image-prompt",
            operation="api_image_prompt_generation",
            stage="api_image_prompt_generation",
        )

        image_config = pixelle_video.config.get("comfyui", {}).get("image", {})
        storyboard_plan = (
            request.storyboard_generation.to_storyboard_plan()
            if request.storyboard_generation is not None
            else None
        )
        text_rendering = (
            project_prompt_text_rendering_request(
                request.text_rendering.model_dump(exclude_none=True)
            )
            if request.text_rendering is not None
            else None
        )
        if storyboard_plan is not None:
            batch = await ImagePromptComposer().compose(
                llm_service=pixelle_video.llm,
                storyboard_plan=storyboard_plan,
                image_config=image_config,
                prompt_prefix=None,
                prompt_language=request.storyboard_prompt_language,
                workflow=None,
                media_service=pixelle_video.media,
                min_words=request.min_words,
                max_words=request.max_words,
                batch_size=getattr(request, LLM_PROMPT_BATCH_SIZE_PARAM),
                max_concurrency=getattr(request, LLM_PROMPT_BATCH_CONCURRENT_LIMIT_PARAM),
                world_preset_id=request.world_preset_id,
                shot_preset_id=request.shot_preset_id,
                consistency_strength=request.consistency_strength or "standard",
                content_mode=request.content_mode,
                role_strategy=request.role_strategy,
                role_locking_strength=request.role_locking_strength,
                shot_strategy=request.shot_strategy,
                frame_overrides=_serialize_frame_overrides(request.frame_overrides),
                text_rendering=text_rendering,
                upstream_llm_trace_refs=request.upstream_llm_trace_refs,
                trace_context=trace_context,
                trace_recorder=trace_recorder,
            )
        else:
            batch = await generate_styled_image_prompt_batch(
                llm_service=pixelle_video.llm,
                narrations=request.narrations,
                image_config=image_config,
                prompt_prefix=None,
                workflow=None,
                media_service=pixelle_video.media,
                min_words=request.min_words,
                max_words=request.max_words,
                batch_size=getattr(request, LLM_PROMPT_BATCH_SIZE_PARAM),
                max_concurrency=getattr(request, LLM_PROMPT_BATCH_CONCURRENT_LIMIT_PARAM),
                prompt_language=request.storyboard_prompt_language,
                world_preset_id=request.world_preset_id,
                shot_preset_id=request.shot_preset_id,
                consistency_strength=request.consistency_strength or "standard",
                content_mode=request.content_mode,
                role_strategy=request.role_strategy,
                role_locking_strength=request.role_locking_strength,
                shot_strategy=request.shot_strategy,
                frame_overrides=_serialize_frame_overrides(request.frame_overrides),
                text_rendering=text_rendering,
                upstream_llm_trace_refs=request.upstream_llm_trace_refs,
                trace_context=trace_context,
                trace_recorder=trace_recorder,
            )

        return ImagePromptGenerateResponse(
            image_prompts=batch.prompts,
            **_image_prompt_response_provenance(batch),
        )

    except ValueError as e:
        # Validation errors from normalize_plan_frame_overrides or other validation
        # These are client errors (4xx), not server errors (5xx)
        error_msg = str(e)
        logger.warning(f"Image prompt validation error: {error_msg}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=error_msg
        )

    except HTTPException:
        # Re-raise HTTPExceptions as-is (e.g., from dependencies)
        raise

    except Exception as e:
        logger.error(f"Image prompt generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/title", response_model=TitleGenerateResponse)
async def generate_title_endpoint(
    request: TitleGenerateRequest,
    http_request: Request,
    pixelle_video: PixelleVideoDep,
):
    """
    Generate video title from text
    
    Uses LLM to create an engaging title.
    
    - **text**: Source text
    - **style**: Optional title style hint
    
    Returns generated title.
    """
    try:
        logger.info("Generating title from text")
        trace_recorder = build_api_llm_trace_recorder(
            http_request,
            route="/content/title",
        )
        trace_context = build_api_llm_trace_context(
            http_request,
            route="/content/title",
            operation="api_title_generation",
            stage="api_title_generation",
        )
        
        # Call title generator utility function
        title = await generate_title(
            llm_service=pixelle_video.llm,
            content=request.text,
            strategy="llm",
            trace_context=trace_context,
            trace_recorder=trace_recorder,
        )
        
        return TitleGenerateResponse(
            title=title
        )
        
    except Exception as e:
        logger.error(f"Title generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
