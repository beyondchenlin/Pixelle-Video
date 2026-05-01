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
Standard Video Generation Pipeline

Standard workflow for generating short videos from topic or fixed script.
This is the default pipeline for general-purpose video generation.
Refactored to use LinearVideoPipeline (Template Method Pattern).
"""

import asyncio
import inspect
import json
import os
import shutil
import subprocess
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, List, Literal, Mapping, Optional

from loguru import logger

from pixelle_video.config.tts_defaults import resolve_tts_inference_mode
from pixelle_video.config.workflow_defaults import infer_workflow_domain
from pixelle_video.models.caption_speech_plan import build_caption_speech_plan
from pixelle_video.models.creation_package import CreationPackage
from pixelle_video.models.progress import (
    ProgressEvent,
    ProgressEventType,
    ProgressFrameAction,
    ProgressI18nMessage,
)
from pixelle_video.models.prompt_plan import PromptPlan
from pixelle_video.models.render_execution_plan import (
    RenderExecutionArtifact,
    RenderExecutionPlan,
)
from pixelle_video.models.render_package import (
    CaptionCue,
    RenderAudioTrack,
    RenderManifest,
    TextCue,
    TextTrack,
    VisualClip,
)
from pixelle_video.models.size_contract import (
    GenerationSizeContract,
    orientation_from_dimensions,
)
from pixelle_video.models.storyboard import (
    Storyboard,
    StoryboardConfig,
    StoryboardFrame,
    VideoGenerationResult,
    build_storyboard_config_planning_kwargs,
    build_storyboard_frame_planning_kwargs,
)
from pixelle_video.models.text_overlay import project_prompt_text_rendering_request
from pixelle_video.models.text_style import DEFAULT_TITLE_STYLE_ID
from pixelle_video.models.video_generation_contract import StoryboardControlsContract
from pixelle_video.pipelines.linear import LinearVideoPipeline, PipelineContext
from pixelle_video.pipelines.storyboard_config import resolve_storyboard_render_kwargs
from pixelle_video.prompt_language import DEFAULT_PROMPT_LANGUAGE
from pixelle_video.render_backend import (
    FFMPEG_MANIFEST_RENDER_BACKEND,
    HYPERFRAMES_COMPILED_RENDER_BACKEND,
    LEGACY_RENDER_BACKEND,
)
from pixelle_video.services.ass_text_adapter import AssTextAdapter
from pixelle_video.services.caption_cue_builder import build_caption_cues_from_sentences
from pixelle_video.services.frame_timing_allocator import allocate_frame_timing_windows
from pixelle_video.services.image_prompt_composer import ImagePromptComposer
from pixelle_video.services.native_prompt_projection import NativePromptProjection
from pixelle_video.services.render_capability_resolver import (
    RenderCapabilityInput,
    RenderCapabilityResolver,
    RenderCapabilityResult,
)
from pixelle_video.services.script_generation import ScriptGenerationService
from pixelle_video.services.storyboard_generation import StoryboardGenerationService
from pixelle_video.services.storyboard_workbench_artifact_bridge import (
    StoryboardWorkbenchArtifactBridge,
)
from pixelle_video.services.text_cue_compiler import TextCueCompiler
from pixelle_video.services.text_rendering_contract_summary import (
    TEXT_RENDER_PACKAGE_ARTIFACT_PATH,
    build_text_rendering_result_metadata,
)
from pixelle_video.services.text_rendering_orchestrator import TextRenderingOrchestrator
from pixelle_video.services.timing_planner import TimingPlanner
from pixelle_video.services.tts_segmentation import build_external_tts_segmentation_plan
from pixelle_video.services.video import VideoService
from pixelle_video.tts_audio_strategy import (
    AUTO_TTS_AUDIO_STRATEGY,
    MASTER_TRACK_TTS_AUDIO_STRATEGY,
    PER_FRAME_TTS_AUDIO_STRATEGY,
    SUPPORTED_STANDARD_TTS_AUDIO_STRATEGIES,
)
from pixelle_video.tts_split_strategy import INTERNAL_ONLY_TTS_SPLIT_MODE
from pixelle_video.tts_workflow_contract import (
    is_index_tts2_workflow_key,
    resolve_workflow_output_audio_extension_from_info,
    resolve_workflow_output_audio_extension_from_key,
)
from pixelle_video.utils.content_generators import (
    generate_title,
)
from pixelle_video.utils.logging_util import (
    attach_task_log_sinks,
    build_content_observability,
    emit_stage_event,
)
from pixelle_video.utils.os_util import (
    create_task_output_dir,
    get_task_final_video_path,
    get_task_frame_path,
    get_task_path,
    get_temp_path,
)
from pixelle_video.utils.prompt_generation_performance import (
    LLM_PROMPT_BATCH_CONCURRENT_LIMIT_PARAM,
    LLM_PROMPT_BATCH_SIZE_PARAM,
)
from pixelle_video.utils.template_util import (
    get_template_orientation,
    get_template_type,
    parse_template_size,
    resolve_default_template_for_type_and_orientation,
    resolve_template_path,
    validate_template_canvas_orientation,
)
from pixelle_video.utils.workflow_capabilities import (
    WorkflowCapabilities,
    get_workflow_capabilities,
)

LocalMediaSessionPolicy = Literal["none", "batch", "per_frame"]


@dataclass(frozen=True)
class AssetExecutionMode:
    template_type: Literal["static", "image", "video"]
    tts_workflow_key: Optional[str]
    media_workflow_key: Optional[str]
    media_domain: Literal["static", "image", "video"]
    is_runninghub: bool
    use_runninghub_parallel: bool
    use_staged_mode: bool
    local_media_session_policy: LocalMediaSessionPolicy = "none"


@asynccontextmanager
async def _maybe_local_comfyui_workflow_session(
    core: Any,
    *,
    release_after_session: bool = False,
):
    session_factory = getattr(core, "local_comfyui_workflow_session", None)
    if callable(session_factory):
        try:
            signature = inspect.signature(session_factory)
        except (TypeError, ValueError):
            supports_release_after_session = True
        else:
            supports_release_after_session = (
                "release_after_session" in signature.parameters
                or any(
                    parameter.kind == inspect.Parameter.VAR_KEYWORD
                    for parameter in signature.parameters.values()
                )
            )

        session_context = (
            session_factory(release_after_session=release_after_session)
            if supports_release_after_session
            else session_factory()
        )
        async with session_context:
            yield
        return

    yield


def _resolve_frame_template_for_size_contract(
    params: Mapping[str, Any],
    size_contract: GenerationSizeContract,
) -> str:
    canvas_orientation = orientation_from_dimensions(
        size_contract.canvas_width,
        size_contract.canvas_height,
    )
    frame_template = params.get("frame_template")
    if frame_template:
        resolved_template = resolve_template_path(str(frame_template))
        validate_template_canvas_orientation(resolved_template, canvas_orientation)
        return str(frame_template)

    return resolve_default_template_for_type_and_orientation(
        "image",
        canvas_orientation,
    )


def _has_explicit_canvas_size_intent(params: Mapping[str, Any]) -> bool:
    if bool(params.get("sync_media_size_to_canvas", False)):
        return True
    return any(
        key in params and params.get(key) is not None
        for key in (
            "canvas_width",
            "canvas_height",
            "video_orientation",
            "video_resolution_preset",
        )
    )


def _size_params_with_template_defaults(params: Mapping[str, Any]) -> dict[str, Any]:
    size_params = dict(params)
    frame_template = size_params.get("frame_template")
    if not frame_template:
        return size_params
    if _has_explicit_canvas_size_intent(size_params):
        return size_params

    resolved_template = resolve_template_path(str(frame_template))
    size_params["video_orientation"] = get_template_orientation(resolved_template)
    return size_params




class StandardPipeline(LinearVideoPipeline):
    """
    Standard video generation pipeline
    
    Workflow:
    1. Generate/determine title
    2. Generate narrations (from topic or split fixed script)
    3. Generate image prompts for each narration
    4. For each frame:
       - Generate audio (TTS)
       - Generate image
       - Compose frame with template
       - Create video segment
    5. Concatenate all segments
    6. Add BGM (optional)
    
    Supports two modes:
    - "generate": LLM generates narrations from topic
    - "fixed": Use provided script as-is (each line = one narration)
    """
    
    # ==================== Lifecycle Methods ====================

    async def setup_environment(self, ctx: PipelineContext):
        """Step 1: Setup task directory and environment."""
        text = ctx.input_text
        mode = ctx.params.get("mode", "generate")
        
        logger.info(f"🚀 Starting StandardPipeline in '{mode}' mode")
        logger.info(f"   Text length: {len(text)} chars")
        
        # Create isolated task directory
        task_dir, task_id = create_task_output_dir()
        ctx.task_id = task_id
        ctx.task_dir = task_dir
        ctx.observability.update(
            {
                "version": "v1",
                "request_id": ctx.request_id,
                "session_id": ctx.session_id,
                "api_task_id": ctx.api_task_id,
                "task_id": task_id,
                "runtime_log_path": str(self.core.persistence.get_task_runtime_log_path(task_id)),
                "ai_creation_log_path": str(self.core.persistence.get_task_ai_creation_log_path(task_id)),
            }
        )
        ctx.task_log_session = attach_task_log_sinks(task_id=task_id, task_dir=Path(task_dir))
        logger.bind(
            channel="runtime",
            event="bind_task_context",
            request_id=ctx.request_id,
            session_id=ctx.session_id,
            api_task_id=ctx.api_task_id,
            task_id=task_id,
            pipeline="standard",
        ).info("task log context bound")
        
        logger.info(f"📁 Task directory created: {task_dir}")
        logger.info(f"   Task ID: {task_id}")
        
        # Determine final video path
        output_path = ctx.params.get("output_path")
        if output_path is None:
            ctx.final_video_path = get_task_final_video_path(task_id)
        else:
            # We will copy to this path in finalize/post_production
            # For internal processing, we still use the task dir path? 
            # Actually StandardPipeline logic used get_task_final_video_path as the target for concat
            # and then copied. Let's stick to that.
            ctx.final_video_path = get_task_final_video_path(task_id)
            logger.info(f"   Will copy final video to: {output_path}")

    async def generate_content(self, ctx: PipelineContext):
        """Step 2: Generate or process script/narrations."""
        mode = ctx.params.get("mode", "generate")
        text = ctx.input_text
        storyboard_contract = StoryboardControlsContract.from_mapping(
            ctx.params,
            default_prompt_language=DEFAULT_PROMPT_LANGUAGE,
        )
        requested_scene_count = storyboard_contract.storyboard_scene_count
        stage_callback = self._ai_stage_callback(ctx)

        summary = ctx.observability.setdefault("ai_creation", {})
        if not summary.get("request_received"):
            summary["request_received"] = True
            emit_stage_event(
                channel="ai_creation",
                stage="request_received",
                event="end",
                message="ai creation request received",
                callback=stage_callback,
                status="success",
                latency_ms=0,
                llm_call_count=0,
                retry_count=0,
                narration_count=requested_scene_count,
                pipeline="standard",
                workflow=ctx.params.get("media_workflow"),
                template=ctx.params.get("frame_template"),
            )
        
        if mode == "generate":
            self._report_progress(ctx.progress_callback, ProgressEventType.GENERATING_SOURCE_TEXT, 0.05)
            ctx.source_text = await ScriptGenerationService().generate(
                llm_service=self.llm,
                topic=text,
                script_length_mode=ctx.params.get("script_length_mode", "auto"),
                script_target_words=ctx.params.get("script_target_words"),
            )
            logger.info("✅ Generated complete source text for storyboard planning")
        else:  # fixed
            self._report_progress(ctx.progress_callback, ProgressEventType.PREPARING_SOURCE_TEXT, 0.05)
            ctx.source_text = text.strip()
            logger.info("✅ Prepared fixed source text for storyboard planning")

        self._report_progress(ctx.progress_callback, ProgressEventType.GENERATING_STORYBOARD_PLAN, 0.08)
        ctx.storyboard_plan = await StoryboardGenerationService(
            config=self.core.config,
        ).generate(
            llm_service=self.llm,
            source_text=ctx.source_text,
            storyboard_mode=storyboard_contract.storyboard_mode,
            storyboard_count_mode=storyboard_contract.storyboard_count_mode,
            storyboard_scene_count=storyboard_contract.storyboard_scene_count,
            storyboard_max_scene_count=storyboard_contract.storyboard_max_scene_count,
            prompt_language=storyboard_contract.storyboard_prompt_language,
        )
        ctx.source_text = ctx.storyboard_plan.source_text
        ctx.caption_speech_plan = build_caption_speech_plan(
            ctx.storyboard_plan.source_text,
            storyboard_plan=ctx.storyboard_plan,
            punctuation_mode=ctx.params.get("caption_punctuation_mode", "strip_all"),
        )
        logger.info(
            "✅ Generated storyboard plan with "
            f"{ctx.storyboard_plan.resolved_scene_count} frames and "
            f"{len(ctx.caption_speech_plan.units)} caption speech units"
        )

    async def determine_title(self, ctx: PipelineContext):
        """Step 3: Determine or generate video title."""
        # Note: Swapped order with generate_content in base class call, 
        # but in StandardPipeline original code, title was determined BEFORE narrations.
        # However, LinearVideoPipeline defines generate_content BEFORE determine_title.
        # This is fine as they are independent in StandardPipeline logic.
        
        title = ctx.params.get("title")
        mode = ctx.params.get("mode", "generate")
        text = ctx.input_text
        stage_callback = self._ai_stage_callback(ctx)
        
        if title:
            ctx.title = title
            emit_stage_event(
                channel="ai_creation",
                stage="title_generation",
                event="skip",
                message="title generation skipped",
                callback=stage_callback,
                status="skipped",
                latency_ms=0,
                llm_call_count=0,
                retry_count=0,
                reason="user supplied title",
            )
            logger.info(f"   Title: '{title}' (user-specified)")
        else:
            self._report_progress(ctx.progress_callback, ProgressEventType.GENERATING_TITLE, 0.10)
            if mode == "generate":
                ctx.title = await generate_title(
                    self.llm,
                    text,
                    strategy="auto",
                    stage_callback=stage_callback,
                )
                logger.info(f"   Title: '{ctx.title}' (auto-generated)")
            else:  # fixed
                ctx.title = await generate_title(
                    self.llm,
                    text,
                    strategy="llm",
                    stage_callback=stage_callback,
                )
                logger.info(f"   Title: '{ctx.title}' (LLM-generated)")

    async def plan_visuals(self, ctx: PipelineContext):
        """Step 4: Generate image prompts or visual descriptions."""
        storyboard_contract = StoryboardControlsContract.from_mapping(
            ctx.params,
            default_prompt_language=DEFAULT_PROMPT_LANGUAGE,
        )
        # Detect template type to determine if media generation is needed
        size_contract = GenerationSizeContract.from_params(
            _size_params_with_template_defaults(ctx.params)
        )
        frame_template = _resolve_frame_template_for_size_contract(ctx.params, size_contract)
        
        template_name = Path(frame_template).name
        template_type = get_template_type(template_name)
        template_requires_media = (template_type in ["image", "video"])
        stage_callback = self._ai_stage_callback(ctx)
        text_rendering_result = self._get_text_rendering_result(ctx)
        
        if template_type == "image":
            logger.info("📸 Template requires image generation")
        elif template_type == "video":
            logger.info("🎬 Template requires video generation")
        else:  # static
            logger.info("⚡ Static template - skipping media generation pipeline")
            logger.info("   💡 Benefits: Faster generation + Lower cost + No ComfyUI dependency")
        
        # Only generate image prompts if template requires media
        if template_requires_media:
            self._report_progress(ctx.progress_callback, ProgressEventType.GENERATING_IMAGE_PROMPTS, 0.15)
            
            prompt_prefix = ctx.params.get("prompt_prefix")
            min_words = ctx.params.get("min_image_prompt_words", 30)
            max_words = ctx.params.get("max_image_prompt_words", 60)
            media_type = "video" if template_type == "video" else "image"
            
            if prompt_prefix is not None:
                logger.bind(
                    channel="runtime",
                    prompt_prefix=build_content_observability(prompt_prefix),
                ).info("custom prompt prefix received")

            # Create progress callback wrapper for image prompt generation
            def image_prompt_progress(
                completed: int,
                total: int,
                message: ProgressI18nMessage,
            ):
                batch_progress = completed / total if total > 0 else 0
                overall_progress = 0.15 + (batch_progress * 0.15)
                self._report_progress(
                    ctx.progress_callback,
                    ProgressEventType.GENERATING_IMAGE_PROMPTS,
                    overall_progress,
                    extra_info=message
                )
            
            image_config = self.core.config.get("comfyui", {}).get(media_type, {})
            native_hints = NativePromptProjection().project(
                plan=text_rendering_result.overlay_plan,
                policy=text_rendering_result.overlay_policy,
            )
            if ctx.storyboard_plan is None:
                raise ValueError("storyboard_plan must be generated before visual planning")

            styled_batch = await ImagePromptComposer().compose(
                llm_service=self.llm,
                storyboard_plan=ctx.storyboard_plan,
                image_config=image_config,
                prompt_language=storyboard_contract.storyboard_prompt_language,
                prompt_prefix=prompt_prefix,
                workflow=ctx.params.get("media_workflow"),
                media_service=self.core.media,
                media_type=media_type,
                min_words=min_words,
                max_words=max_words,
                batch_size=ctx.params.get(LLM_PROMPT_BATCH_SIZE_PARAM),
                max_concurrency=ctx.params.get(LLM_PROMPT_BATCH_CONCURRENT_LIMIT_PARAM),
                progress_callback=image_prompt_progress,
                world_preset_id=storyboard_contract.world_preset_id,
                shot_preset_id=storyboard_contract.shot_preset_id,
                consistency_strength=storyboard_contract.consistency_strength or "standard",
                content_mode=storyboard_contract.content_mode,
                role_strategy=storyboard_contract.role_strategy,
                role_locking_strength=storyboard_contract.role_locking_strength,
                shot_strategy=storyboard_contract.shot_strategy,
                frame_overrides=list(storyboard_contract.frame_overrides),
                text_rendering=self._prompt_text_rendering_request(ctx),
                native_prompt_hints_by_frame=native_hints,
                stage_callback=stage_callback,
            )

            ctx.image_prompts = styled_batch.prompts
            ctx.resolved_style = styled_batch.resolved_style
            ctx.media_negative_prompt = styled_batch.negative_prompt
            ctx.planning_snapshot = dict(styled_batch.planning_snapshot or {}) or None
            await self._persist_prompt_plan_bundle(ctx)
            
            logger.info(f"✅ Generated {len(ctx.image_prompts)} image prompts")
        else:
            # Static template - skip image prompt generation entirely
            frame_count = ctx.storyboard_plan.resolved_scene_count if ctx.storyboard_plan else 0
            ctx.image_prompts = [None] * frame_count
            ctx.resolved_style = None
            ctx.media_negative_prompt = None
            ctx.planning_snapshot = (
                {"storyboard_generation": ctx.storyboard_plan.to_dict()}
                if ctx.storyboard_plan is not None
                else None
            )
            emit_stage_event(
                channel="ai_creation",
                stage="image_prompt_batch",
                event="skip",
                message="image prompt batch skipped",
                callback=stage_callback,
                status="skipped",
                latency_ms=0,
                llm_call_count=0,
                retry_count=0,
                narration_count=frame_count,
                reason="static template",
            )
            logger.info("⚡ Skipped image prompt generation (static template)")
            logger.info(f"   💡 Savings: {frame_count} LLM calls + {frame_count} media generations")

        self._emit_ai_creation_total(ctx, status="success")

    async def initialize_storyboard(self, ctx: PipelineContext):
        """Step 5: Create Storyboard object and frames."""
        # === Handle TTS parameter compatibility ===
        tts_inference_mode = ctx.params.get("tts_inference_mode")
        tts_voice = ctx.params.get("tts_voice")
        voice_id = ctx.params.get("voice_id")
        tts_workflow = ctx.params.get("tts_workflow")
        requested_tts_inference_mode = tts_inference_mode
        if not requested_tts_inference_mode and (voice_id or tts_voice) and not tts_workflow:
            requested_tts_inference_mode = "local"
        resolved_tts_inference_mode = resolve_tts_inference_mode(
            self.core.config,
            requested_tts_inference_mode,
        )
        
        final_voice_id = None
        final_tts_workflow = tts_workflow
        
        if resolved_tts_inference_mode == "local":
            final_voice_id = tts_voice or voice_id or "zh-CN-YunjianNeural"
            final_tts_workflow = None
            logger.debug(f"TTS Mode: local (voice={final_voice_id})")
        elif resolved_tts_inference_mode == "comfyui":
            final_voice_id = None
            logger.debug(f"TTS Mode: comfyui (workflow={final_tts_workflow})")
            
        if ctx.storyboard_plan is None:
            raise ValueError("storyboard_plan must be generated before storyboard initialization")
        if ctx.caption_speech_plan is None:
            ctx.caption_speech_plan = build_caption_speech_plan(
                ctx.storyboard_plan.source_text,
                storyboard_plan=ctx.storyboard_plan,
                punctuation_mode=ctx.params.get("caption_punctuation_mode", "strip_all"),
            )

        frame_count = ctx.storyboard_plan.resolved_scene_count
        size_contract = GenerationSizeContract.from_params(
            _size_params_with_template_defaults(ctx.params)
        )
        frame_template = _resolve_frame_template_for_size_contract(ctx.params, size_contract)
        template_type = get_template_type(Path(frame_template).name)
        planning_params = ctx.params if template_type in {"image", "video"} else {}

        # Create config
        ctx.config = StoryboardConfig(
            task_id=ctx.task_id,
            n_storyboard=frame_count,
            min_narration_words=ctx.params.get("min_narration_words", 5),
            max_narration_words=ctx.params.get("max_narration_words", 20),
            min_image_prompt_words=ctx.params.get("min_image_prompt_words", 30),
            max_image_prompt_words=ctx.params.get("max_image_prompt_words", 60),
            video_fps=ctx.params.get("video_fps", 30),
            tts_inference_mode=resolved_tts_inference_mode,
            voice_id=final_voice_id,
            tts_workflow=final_tts_workflow,
            tts_speed=ctx.params.get("tts_speed", 1.2),
            ref_audio=ctx.params.get("ref_audio"),
            ref_audio_text=ctx.params.get("ref_audio_text") or ctx.params.get("prompt_text"),
            **resolve_storyboard_render_kwargs(self.core.config, ctx.params),
            canvas_width=size_contract.canvas_width,
            canvas_height=size_contract.canvas_height,
            media_width=size_contract.media_width,
            media_height=size_contract.media_height,
            video_orientation=size_contract.video_orientation,
            video_resolution_preset=size_contract.video_resolution_preset,
            media_orientation=size_contract.media_orientation,
            media_resolution_preset=size_contract.media_resolution_preset,
            sync_media_size_to_canvas=size_contract.sync_media_size_to_canvas,
            media_placement=ctx.params.get("media_placement"),
            media_workflow=ctx.params.get("media_workflow"),
            media_negative_prompt=ctx.media_negative_prompt,
            frame_template=frame_template,
            template_params=ctx.params.get("template_params"),
            **build_storyboard_config_planning_kwargs(ctx.planning_snapshot, planning_params),
        )
        
        # Create storyboard
        ctx.storyboard = Storyboard(
            title=ctx.title,
            config=ctx.config,
            content_metadata=ctx.params.get("content_metadata"),
            created_at=datetime.now(),
            planning_snapshot=dict(ctx.planning_snapshot or {}) or None,
        )
        
        # Create frames
        for i, (plan_frame, image_prompt) in enumerate(zip(ctx.storyboard_plan.frames, ctx.image_prompts)):
            frame = StoryboardFrame(
                index=i,
                narration=plan_frame.source_text,
                image_prompt=image_prompt,
                created_at=datetime.now(),
                **build_storyboard_frame_planning_kwargs(ctx.planning_snapshot, i),
            )
            ctx.storyboard.frames.append(frame)

        effective_max_sentences, effective_max_chars, normalize_block_text_for_tts, single_audio_block = (
            self._resolve_effective_timing_plan_settings(ctx.config)
        )
        planner = TimingPlanner(
            mode=ctx.config.tts_batching_mode,
            max_sentences=effective_max_sentences,
            max_chars=effective_max_chars,
            normalize_block_text_for_tts=normalize_block_text_for_tts,
            single_audio_block=single_audio_block,
            tts_sentence_joiner_mode=ctx.config.tts_sentence_joiner_mode,
        )
        ctx.timing_plan = planner.build_from_caption_speech_plan(ctx.caption_speech_plan)
        logger.info(
            "Timing plan prepared: "
            f"{len(ctx.timing_plan.sentences)} sentence units -> {len(ctx.timing_plan.blocks)} audio blocks"
        )
        self._record_tts_text_flow(ctx)
        if (
            ctx.creation_package is not None
            and ctx.creation_package.text_overlay_plan is not None
            and ctx.task_dir
        ):
            text_plan_path = Path(ctx.task_dir) / "text_overlay_plan.json"
            text_plan_path.write_text(
                json.dumps(
                    ctx.creation_package.text_overlay_plan.to_dict(),
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

    def _ai_stage_callback(self, ctx: PipelineContext):
        return lambda payload: self._record_ai_creation_stage(ctx, payload)

    def _record_tts_text_flow(self, ctx: PipelineContext) -> None:
        timing_plan = ctx.timing_plan
        config = ctx.config
        if timing_plan is None or config is None:
            return

        ctx.observability["tts_text_flow"] = {
            "version": "v1",
            "preserve_natural_punctuation": bool(config.preserve_natural_punctuation),
            "tts_sentence_joiner_mode": config.tts_sentence_joiner_mode,
            "caption_punctuation_mode": config.caption_punctuation_mode,
            "tts_split_mode": config.tts_split_mode,
            "source_frames": [
                {
                    "frame_index": frame.index,
                    "source_text": frame.narration,
                }
                for frame in ctx.storyboard.frames
            ],
            "caption_speech_units": [
                unit.to_dict()
                for unit in (ctx.caption_speech_plan.units if ctx.caption_speech_plan else ())
            ],
            "sentence_units": [
                {
                    "id": sentence.id,
                    "speech_text": sentence.text,
                    "frame_indices": list(sentence.frame_indices),
                    "block_id": sentence.block_id,
                }
                for sentence in timing_plan.sentences
            ],
            "audio_blocks": [
                {
                    "id": block.id,
                    "speech_text": block.text,
                    "source_frame_indices": list(block.source_frame_indices),
                }
                for block in timing_plan.blocks
            ],
        }

    def _record_ai_creation_stage(self, ctx: PipelineContext, event: dict[str, Any]) -> None:
        if event.get("channel") != "ai_creation" or event.get("event") not in {"end", "skip", "fail"}:
            return

        summary = ctx.observability.setdefault("ai_creation", {})
        summary.setdefault("total_latency_ms", 0)
        summary.setdefault("llm_call_count", 0)
        summary.setdefault("slowest_stage", None)
        summary.setdefault("stages", [])

        if event.get("stage") == "ai_creation_total":
            summary["status"] = event.get("status", "success")
            summary["total_elapsed_ms"] = event.get("latency_ms", summary["total_latency_ms"])
            return

        stage_entry = {
            "stage": event["stage"],
            "status": event.get("status", "success"),
            "latency_ms": event.get("latency_ms", 0),
            "llm_call_count": event.get("llm_call_count", 0),
            "retry_count": event.get("retry_count", 0),
        }
        for optional_key in ("batch_total", "narration_count", "reason"):
            if event.get(optional_key) is not None:
                stage_entry[optional_key] = event[optional_key]

        summary["stages"].append(stage_entry)
        summary["total_latency_ms"] = sum(item.get("latency_ms", 0) for item in summary["stages"])
        summary["llm_call_count"] = sum(item.get("llm_call_count", 0) for item in summary["stages"])
        summary["slowest_stage"] = max(
            summary["stages"],
            key=lambda item: item.get("latency_ms", 0),
        )["stage"]
        if event.get("status") == "failed":
            summary["status"] = "failed"
        else:
            summary.setdefault("status", "success")

    def _emit_ai_creation_total(self, ctx: PipelineContext, *, status: str) -> None:
        summary = ctx.observability.get("ai_creation", {})
        emit_stage_event(
            channel="ai_creation",
            stage="ai_creation_total",
            event="end" if status != "failed" else "fail",
            message="ai creation total recorded",
            callback=self._ai_stage_callback(ctx),
            status=status,
            latency_ms=summary.get("total_latency_ms", 0),
            llm_call_count=summary.get("llm_call_count", 0),
            retry_count=sum(item.get("retry_count", 0) for item in summary.get("stages", [])),
        )

    def _resolve_media_domain(
        self,
        config: StoryboardConfig,
    ) -> Literal["static", "image", "video"]:
        template_type = get_template_type(Path(config.frame_template).name)
        if template_type == "static":
            return "static"

        configured_domain = infer_workflow_domain(config.media_workflow)
        if configured_domain == "video":
            return "video"
        if configured_domain == "image":
            return "image"

        return template_type

    def _resolve_asset_execution_mode(self, ctx: PipelineContext) -> AssetExecutionMode:
        config = ctx.config
        template_type = get_template_type(Path(config.frame_template).name)
        media_domain = self._resolve_media_domain(config)
        core = getattr(self, "core", None)

        tts_workflow_key = None
        if config.tts_inference_mode == "comfyui":
            tts_resolver = getattr(getattr(core, "tts", None), "_resolve_workflow", None)
            if callable(tts_resolver):
                tts_workflow_key = tts_resolver(
                    workflow=config.tts_workflow,
                )["key"]
            else:
                tts_workflow_key = config.tts_workflow

        media_workflow_key = None
        media_capabilities = WorkflowCapabilities()
        if media_domain != "static":
            media_resolver = getattr(getattr(core, "media", None), "_resolve_workflow", None)
            if callable(media_resolver):
                media_workflow_info = media_resolver(
                    workflow=config.media_workflow,
                    workflow_domain=media_domain,
                )
                media_workflow_key = media_workflow_info["key"]
                media_capabilities = self._resolve_workflow_capabilities_for_execution(
                    media_workflow_info
                )
            else:
                media_workflow_key = config.media_workflow

        is_runninghub = any(
            key and key.startswith("runninghub/")
            for key in (tts_workflow_key, media_workflow_key)
        )
        has_selfhost_workflow = any(
            key and key.startswith("selfhost/")
            for key in (tts_workflow_key, media_workflow_key)
        )
        use_runninghub_parallel = is_runninghub and not has_selfhost_workflow
        use_staged_mode = (
            template_type == "image"
            and media_domain == "image"
            and bool(media_workflow_key and media_workflow_key.startswith("selfhost/"))
        )
        local_media_session_policy: LocalMediaSessionPolicy = "none"
        if use_staged_mode:
            local_media_session_policy = (
                "per_frame"
                if media_capabilities.prefers_isolated_local_execution
                else "batch"
            )

        return AssetExecutionMode(
            template_type=template_type,
            tts_workflow_key=tts_workflow_key,
            media_workflow_key=media_workflow_key,
            media_domain=media_domain,
            is_runninghub=is_runninghub,
            use_runninghub_parallel=use_runninghub_parallel,
            use_staged_mode=use_staged_mode,
            local_media_session_policy=local_media_session_policy,
        )

    def _resolve_workflow_capabilities_for_execution(
        self,
        workflow_info: Mapping[str, Any],
    ) -> WorkflowCapabilities:
        try:
            return get_workflow_capabilities(dict(workflow_info))
        except Exception as exc:
            logger.warning(
                "Workflow capability inspection failed for "
                f"{workflow_info.get('key')!r}; using conservative local execution: {exc}"
            )
            if str(workflow_info.get("source") or "").lower() == "selfhost":
                return WorkflowCapabilities(
                    local_memory_profile="high",
                    prefers_isolated_local_execution=True,
                )
            return WorkflowCapabilities()

    def _resolve_hyperframes_template_id(self, config: StoryboardConfig) -> str:
        template_id = Path(config.frame_template).stem
        if template_id == "default":
            return "image_default"
        return template_id

    @staticmethod
    def _resolve_storyboard_canvas_size(config: StoryboardConfig) -> tuple[int, int]:
        canvas_width = getattr(config, "canvas_width", None)
        canvas_height = getattr(config, "canvas_height", None)
        if canvas_width is not None and canvas_height is not None:
            return int(canvas_width), int(canvas_height)
        return int(config.media_width), int(config.media_height)

    def _resolve_hyperframes_canvas_size(
        self,
        config: StoryboardConfig,
    ) -> tuple[int, int]:
        canvas_width = getattr(config, "canvas_width", None)
        canvas_height = getattr(config, "canvas_height", None)
        if canvas_width is not None and canvas_height is not None:
            return int(canvas_width), int(canvas_height)

        try:
            return parse_template_size(config.frame_template)
        except ValueError as exc:
            logger.warning(
                "Failed to parse HyperFrames canvas size from template "
                f"{config.frame_template!r}: {exc}. Falling back to media size."
            )
            return int(config.media_width), int(config.media_height)

    def _get_hyperframes_fallback_reason(self, ctx: PipelineContext) -> Optional[str]:
        if ctx.config.render_backend != HYPERFRAMES_COMPILED_RENDER_BACKEND:
            return None
        return self._get_hyperframes_template_unavailable_reason(ctx)

    def _get_hyperframes_template_unavailable_reason(
        self,
        ctx: PipelineContext,
    ) -> Optional[str]:
        config = ctx.config
        execution_mode = self._resolve_asset_execution_mode(ctx)
        if execution_mode.template_type != "image":
            return f"template type {execution_mode.template_type!r} is not supported by HyperFrames"
        if execution_mode.media_domain != "image":
            return f"media domain {execution_mode.media_domain!r} is not supported by HyperFrames"

        template_dir = (
            Path(__file__).resolve().parents[2]
            / "resources"
            / "hyperframes"
            / "templates"
            / self._resolve_hyperframes_template_id(config)
        )
        if not template_dir.exists():
            return f"HyperFrames template directory does not exist: {template_dir}"
        return None

    def _resolve_render_capability(self, ctx: PipelineContext):
        execution_mode = self._resolve_asset_execution_mode(ctx)
        requested_backend = getattr(ctx.config, "render_backend", LEGACY_RENDER_BACKEND)
        hyperframes_template_unavailable_reason = (
            self._get_hyperframes_template_unavailable_reason(ctx)
        )
        has_hyperframes_native_template = hyperframes_template_unavailable_reason is None
        template_prerendered = (
            execution_mode.template_type == "image"
            and execution_mode.media_domain == "image"
        )
        if requested_backend == HYPERFRAMES_COMPILED_RENDER_BACKEND:
            # Compiled HyperFrames renders native templates from raw media; prerendered
            # HTML screenshots belong to legacy/ffmpeg-manifest paths only.
            template_prerendered = False

        element_motion_backend = None
        if getattr(ctx.config, "element_animation_enabled", False):
            element_motion_backend = getattr(
                ctx.config,
                "element_animation_backend",
                None,
            )

        result = RenderCapabilityResolver().resolve(
            RenderCapabilityInput(
                requested_backend=requested_backend,
                template_type=execution_mode.template_type,
                media_domain=execution_mode.media_domain,
                template_prerendered=template_prerendered,
                element_motion_backend=element_motion_backend,
                has_hyperframes_native_template=has_hyperframes_native_template,
            )
        )

        fallback_reason = result.fallback_reason
        if (
            result.fallback_reason
            and requested_backend == HYPERFRAMES_COMPILED_RENDER_BACKEND
            and hyperframes_template_unavailable_reason
        ):
            fallback_reason = hyperframes_template_unavailable_reason
        elif (
            result.fallback_reason
            and requested_backend == FFMPEG_MANIFEST_RENDER_BACKEND
            and element_motion_backend == "hyperframes_canvas"
            and hyperframes_template_unavailable_reason
            and result.effective_backend == LEGACY_RENDER_BACKEND
        ):
            fallback_reason = (
                f"{result.fallback_reason}: "
                f"{hyperframes_template_unavailable_reason}"
            )

        if fallback_reason != result.fallback_reason:
            result = RenderCapabilityResult(
                effective_backend=result.effective_backend,
                fallback_reason=fallback_reason,
            )
        setattr(ctx, "render_backend_fallback_reason", result.fallback_reason)
        return result

    def _get_render_backend_fallback_reason(
        self,
        ctx: PipelineContext,
    ) -> Optional[str]:
        return self._resolve_render_capability(ctx).fallback_reason

    def _is_hyperframes_render_path(self, ctx: PipelineContext) -> bool:
        return (
            self._resolve_effective_render_backend(ctx)
            == HYPERFRAMES_COMPILED_RENDER_BACKEND
        )

    def _resolve_effective_render_backend(self, ctx: PipelineContext) -> str:
        return self._resolve_render_capability(ctx).effective_backend

    def _resolve_effective_tts_audio_strategy(self, ctx: PipelineContext) -> str:
        requested_strategy = (
            getattr(ctx.config, "tts_audio_strategy", AUTO_TTS_AUDIO_STRATEGY)
            or AUTO_TTS_AUDIO_STRATEGY
        )
        if requested_strategy not in SUPPORTED_STANDARD_TTS_AUDIO_STRATEGIES:
            if requested_strategy == PER_FRAME_TTS_AUDIO_STRATEGY:
                raise ValueError(
                    "per_frame tts_audio_strategy is not supported in standard video generation"
                )
            raise ValueError(
                f"unsupported standard tts_audio_strategy: {requested_strategy}"
            )
        if self._resolve_effective_render_backend(ctx) in {
            HYPERFRAMES_COMPILED_RENDER_BACKEND,
            FFMPEG_MANIFEST_RENDER_BACKEND,
        }:
            return MASTER_TRACK_TTS_AUDIO_STRATEGY

        if requested_strategy == AUTO_TTS_AUDIO_STRATEGY:
            return MASTER_TRACK_TTS_AUDIO_STRATEGY
        return requested_strategy

    def _legacy_template_body_text_for_captions(self, ctx: PipelineContext) -> Optional[str]:
        template_text_policy = getattr(ctx.config, "template_text_policy", "caption_renderer")
        if template_text_policy in {"template_body", "explicit_both"}:
            return None
        if self._caption_renderer_enabled(ctx, "ass"):
            return ""
        return None

    def _resolve_effective_timing_plan_settings(
        self,
        config: StoryboardConfig,
    ) -> tuple[int, int, bool, bool]:
        max_sentences = max(1, int(config.tts_batch_max_sentences))
        max_chars = max(1, int(config.tts_batch_max_chars))
        normalize_block_text_for_tts = False
        single_audio_block = False

        if self._uses_index_tts2_workflow(config):
            normalize_block_text_for_tts = True
            single_audio_block = True
            if config.tts_split_mode != INTERNAL_ONLY_TTS_SPLIT_MODE:
                max_chars = max(1, int(config.max_chars_per_tts_segment))

        return max_sentences, max_chars, normalize_block_text_for_tts, single_audio_block

    def _uses_index_tts2_workflow(self, config: StoryboardConfig) -> bool:
        if config.tts_inference_mode != "comfyui":
            return False

        workflow_key = config.tts_workflow or ""
        tts_service = getattr(self.core, "tts", None)
        if tts_service is not None and hasattr(tts_service, "_resolve_workflow"):
            try:
                workflow_key = tts_service._resolve_workflow(workflow=config.tts_workflow)["key"]
            except Exception:
                workflow_key = config.tts_workflow or workflow_key

        return is_index_tts2_workflow_key(workflow_key)

    def _resolve_tts_source_extension(self, config: StoryboardConfig) -> str:
        if config.tts_inference_mode != "comfyui":
            return ".mp3"

        tts_service = getattr(self.core, "tts", None)
        if tts_service is not None and hasattr(tts_service, "_resolve_workflow"):
            try:
                workflow_info = tts_service._resolve_workflow(workflow=config.tts_workflow)
                extension = resolve_workflow_output_audio_extension_from_info(
                    workflow_info,
                    default=".mp3",
                )
                return extension or ".mp3"
            except Exception:
                pass

        extension = resolve_workflow_output_audio_extension_from_key(
            config.tts_workflow,
            default=".mp3",
        )
        return extension or ".mp3"

    async def _prepare_legacy_master_track_audio(self, ctx: PipelineContext) -> None:
        storyboard = ctx.storyboard
        if not storyboard.frames:
            return
        if all(frame.audio_path for frame in storyboard.frames):
            if getattr(ctx, "master_audio_path", None):
                return
            raise RuntimeError(
                "master-track audio requires a synthesized master_audio_path; "
                "frame audio alone is not a valid standard video audio source."
            )
        if any(frame.audio_path for frame in storyboard.frames):
            raise RuntimeError(
                "master-track audio preparation requires all frame audio to come "
                "from the same synthesized master track."
            )
        if ctx.timing_plan is None or not ctx.timing_plan.blocks:
            raise RuntimeError("master-track audio preparation requires a timing plan.")
        if not getattr(ctx.timing_plan, "sentences", None):
            raise RuntimeError("master-track audio preparation requires sentence timings.")

        master_audio_path, master_audio_duration = await self._synthesize_hyperframes_audio(ctx)
        setattr(ctx, "master_audio_path", master_audio_path)
        setattr(ctx, "master_audio_duration", master_audio_duration)
        self._align_legacy_master_track_timings(ctx)
        self._offset_sentence_timings_to_master_timeline(ctx.timing_plan)
        frame_timing_windows = {
            window.frame_index: window
            for window in allocate_frame_timing_windows(
                frame_count=len(storyboard.frames),
                sentence_units=ctx.timing_plan.sentences,
            )
        }

        for frame in storyboard.frames:
            window = frame_timing_windows.get(frame.index)
            if window is None or window.end <= window.start:
                raise RuntimeError(
                    f"Unable to resolve master-track timing window for frame {frame.index + 1}."
                )

            output_path = get_task_frame_path(ctx.config.task_id, frame.index, "audio")
            output_path = str(Path(output_path).with_suffix(".wav"))
            self._extract_audio_clip(
                master_audio_path,
                output_path,
                start_time=window.start,
                end_time=window.end,
                fade_ms=ctx.config.tts_audio_boundary_fade_ms,
            )
            frame.audio_path = output_path
            frame.duration = self._get_audio_duration(output_path)

    def _assert_master_track_audio_prepared(self, ctx: PipelineContext) -> None:
        frames = list(getattr(ctx.storyboard, "frames", []) or [])
        if not frames:
            return
        missing_audio = [
            frame.index + 1
            for frame in frames
            if not getattr(frame, "audio_path", None)
        ]
        if missing_audio:
            raise RuntimeError(
                "master-track audio was not prepared for every frame: "
                + ", ".join(str(index) for index in missing_audio)
            )
        if not getattr(ctx, "master_audio_path", None):
            raise RuntimeError(
                "master-track audio requires a synthesized master_audio_path; "
                "standard video generation cannot fall back to per-frame audio."
            )

    def _align_legacy_master_track_timings(self, ctx: PipelineContext) -> None:
        engine = (ctx.config.subtitle_alignment_engine or "qwen_forced_aligner").strip().lower()
        timing_plan = ctx.timing_plan

        if engine == "direct_duration":
            self.core.alignment_service.align_blocks_by_duration(
                timing_plan.blocks,
                timing_plan.sentences,
            )
            return

        try:
            self.core.alignment_service.align_blocks(
                timing_plan.blocks,
                timing_plan.sentences,
            )
        except Exception as exc:
            logger.warning(
                "Legacy master-track alignment failed with "
                f"{ctx.config.subtitle_alignment_engine!r}: {exc}. Falling back to duration alignment."
            )
            self.core.alignment_service.align_blocks_by_duration(
                timing_plan.blocks,
                timing_plan.sentences,
            )

    def _extract_audio_clip(
        self,
        input_path: str,
        output_path: str,
        *,
        start_time: float,
        end_time: float,
        fade_ms: int = 8,
    ) -> str:
        duration = max(float(end_time) - float(start_time), 0.01)
        fade_duration = min(max(float(fade_ms), 0.0) / 1000.0, duration / 4)
        fade_out_start = max(duration - fade_duration, 0.0)
        audio_filter = (
            f"afade=t=in:st=0:d={self._format_ffmpeg_time(fade_duration)},"
            f"afade=t=out:st={self._format_ffmpeg_time(fade_out_start)}:"
            f"d={self._format_ffmpeg_time(fade_duration)}"
        )
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        completed = subprocess.run(
            [
                "ffmpeg",
                "-ss",
                self._format_ffmpeg_time(start_time),
                "-i",
                input_path,
                "-t",
                self._format_ffmpeg_time(duration),
                "-vn",
                "-af",
                audio_filter,
                "-c:a",
                "pcm_s16le",
                "-y",
                output_path,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip() or "unknown error"
            raise RuntimeError(f"Failed to extract legacy master-track audio clip: {detail}")
        return output_path

    @staticmethod
    def _format_ffmpeg_time(value: float) -> str:
        formatted = format(max(float(value), 0.0), ".12f").rstrip("0").rstrip(".")
        return formatted or "0"

    def _stage_progress(
        self,
        stage_start: float,
        stage_end: float,
        frame_current: int,
        frame_total: int,
    ) -> float:
        if frame_total <= 0:
            return stage_end

        frame_fraction = frame_current / frame_total
        return stage_start + ((stage_end - stage_start) * frame_fraction)

    def _report_staged_frame_progress(
        self,
        callback: Optional[Callable[[ProgressEvent], None]],
        *,
        stage_start: float,
        stage_end: float,
        frame_current: int,
        frame_total: int,
        step: int,
        action: str | ProgressFrameAction,
    ) -> None:
        self._report_progress(
            callback,
            ProgressEventType.FRAME_STEP,
            self._stage_progress(stage_start, stage_end, frame_current, frame_total),
            frame_current=frame_current,
            frame_total=frame_total,
            step=step,
            action=action,
        )

    async def _produce_assets_staged(
        self,
        ctx: PipelineContext,
        *,
        template_body_text: Optional[str] = None,
        media_session_policy: LocalMediaSessionPolicy = "batch",
    ):
        storyboard = ctx.storyboard
        config = ctx.config
        total_frames = len(storyboard.frames)

        logger.info("Using staged selfhost image processing")

        async with _maybe_local_comfyui_workflow_session(
            self.core,
            release_after_session=True,
        ):
            for frame in storyboard.frames:
                if not frame.audio_path:
                    self._report_staged_frame_progress(
                        ctx.progress_callback,
                        stage_start=0.20,
                        stage_end=0.35,
                        frame_current=frame.index + 1,
                        frame_total=total_frames,
                        step=1,
                        action=ProgressFrameAction.AUDIO,
                    )
                    await self.core.frame_processor._step_generate_audio(frame, config)

        await self._produce_staged_media(
            ctx,
            stage_start=0.35,
            stage_end=0.50,
            media_session_policy=media_session_policy,
        )

        for frame in storyboard.frames:
            self._report_staged_frame_progress(
                ctx.progress_callback,
                stage_start=0.50,
                stage_end=0.65,
                frame_current=frame.index + 1,
                frame_total=total_frames,
                step=3,
                action=ProgressFrameAction.COMPOSE,
            )
            await self.core.frame_processor._step_compose_frame(
                frame,
                storyboard,
                config,
                template_body_text=template_body_text,
            )

        for frame in storyboard.frames:
            self._report_staged_frame_progress(
                ctx.progress_callback,
                stage_start=0.65,
                stage_end=0.80,
                frame_current=frame.index + 1,
                frame_total=total_frames,
                step=4,
                action=ProgressFrameAction.VIDEO,
            )
            await self._materialize_element_motion_for_frame(ctx, frame)
            await self.core.frame_processor._step_create_video_segment(frame, config)
            storyboard.total_duration += frame.duration

    async def _produce_staged_media(
        self,
        ctx: PipelineContext,
        *,
        stage_start: float,
        stage_end: float,
        media_session_policy: LocalMediaSessionPolicy,
    ) -> None:
        storyboard = ctx.storyboard
        total_frames = len(storyboard.frames)

        if media_session_policy == "per_frame":
            for frame in storyboard.frames:
                if frame.image_prompt is None:
                    await self._produce_staged_media_frame(
                        ctx,
                        frame,
                        stage_start=stage_start,
                        stage_end=stage_end,
                        total_frames=total_frames,
                    )
                    continue

                async with _maybe_local_comfyui_workflow_session(
                    self.core,
                    release_after_session=True,
                ):
                    await self._produce_staged_media_frame(
                        ctx,
                        frame,
                        stage_start=stage_start,
                        stage_end=stage_end,
                        total_frames=total_frames,
                    )
            return

        if media_session_policy == "batch":
            generatable_frame_count = sum(
                1
                for frame in storyboard.frames
                if frame.image_prompt is not None
            )
            release_after_session = True
            emit_stage_event(
                channel="runtime",
                stage="local_media_batch",
                event="start",
                message="Local media batch generation started",
                media_session_policy=media_session_policy,
                frame_count=total_frames,
                generatable_frame_count=generatable_frame_count,
                release_after_session=release_after_session,
            )
            started_at = time.perf_counter()
            generated_frame_count = 0
            try:
                async with _maybe_local_comfyui_workflow_session(
                    self.core,
                    release_after_session=release_after_session,
                ):
                    for frame in storyboard.frames:
                        await self._produce_staged_media_frame(
                            ctx,
                            frame,
                            stage_start=stage_start,
                            stage_end=stage_end,
                            total_frames=total_frames,
                        )
                        if frame.image_prompt is not None:
                            generated_frame_count += 1
            except Exception:
                elapsed_ms = int(round((time.perf_counter() - started_at) * 1000))
                emit_stage_event(
                    channel="runtime",
                    stage="local_media_batch",
                    event="fail",
                    message="Local media batch generation failed",
                    media_session_policy=media_session_policy,
                    frame_count=total_frames,
                    generatable_frame_count=generatable_frame_count,
                    generated_frame_count=generated_frame_count,
                    release_after_session=release_after_session,
                    elapsed_ms=elapsed_ms,
                )
                raise
            elapsed_ms = int(round((time.perf_counter() - started_at) * 1000))
            emit_stage_event(
                channel="runtime",
                stage="local_media_batch",
                event="end",
                message="Local media batch generation completed",
                media_session_policy=media_session_policy,
                frame_count=total_frames,
                generatable_frame_count=generatable_frame_count,
                generated_frame_count=generated_frame_count,
                release_after_session=release_after_session,
                elapsed_ms=elapsed_ms,
            )
            return

        for frame in storyboard.frames:
            await self._produce_staged_media_frame(
                ctx,
                frame,
                stage_start=stage_start,
                stage_end=stage_end,
                total_frames=total_frames,
            )

    async def _produce_staged_media_frame(
        self,
        ctx: PipelineContext,
        frame: StoryboardFrame,
        *,
        stage_start: float,
        stage_end: float,
        total_frames: int,
    ) -> None:
        config = ctx.config
        has_existing_media = frame.image_path is not None or frame.video_path is not None
        needs_generation = frame.image_prompt is not None

        if needs_generation:
            self._report_staged_frame_progress(
                ctx.progress_callback,
                stage_start=stage_start,
                stage_end=stage_end,
                frame_current=frame.index + 1,
                frame_total=total_frames,
                step=2,
                action=ProgressFrameAction.MEDIA,
            )
            await self.core.frame_processor._step_generate_media(frame, config)
            await self._register_storyboard_workbench_frame_artifact(ctx, frame)
        elif not has_existing_media:
            frame.image_path = None
            frame.media_type = None

    async def _register_storyboard_workbench_artifacts(self, ctx: PipelineContext) -> None:
        storyboard = ctx.storyboard
        if storyboard is None:
            return
        for frame in storyboard.frames:
            await self._register_storyboard_workbench_frame_artifact(ctx, frame)

    async def _register_storyboard_workbench_frame_artifact(
        self,
        ctx: PipelineContext,
        frame: StoryboardFrame,
    ) -> None:
        if frame.workbench_state is not None or not frame.image_path:
            return
        dependencies = self._resolve_storyboard_workbench_dependencies()
        if dependencies is None:
            return
        storyboard_id, frame_id, prompt_plan = self._resolve_frame_prompt_plan(
            ctx,
            frame,
        )
        if not storyboard_id or not frame_id or prompt_plan is None:
            return

        bridge = StoryboardWorkbenchArtifactBridge(**dependencies)
        state = await bridge.attach_generated_image(
            workspace_id=self._resolve_workspace_id(ctx),
            storyboard_id=storyboard_id,
            frame=frame,
            frame_id=frame_id,
            prompt_plan=prompt_plan,
            source_path=frame.image_path,
            provider=self._resolve_workbench_provider(ctx),
            width=getattr(ctx.config, "media_width", None),
            height=getattr(ctx.config, "media_height", None),
        )
        if state is not None:
            await self._persist_storyboard_workbench_state(
                ctx,
                storyboard_id=storyboard_id,
                frame_id=frame_id,
                workbench_state=state.to_dict(),
            )
            self._sync_workbench_artifact_ref_to_planning_snapshot(
                ctx,
                frame_id=frame_id,
                artifact_id=state.selected_image_artifact_id,
            )

    def _resolve_storyboard_workbench_dependencies(self) -> dict[str, Any] | None:
        artifact_repository = getattr(self.core, "artifact_repository", None)
        object_store = getattr(self.core, "artifact_object_store", None)
        trace_repository = getattr(self.core, "trace_repository", None)
        if artifact_repository is None or object_store is None or trace_repository is None:
            return None
        return {
            "artifact_repository": artifact_repository,
            "object_store": object_store,
            "trace_repository": trace_repository,
        }

    async def _persist_prompt_plan_bundle(self, ctx: PipelineContext) -> None:
        prompt_plan_repository = getattr(self.core, "prompt_plan_repository", None)
        if prompt_plan_repository is None or not isinstance(ctx.planning_snapshot, Mapping):
            return
        bundle = ctx.planning_snapshot.get("prompt_plan_bundle")
        if not isinstance(bundle, Mapping):
            return
        await prompt_plan_repository.save_prompt_plan_bundle(
            self._resolve_workspace_id(ctx),
            dict(bundle),
        )

    def _resolve_frame_prompt_plan(
        self,
        ctx: PipelineContext,
        frame: StoryboardFrame,
    ) -> tuple[str, str, PromptPlan | None]:
        snapshot = ctx.planning_snapshot or getattr(ctx.storyboard, "planning_snapshot", None) or {}
        generation = snapshot.get("storyboard_generation")
        if not isinstance(generation, Mapping):
            return "", "", None
        storyboard_id = str(generation.get("plan_id") or "").strip()
        frame_id = self._resolve_snapshot_frame_id(snapshot, frame.index)
        if not storyboard_id or not frame_id:
            return "", "", None
        bundle = snapshot.get("prompt_plan_bundle")
        if not isinstance(bundle, Mapping):
            return storyboard_id, frame_id, None
        plans = bundle.get("prompt_plans")
        if not isinstance(plans, list):
            return storyboard_id, frame_id, None
        for plan_payload in plans:
            if not isinstance(plan_payload, Mapping):
                continue
            if str(plan_payload.get("frame_id") or "").strip() == frame_id:
                return storyboard_id, frame_id, PromptPlan.from_dict(plan_payload)
        return storyboard_id, frame_id, None

    @staticmethod
    def _resolve_snapshot_frame_id(snapshot: Mapping[str, Any], frame_index: int) -> str:
        generation = snapshot.get("storyboard_generation")
        if not isinstance(generation, Mapping):
            return ""
        frames = generation.get("frames")
        if not isinstance(frames, list) or frame_index >= len(frames):
            return ""
        frame_payload = frames[frame_index]
        if not isinstance(frame_payload, Mapping):
            return ""
        return str(frame_payload.get("frame_id") or "").strip()

    @staticmethod
    def _resolve_workspace_id(ctx: PipelineContext) -> str:
        return str(
            ctx.params.get("workspace_id")
            or ctx.params.get("project_id")
            or ctx.session_id
            or "workspace_1"
        ).strip()

    @staticmethod
    def _resolve_workbench_provider(ctx: PipelineContext) -> str | None:
        if ctx.params.get("media_workflow"):
            return "media_workflow"
        return None

    async def _persist_storyboard_workbench_state(
        self,
        ctx: PipelineContext,
        *,
        storyboard_id: str,
        frame_id: str,
        workbench_state: dict[str, Any],
    ) -> None:
        state_store = getattr(self.core, "storyboard_workbench_state_store", None)
        if state_store is None:
            return
        await state_store.save_frame_state(
            self._resolve_workspace_id(ctx),
            storyboard_id,
            frame_id,
            workbench_state,
        )

    def _sync_workbench_artifact_ref_to_planning_snapshot(
        self,
        ctx: PipelineContext,
        *,
        frame_id: str,
        artifact_id: str | None,
    ) -> None:
        if not artifact_id:
            return
        if ctx.planning_snapshot is None:
            ctx.planning_snapshot = {}
        snapshots = [ctx.planning_snapshot]
        if ctx.storyboard is not None:
            if ctx.storyboard.planning_snapshot is None:
                ctx.storyboard.planning_snapshot = ctx.planning_snapshot
            elif ctx.storyboard.planning_snapshot is not ctx.planning_snapshot:
                snapshots.append(ctx.storyboard.planning_snapshot)

        for snapshot in snapshots:
            generation = snapshot.get("storyboard_generation")
            if isinstance(generation, dict):
                for frame_payload in generation.get("frames") or ():
                    if (
                        isinstance(frame_payload, dict)
                        and str(frame_payload.get("frame_id") or "").strip() == frame_id
                    ):
                        frame_payload["image_artifact_id"] = artifact_id
            display_frames = snapshot.get("frames")
            generation_frames = (
                generation.get("frames")
                if isinstance(generation, Mapping)
                else None
            )
            for index, frame_payload in enumerate(display_frames or ()):
                if isinstance(frame_payload, dict):
                    candidate_id = str(frame_payload.get("frame_id") or "").strip()
                    if not candidate_id and isinstance(generation_frames, list) and index < len(generation_frames):
                        identity_frame = generation_frames[index]
                        if isinstance(identity_frame, Mapping):
                            candidate_id = str(identity_frame.get("frame_id") or "").strip()
                    if candidate_id == frame_id:
                        frame_payload["image_artifact_id"] = artifact_id

    async def _materialize_element_motion_for_frame(
        self,
        ctx: PipelineContext,
        frame: StoryboardFrame,
    ) -> None:
        config = ctx.config
        if not getattr(config, "element_animation_enabled", False):
            return

        source_image_path = self._resolve_element_motion_source_image_path(ctx, frame)
        if not source_image_path:
            return

        from pixelle_video.services.element_motion_materializer import (
            ElementMotionMaterializer,
        )
        from pixelle_video.services.element_segmentation import ElementSegmentationService

        materializer = ElementMotionMaterializer(
            segmentation_service=ElementSegmentationService(self.core),
        )
        task_id = getattr(ctx, "task_id", None) or config.task_id or ""
        output_dir = getattr(ctx, "task_dir", None) or Path(source_image_path).parent
        canvas_width, canvas_height = self._resolve_storyboard_canvas_size(config)

        artifact = await materializer.materialize_frame(
            frame=frame,
            source_image_path=source_image_path,
            task_id=task_id,
            output_dir=output_dir,
            width=canvas_width,
            height=canvas_height,
            fps=int(config.video_fps),
            backend=config.element_animation_backend,
            selected_count=int(config.element_animation_subject_count),
            candidate_limit=int(config.element_animation_candidate_limit),
            prompt=config.element_animation_prompt,
            workflow=config.element_animation_workflow,
            intensity=config.element_animation_intensity,
            audio_path=frame.audio_path,
        )
        frame.element_animation_manifest_path = artifact.manifest_path
        frame.element_motion_video_path = artifact.motion_video_path

    def _resolve_element_motion_source_image_path(
        self,
        ctx: PipelineContext,
        frame: StoryboardFrame,
    ) -> str | None:
        if self._resolve_effective_render_backend(ctx) == HYPERFRAMES_COMPILED_RENDER_BACKEND:
            return frame.image_path
        return frame.composed_image_path or frame.image_path

    async def produce_assets(self, ctx: PipelineContext):
        """Step 6: Generate audio, images, and render frames (Core processing)."""
        storyboard = ctx.storyboard
        config = ctx.config
        effective_tts_audio_strategy = self._resolve_effective_tts_audio_strategy(ctx)
        if self._is_hyperframes_render_path(ctx):
            await self._produce_assets_hyperframes(ctx)
            await self._register_storyboard_workbench_artifacts(ctx)
            logger.info("All raw media assets prepared for HyperFrames compiled render")
            return

        if effective_tts_audio_strategy == MASTER_TRACK_TTS_AUDIO_STRATEGY:
            await self._prepare_legacy_master_track_audio(ctx)
            self._assert_master_track_audio_prepared(ctx)

        template_body_text = (
            self._legacy_template_body_text_for_captions(ctx)
            if effective_tts_audio_strategy == MASTER_TRACK_TTS_AUDIO_STRATEGY
            else None
        )

        execution_mode = self._resolve_asset_execution_mode(ctx)
        
        # Get concurrent limit from config_manager (supports hot reload without restart)
        from pixelle_video.config import config_manager
        runninghub_concurrent_limit = config_manager.config.comfyui.runninghub_concurrent_limit or 1

        if execution_mode.use_staged_mode:
            await self._produce_assets_staged(
                ctx,
                template_body_text=template_body_text,
                media_session_policy=execution_mode.local_media_session_policy,
            )
            await self._register_storyboard_workbench_artifacts(ctx)
            logger.info(
                f"All frames processed in staged mode (total duration: {storyboard.total_duration:.2f}s)"
            )
            return

        async def element_motion_materializer(frame_to_materialize: StoryboardFrame) -> None:
            await self._materialize_element_motion_for_frame(ctx, frame_to_materialize)
        
        if execution_mode.use_runninghub_parallel and runninghub_concurrent_limit > 1:
            logger.info(f"🚀 Using parallel processing for RunningHub workflows (max {runninghub_concurrent_limit} concurrent)")
            
            semaphore = asyncio.Semaphore(runninghub_concurrent_limit)
            completed_count = 0
            
            async def process_frame_with_semaphore(i: int, frame: StoryboardFrame):
                nonlocal completed_count
                async with semaphore:
                    base_progress = 0.2
                    frame_range = 0.6
                    per_frame_progress = frame_range / len(storyboard.frames)
                    
                    # Create frame-specific progress callback
                    def frame_progress_callback(event: ProgressEvent):
                        overall_progress = base_progress + (per_frame_progress * completed_count) + (per_frame_progress * event.progress)
                        if ctx.progress_callback:
                            adjusted_event = ProgressEvent(
                                event_type=event.event_type,
                                progress=overall_progress,
                                frame_current=i+1,
                                frame_total=len(storyboard.frames),
                                step=event.step,
                                action=event.action
                            )
                            ctx.progress_callback(adjusted_event)
                    
                    # Report frame start
                    self._report_progress(
                        ctx.progress_callback,
                        ProgressEventType.PROCESSING_FRAME,
                        base_progress + (per_frame_progress * completed_count),
                        frame_current=i+1,
                        frame_total=len(storyboard.frames)
                    )
                    
                    frame_processor_kwargs = {
                        "frame": frame,
                        "storyboard": storyboard,
                        "config": config,
                        "total_frames": len(storyboard.frames),
                        "progress_callback": frame_progress_callback,
                        "template_body_text": template_body_text,
                    }
                    if getattr(config, "element_animation_enabled", False):
                        frame_processor_kwargs[
                            "element_motion_materializer"
                        ] = element_motion_materializer

                    processed_frame = await self.core.frame_processor(
                        **frame_processor_kwargs
                    )
                    
                    completed_count += 1
                    logger.info(f"✅ Frame {i+1} completed ({processed_frame.duration:.2f}s) [{completed_count}/{len(storyboard.frames)}]")
                    return i, processed_frame
            
            # Create all tasks and execute in parallel
            tasks = [process_frame_with_semaphore(i, frame) for i, frame in enumerate(storyboard.frames)]
            results = await asyncio.gather(*tasks)
            
            # Update frames in order and calculate total duration
            for idx, processed_frame in sorted(results, key=lambda x: x[0]):
                storyboard.frames[idx] = processed_frame
                storyboard.total_duration += processed_frame.duration
            await self._register_storyboard_workbench_parallel_results(ctx, results)
            
            logger.info(f"✅ All frames processed in parallel (total duration: {storyboard.total_duration:.2f}s)")
        else:
            # Serial processing for non-RunningHub workflows
            logger.info("⚙️ Using serial processing (non-RunningHub workflow)")
            
            for i, frame in enumerate(storyboard.frames):
                base_progress = 0.2
                frame_range = 0.6
                per_frame_progress = frame_range / len(storyboard.frames)
                
                # Create frame-specific progress callback
                def frame_progress_callback(event: ProgressEvent):
                    overall_progress = base_progress + (per_frame_progress * i) + (per_frame_progress * event.progress)
                    if ctx.progress_callback:
                        adjusted_event = ProgressEvent(
                            event_type=event.event_type,
                            progress=overall_progress,
                            frame_current=event.frame_current,
                            frame_total=event.frame_total,
                            step=event.step,
                            action=event.action
                        )
                        ctx.progress_callback(adjusted_event)
                
                # Report frame start
                self._report_progress(
                    ctx.progress_callback,
                    ProgressEventType.PROCESSING_FRAME,
                    base_progress + (per_frame_progress * i),
                    frame_current=i+1,
                    frame_total=len(storyboard.frames)
                )
                
                frame_processor_kwargs = {
                    "frame": frame,
                    "storyboard": storyboard,
                    "config": config,
                    "total_frames": len(storyboard.frames),
                    "progress_callback": frame_progress_callback,
                    "template_body_text": template_body_text,
                }
                if getattr(config, "element_animation_enabled", False):
                    frame_processor_kwargs[
                        "element_motion_materializer"
                    ] = element_motion_materializer

                processed_frame = await self.core.frame_processor(
                    **frame_processor_kwargs
                )
                storyboard.total_duration += processed_frame.duration
                await self._register_storyboard_workbench_frame_artifact(ctx, processed_frame)
                logger.info(f"✅ Frame {i+1} completed ({processed_frame.duration:.2f}s)")

    async def _produce_assets_hyperframes(self, ctx: PipelineContext):
        execution_mode = self._resolve_asset_execution_mode(ctx)
        media_session_policy = execution_mode.local_media_session_policy
        if media_session_policy == "none" and execution_mode.media_domain != "static":
            media_session_policy = "batch"

        logger.info("Using HyperFrames raw media asset production path")

        await self._produce_staged_media(
            ctx,
            stage_start=0.25,
            stage_end=0.55,
            media_session_policy=media_session_policy,
        )

        logger.info("HyperFrames raw media assets prepared; skipping legacy HTML prerender")

    async def _register_storyboard_workbench_parallel_results(
        self,
        ctx: PipelineContext,
        results: list[tuple[int, StoryboardFrame]],
    ) -> None:
        for _idx, processed_frame in sorted(results, key=lambda item: item[0]):
            await self._register_storyboard_workbench_frame_artifact(ctx, processed_frame)

    async def post_production(self, ctx: PipelineContext):
        """Step 7: Concatenate videos and add BGM."""
        effective_backend = self._resolve_effective_render_backend(ctx)
        if effective_backend == HYPERFRAMES_COMPILED_RENDER_BACKEND:
            await self._post_production_hyperframes(ctx)
            return
        if effective_backend == FFMPEG_MANIFEST_RENDER_BACKEND:
            await self._post_production_ffmpeg_manifest(ctx)
            return

        fallback_reason = self._get_render_backend_fallback_reason(ctx)
        if fallback_reason is not None:
            if ctx.config.render_backend == HYPERFRAMES_COMPILED_RENDER_BACKEND:
                logger.warning(
                    "HyperFrames backend requested but falling back to legacy "
                    f"rendering: {fallback_reason}"
                )
            else:
                logger.warning(
                    f"Render backend {ctx.config.render_backend!r} resolved to "
                    f"{effective_backend!r}: {fallback_reason}"
                )

        self._report_progress(ctx.progress_callback, ProgressEventType.CONCATENATING, 0.85)
        
        storyboard = ctx.storyboard
        segment_paths = [frame.video_segment_path for frame in storyboard.frames]
        
        video_service = VideoService()
        
        final_video_path = video_service.concat_videos(
            videos=segment_paths,
            output=ctx.final_video_path,
            bgm_path=ctx.params.get("bgm_path"),
            bgm_volume=ctx.params.get("bgm_volume", 0.2),
            bgm_mode=ctx.params.get("bgm_mode", "loop")
        )

        self._get_text_rendering_result(ctx)
        text_tracks, text_cues = self._compile_text_layer_for_render(ctx)
        caption_cues = (
            self._build_caption_cues_for_render(ctx, rebuild=True)
            if self._caption_renderer_enabled(ctx, "ass")
            else []
        )
        self._update_text_render_package(
            ctx,
            caption_cues=caption_cues,
            text_tracks=text_tracks,
            text_cues=text_cues,
        )
        overlay_ass_tracks, overlay_ass_cues = self._filter_text_layer_for_renderer(
            text_tracks,
            text_cues,
            renderer="ass",
        )
        caption_ass_tracks, caption_ass_cues = self._caption_text_layer_for_renderer(
            ctx,
            caption_cues=caption_cues,
            renderer="ass",
        )
        ass_tracks = [*caption_ass_tracks, *overlay_ass_tracks]
        ass_cues = [*caption_ass_cues, *overlay_ass_cues]
        ass_outputs = None
        if ass_cues:
            ass_dir = Path(ctx.task_dir or Path(final_video_path).parent) / "text_layer"
            canvas_width, canvas_height = self._resolve_storyboard_canvas_size(
                storyboard.config
            )
            manifest = RenderManifest(
                task_id=ctx.task_id or storyboard.config.task_id or "",
                title=storyboard.title,
                canvas_width=canvas_width,
                canvas_height=canvas_height,
                media_width=storyboard.config.media_width,
                media_height=storyboard.config.media_height,
                sync_media_size_to_canvas=storyboard.config.sync_media_size_to_canvas,
                media_layout_mode=storyboard.config.media_layout_mode,
                media_placement=storyboard.config.media_placement,
                fps=storyboard.config.video_fps,
                template_id="legacy",
                caption_rendering_enabled=self._caption_renderer_enabled(ctx, "ass"),
                caption_renderer_targets=list(
                    self._caption_renderer_targets_for_summary(ctx)
                ),
                caption_cues=caption_cues,
                text_style_profiles=self._text_style_profiles_for_manifest(ctx),
                text_tracks=ass_tracks,
                text_cues=ass_cues,
            )
            ass_outputs = AssTextAdapter().export(
                manifest=manifest,
                output_dir=ass_dir,
            )
            burned_path = str(Path(final_video_path).with_name("final_text_burned.mp4"))
            final_video_path = video_service.burn_ass_subtitles(
                final_video_path,
                str(ass_outputs.master),
                burned_path,
            )
        self._record_caption_rendering_summary(
            ctx,
            enabled=bool(caption_ass_cues),
            caption_cue_count=len(caption_ass_cues),
            style_profile=self._caption_style_profile_for_summary(ctx),
            renderer_targets=self._caption_renderer_targets_for_summary(ctx),
            artifacts=self._ass_caption_artifacts(ass_outputs),
            fallbacks=self._ass_export_fallbacks(ass_outputs),
        )
        self._record_text_layer_summary(
            ctx,
            renderer="ass" if overlay_ass_cues else "disabled",
            text_tracks=overlay_ass_tracks,
            text_cues=overlay_ass_cues,
            native_hint_count=self._count_native_prompt_hints(ctx),
            artifacts=(
                self._ass_text_layer_artifacts(ass_outputs)
                if overlay_ass_cues
                else {}
            ),
            fallbacks=(
                self._ass_export_fallbacks(ass_outputs)
                if overlay_ass_cues
                else ()
            ),
        )
        
        storyboard.final_video_path = final_video_path
        storyboard.completed_at = datetime.now()
        
        # Copy to user-specified path if provided
        user_specified_output = ctx.params.get("output_path")
        if user_specified_output:
            Path(user_specified_output).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(final_video_path, user_specified_output)
            logger.info(f"📹 Final video copied to: {user_specified_output}")
            ctx.final_video_path = user_specified_output
            storyboard.final_video_path = user_specified_output
        
        logger.success(f"🎬 Video generation completed: {ctx.final_video_path}")

    async def _post_production_ffmpeg_manifest(self, ctx: PipelineContext):
        self._report_progress(ctx.progress_callback, ProgressEventType.RENDERING_FFMPEG_MANIFEST, 0.85)

        manifest = self._build_render_manifest_for_current_timeline(ctx)
        execution_plan = self._build_render_execution_plan(ctx, manifest=manifest)
        ass_outputs = self._export_ass_for_manifest_if_needed(ctx, manifest)

        from pixelle_video.services.ffmpeg_manifest_renderer import FfmpegManifestRenderer

        final_video_path = FfmpegManifestRenderer().render(
            manifest=manifest,
            execution_plan=execution_plan,
            output_path=ctx.final_video_path,
            ass_path=str(ass_outputs.master) if ass_outputs else None,
            bgm_path=ctx.params.get("bgm_path"),
            bgm_volume=ctx.params.get("bgm_volume", 0.2),
            bgm_mode=ctx.params.get("bgm_mode", "loop"),
        )

        ctx.observability["render_execution_plan"] = execution_plan.to_dict()
        ctx.storyboard.final_video_path = final_video_path
        ctx.storyboard.completed_at = datetime.now()

        user_specified_output = ctx.params.get("output_path")
        if user_specified_output:
            Path(user_specified_output).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(final_video_path, user_specified_output)
            logger.info(f"Copied final video to user path: {user_specified_output}")
            ctx.final_video_path = user_specified_output
            ctx.storyboard.final_video_path = user_specified_output
        else:
            ctx.final_video_path = final_video_path
            ctx.storyboard.final_video_path = final_video_path

        logger.success(f"FFmpeg manifest video generation completed: {ctx.final_video_path}")

    def _build_render_manifest_for_current_timeline(
        self,
        ctx: PipelineContext,
    ) -> RenderManifest:
        storyboard = ctx.storyboard
        config = ctx.config
        master_audio_path, master_audio_duration = self._resolve_master_audio_for_manifest(ctx)
        caption_cues = (
            self._build_caption_cues_for_render(ctx, rebuild=True)
            if self._caption_renderer_enabled(ctx, "ass")
            else []
        )
        canvas_width, canvas_height = self._resolve_storyboard_canvas_size(config)
        return RenderManifest(
            task_id=ctx.task_id or config.task_id or "",
            title=storyboard.title,
            canvas_width=canvas_width,
            canvas_height=canvas_height,
            media_width=config.media_width,
            media_height=config.media_height,
            sync_media_size_to_canvas=config.sync_media_size_to_canvas,
            media_layout_mode=config.media_layout_mode,
            media_placement=config.media_placement,
            fps=config.video_fps,
            template_id=Path(config.frame_template).stem,
            master_audio_path=master_audio_path,
            master_audio_duration=master_audio_duration,
            audio_blocks=list(getattr(ctx.timing_plan, "blocks", []) or []),
            sentence_units=list(getattr(ctx.timing_plan, "sentences", []) or []),
            visual_clips=self._build_manifest_visual_clips(ctx),
            caption_rendering_enabled=self._caption_renderer_enabled(ctx, "ass"),
            caption_renderer_targets=list(
                self._caption_renderer_targets_for_summary(ctx)
            ),
            caption_cues=caption_cues,
            text_style_profiles=self._text_style_profiles_for_manifest(ctx),
            caption_punctuation_mode=self._caption_punctuation_mode_for_manifest(ctx),
        )

    def _resolve_master_audio_for_manifest(
        self,
        ctx: PipelineContext,
    ) -> tuple[str, float | None]:
        master_audio_path = getattr(ctx, "master_audio_path", None)
        master_audio_duration = getattr(ctx, "master_audio_duration", None)
        if master_audio_path:
            return str(master_audio_path), master_audio_duration

        if ctx.task_dir:
            candidate = Path(ctx.task_dir) / "audio" / "master_audio.wav"
            if candidate.exists():
                duration = (
                    master_audio_duration
                    if master_audio_duration is not None
                    else self._get_audio_duration(str(candidate))
                )
                setattr(ctx, "master_audio_path", str(candidate))
                setattr(ctx, "master_audio_duration", duration)
                return str(candidate), duration

        raise RuntimeError("ffmpeg_manifest render path requires master audio")

    def _build_manifest_visual_clips(self, ctx: PipelineContext) -> list[VisualClip]:
        prefer_template_frame = (
            self._resolve_effective_render_backend(ctx) != HYPERFRAMES_COMPILED_RENDER_BACKEND
        )
        windows = {
            window.frame_index: window
            for window in allocate_frame_timing_windows(
                frame_count=len(ctx.storyboard.frames),
                sentence_units=getattr(ctx.timing_plan, "sentences", []) or [],
            )
        }
        visual_clips: list[VisualClip] = []
        cursor = 0.0
        for frame in ctx.storyboard.frames:
            media_path, media_type, source_kind, source_media_path = (
                self._resolve_manifest_frame_media(
                    frame,
                    prefer_template_frame=prefer_template_frame,
                )
            )
            if not media_path:
                logger.warning(
                    f"Skipping render manifest visual clip for frame {frame.index + 1}: missing media"
                )
                continue

            window = windows.get(frame.index)
            if window is not None:
                start = float(window.start)
                end = float(window.end)
            else:
                duration = max(float(getattr(frame, "duration", 0.0) or 0.0), 0.001)
                start = cursor
                end = cursor + duration
            cursor = max(cursor, end)

            visual_clips.append(
                VisualClip(
                    id=f"clip-{frame.index + 1}",
                    frame_index=frame.index,
                    start=start,
                    end=max(end, start + 0.001),
                    media_path=media_path,
                    media_type=media_type,
                    source_kind=source_kind,
                    media_role="final_frame",
                    template_id=Path(ctx.config.frame_template).stem,
                    template_path=ctx.config.frame_template,
                    text_policy=getattr(
                        ctx.config,
                        "template_text_policy",
                        "caption_renderer",
                    ),
                    element_animation_manifest_path=getattr(
                        frame,
                        "element_animation_manifest_path",
                        None,
                    ),
                    source_media_path=source_media_path,
                )
            )
        return visual_clips

    def _resolve_manifest_frame_media(
        self,
        frame: StoryboardFrame,
        *,
        prefer_template_frame: bool = True,
    ) -> tuple[str | None, str, str, str | None]:
        if frame.element_motion_video_path:
            source_media_path = frame.image_path or frame.video_path
            if prefer_template_frame and frame.composed_image_path:
                source_media_path = frame.composed_image_path
            return (
                frame.element_motion_video_path,
                "video",
                "element_motion_video",
                source_media_path,
            )
        if prefer_template_frame and frame.composed_image_path:
            return (
                frame.composed_image_path,
                "image",
                "template_frame",
                frame.image_path or frame.video_path,
            )
        if frame.video_path:
            return frame.video_path, "video", "raw_media", None
        if frame.image_path:
            return frame.image_path, "image", "raw_media", None
        return None, "image", "raw_media", None

    def _build_render_execution_plan(
        self,
        ctx: PipelineContext,
        *,
        manifest: RenderManifest | None = None,
    ) -> RenderExecutionPlan:
        manifest = manifest or self._build_render_manifest_for_current_timeline(ctx)
        visual_clips = list(manifest.visual_clips)
        effective_backend = self._resolve_effective_render_backend(ctx)
        if effective_backend == HYPERFRAMES_COMPILED_RENDER_BACKEND:
            template_mode = "hyperframes_native"
        else:
            template_mode = (
                "html_prerender"
                if any(clip.source_kind == "template_frame" for clip in visual_clips)
                else "none"
            )
        element_motion_mode = "disabled"
        if any(clip.source_kind == "element_motion_video" for clip in visual_clips):
            element_motion_mode = "python_ffmpeg"
        elif any(clip.element_animation_manifest_path for clip in visual_clips):
            element_motion_mode = str(
                getattr(ctx.config, "element_animation_backend", "manifest")
            )

        return RenderExecutionPlan(
            requested_backend=ctx.config.render_backend,
            effective_backend=effective_backend,
            fallback_reason=self._get_render_backend_fallback_reason(ctx),
            template_materialization_mode=template_mode,
            element_motion_mode=element_motion_mode,
            subtitle_mode=(
                "ass" if self._caption_renderer_enabled(ctx, "ass") else "disabled"
            ),
            audio_strategy=self._resolve_effective_tts_audio_strategy(ctx),
            artifacts=[
                RenderExecutionArtifact(
                    role=clip.source_kind,
                    path=clip.media_path,
                    frame_index=clip.frame_index,
                )
                for clip in visual_clips
            ],
            diagnostics={
                "clip_count": len(visual_clips),
                "master_audio_path": manifest.master_audio_path,
                "visual_clips": [
                    {
                        "frame_index": clip.frame_index,
                        "media_type": clip.media_type,
                        "media_role": clip.media_role,
                        "source_kind": clip.source_kind,
                    }
                    for clip in visual_clips
                ],
            },
        )

    def _render_execution_plan_for_metadata(
        self,
        ctx: PipelineContext,
    ) -> dict[str, Any]:
        existing = ctx.observability.get("render_execution_plan")
        if isinstance(existing, dict):
            return existing
        if isinstance(existing, RenderExecutionPlan):
            plan = existing.to_dict()
            ctx.observability["render_execution_plan"] = plan
            return plan

        build_error: Exception | None = None
        if getattr(ctx, "master_audio_path", None):
            try:
                plan = self._build_render_execution_plan(ctx).to_dict()
            except Exception as exc:
                build_error = exc
                plan = self._build_minimal_render_execution_plan_for_metadata(
                    ctx,
                    build_error=exc,
                ).to_dict()
        else:
            plan = self._build_minimal_render_execution_plan_for_metadata(
                ctx,
            ).to_dict()

        if build_error is not None:
            logger.debug(
                "Falling back to minimal render execution plan during persistence: "
                f"{build_error}"
            )
        ctx.observability["render_execution_plan"] = plan
        return plan

    def _build_minimal_render_execution_plan_for_metadata(
        self,
        ctx: PipelineContext,
        *,
        build_error: Exception | None = None,
    ) -> RenderExecutionPlan:
        requested_backend = str(
            getattr(ctx.config, "render_backend", LEGACY_RENDER_BACKEND)
        )
        try:
            effective_backend = self._resolve_effective_render_backend(ctx)
        except Exception as exc:
            effective_backend = requested_backend
            build_error = build_error or exc

        try:
            fallback_reason = self._get_render_backend_fallback_reason(ctx)
        except Exception as exc:
            fallback_reason = getattr(ctx, "render_backend_fallback_reason", None)
            build_error = build_error or exc

        try:
            audio_strategy = self._resolve_effective_tts_audio_strategy(ctx)
        except Exception as exc:
            audio_strategy = str(
                getattr(ctx.config, "tts_audio_strategy", AUTO_TTS_AUDIO_STRATEGY)
            )
            build_error = build_error or exc

        try:
            subtitle_mode = (
                "ass" if self._caption_renderer_enabled(ctx, "ass") else "disabled"
            )
        except Exception as exc:
            subtitle_mode = "unknown"
            build_error = build_error or exc

        artifacts: list[RenderExecutionArtifact] = []
        for frame in getattr(ctx.storyboard, "frames", []) or []:
            artifact = self._minimal_render_execution_artifact_for_frame(frame)
            if artifact is not None:
                artifacts.append(artifact)

        element_motion_mode = "disabled"
        if any(artifact.role == "element_motion_video" for artifact in artifacts):
            element_motion_mode = "python_ffmpeg"
        elif getattr(ctx.config, "element_animation_enabled", False):
            element_motion_mode = str(
                getattr(ctx.config, "element_animation_backend", "manifest")
            )

        diagnostics: dict[str, Any] = {
            "plan_scope": "persistence_minimal",
            "artifact_count": len(artifacts),
        }
        if build_error is not None:
            diagnostics["full_plan_error"] = str(build_error)

        return RenderExecutionPlan(
            requested_backend=requested_backend,
            effective_backend=effective_backend,
            fallback_reason=fallback_reason,
            template_materialization_mode="unknown",
            element_motion_mode=element_motion_mode,
            subtitle_mode=subtitle_mode,
            audio_strategy=audio_strategy,
            artifacts=artifacts,
            diagnostics=diagnostics,
        )

    def _minimal_render_execution_artifact_for_frame(
        self,
        frame: StoryboardFrame,
    ) -> RenderExecutionArtifact | None:
        if getattr(frame, "element_motion_video_path", None):
            return RenderExecutionArtifact(
                role="element_motion_video",
                path=frame.element_motion_video_path,
                frame_index=frame.index,
            )
        if getattr(frame, "video_segment_path", None):
            return RenderExecutionArtifact(
                role="legacy_segment",
                path=frame.video_segment_path,
                frame_index=frame.index,
            )
        if getattr(frame, "composed_image_path", None):
            return RenderExecutionArtifact(
                role="template_frame",
                path=frame.composed_image_path,
                frame_index=frame.index,
            )
        if getattr(frame, "video_path", None):
            return RenderExecutionArtifact(
                role="raw_media",
                path=frame.video_path,
                frame_index=frame.index,
            )
        if getattr(frame, "image_path", None):
            return RenderExecutionArtifact(
                role="raw_media",
                path=frame.image_path,
                frame_index=frame.index,
            )
        return None

    def _export_ass_for_manifest_if_needed(
        self,
        ctx: PipelineContext,
        manifest: RenderManifest,
    ):
        self._get_text_rendering_result(ctx)
        text_tracks, text_cues = self._compile_text_layer_for_render(ctx)
        caption_cues = (
            self._build_caption_cues_for_render(ctx, rebuild=True)
            if self._caption_renderer_enabled(ctx, "ass")
            else []
        )
        self._update_text_render_package(
            ctx,
            caption_cues=caption_cues,
            text_tracks=text_tracks,
            text_cues=text_cues,
        )
        overlay_ass_tracks, overlay_ass_cues = self._filter_text_layer_for_renderer(
            text_tracks,
            text_cues,
            renderer="ass",
        )
        caption_ass_tracks, caption_ass_cues = self._caption_text_layer_for_renderer(
            ctx,
            caption_cues=caption_cues,
            renderer="ass",
        )
        ass_tracks = [*caption_ass_tracks, *overlay_ass_tracks]
        ass_cues = [*caption_ass_cues, *overlay_ass_cues]
        ass_outputs = None
        if ass_cues:
            ass_dir = Path(ctx.task_dir or Path(ctx.final_video_path).parent) / "text_layer"
            ass_outputs = AssTextAdapter().export(
                manifest=replace(
                    manifest,
                    caption_rendering_enabled=self._caption_renderer_enabled(ctx, "ass"),
                    caption_renderer_targets=list(
                        self._caption_renderer_targets_for_summary(ctx)
                    ),
                    caption_cues=caption_cues,
                    text_style_profiles=self._text_style_profiles_for_manifest(ctx),
                    text_tracks=ass_tracks,
                    text_cues=ass_cues,
                ),
                output_dir=ass_dir,
            )

        self._record_caption_rendering_summary(
            ctx,
            enabled=bool(caption_ass_cues),
            caption_cue_count=len(caption_ass_cues),
            style_profile=self._caption_style_profile_for_summary(ctx),
            renderer_targets=self._caption_renderer_targets_for_summary(ctx),
            artifacts=self._ass_caption_artifacts(ass_outputs),
            fallbacks=self._ass_export_fallbacks(ass_outputs),
        )
        self._record_text_layer_summary(
            ctx,
            renderer="ass" if overlay_ass_cues else "disabled",
            text_tracks=overlay_ass_tracks,
            text_cues=overlay_ass_cues,
            native_hint_count=self._count_native_prompt_hints(ctx),
            artifacts=(
                self._ass_text_layer_artifacts(ass_outputs)
                if overlay_ass_cues
                else {}
            ),
            fallbacks=(
                self._ass_export_fallbacks(ass_outputs)
                if overlay_ass_cues
                else ()
            ),
        )
        return ass_outputs

    async def _post_production_hyperframes(self, ctx: PipelineContext):
        self._report_progress(ctx.progress_callback, ProgressEventType.RENDERING_HYPERFRAMES, 0.85)

        storyboard = ctx.storyboard
        config = ctx.config
        timing_plan = ctx.timing_plan

        if timing_plan is None:
            raise RuntimeError("HyperFrames render path requires a timing plan.")
        if self.core.hyperframes_project_service is None or self.core.hyperframes_renderer is None:
            raise RuntimeError("HyperFrames services are not initialized.")
        if getattr(self.core, "alignment_service", None) is None:
            raise RuntimeError("Alignment service is not initialized.")
        if config.silence_trim_tool == "auto_editor" and getattr(self.core, "audio_edit_service", None) is None:
            raise RuntimeError("Audio edit service is not initialized.")

        master_audio_path, master_audio_duration = await self._synthesize_hyperframes_audio(ctx)
        self._align_hyperframes_timing_plan(ctx)
        self._offset_sentence_timings_to_master_timeline(timing_plan)

        if config.silence_trim_tool == "auto_editor":
            trim_result = self.core.audio_edit_service.export_trimmed_audio_and_timeline(
                master_audio_path,
                str(Path(master_audio_path).with_name("trimmed_master_audio.wav")),
                margin_ms=config.silence_trim_margin_ms,
            )
            master_audio_path = trim_result.trimmed_audio_path
            master_audio_duration = self._get_audio_duration(master_audio_path)
            self._remap_timing_plan_to_auto_editor_timeline(timing_plan, trim_result.timeline)
            self.core.audio_edit_service.remap_sentence_units(
                timing_plan.sentences,
                trim_result.timeline,
            )

        if timing_plan.blocks:
            timing_plan.blocks[-1].end = master_audio_duration
        storyboard.total_duration = master_audio_duration
        canvas_width, canvas_height = self._resolve_hyperframes_canvas_size(config)
        self._get_text_rendering_result(ctx)
        compiled_text_tracks, compiled_text_cues = self._compile_text_layer_for_render(ctx)
        caption_cues = (
            self._build_caption_cues_for_render(ctx, rebuild=True)
            if self._caption_renderer_enabled(ctx, "hyperframes")
            else []
        )
        hyperframes_caption_cues = self._caption_cues_for_renderer(
            ctx,
            caption_cues=caption_cues,
            renderer="hyperframes",
        )
        self._update_text_render_package(
            ctx,
            caption_cues=caption_cues,
            text_tracks=compiled_text_tracks,
            text_cues=compiled_text_cues,
        )
        text_tracks, text_cues = self._filter_text_layer_for_renderer(
            compiled_text_tracks,
            compiled_text_cues,
            renderer="hyperframes",
        )
        audio_tracks = self._build_hyperframes_audio_tracks(
            ctx,
            master_audio_path=master_audio_path,
            master_audio_duration=master_audio_duration,
        )
        visual_clips = self._build_hyperframes_visual_clips(storyboard, timing_plan)
        await self._materialize_element_motion_for_hyperframes_visual_clips(
            ctx,
            visual_clips,
        )
        visual_clips = self._build_hyperframes_visual_clips(storyboard, timing_plan)

        manifest = RenderManifest(
            task_id=ctx.task_id,
            title=storyboard.title,
            canvas_width=canvas_width,
            canvas_height=canvas_height,
            media_width=config.media_width,
            media_height=config.media_height,
            sync_media_size_to_canvas=config.sync_media_size_to_canvas,
            media_layout_mode=config.media_layout_mode,
            media_placement=config.media_placement,
            fps=config.video_fps,
            template_id=self._resolve_hyperframes_template_id(config),
            master_audio_path=master_audio_path,
            master_audio_duration=master_audio_duration,
            audio_tracks=audio_tracks,
            audio_blocks=list(timing_plan.blocks),
            sentence_units=list(timing_plan.sentences),
            visual_clips=visual_clips,
            caption_rendering_enabled=self._caption_renderer_enabled(ctx, "hyperframes"),
            caption_renderer_targets=list(
                self._caption_renderer_targets_for_summary(ctx)
            ),
            caption_cues=hyperframes_caption_cues,
            text_style_profiles=self._text_style_profiles_for_manifest(ctx),
            text_tracks=text_tracks,
            text_cues=text_cues,
            caption_punctuation_mode=self._caption_punctuation_mode_for_manifest(ctx),
            canonical_timeline=(
                "remapped"
                if any(
                    sentence.remapped_start is not None and sentence.remapped_end is not None
                    for sentence in timing_plan.sentences
                )
                else "source"
            ),
        )
        ctx.observability["render_execution_plan"] = self._build_render_execution_plan(
            ctx,
            manifest=manifest,
        ).to_dict()
        self._record_text_layer_summary(
            ctx,
            renderer="hyperframes",
            text_tracks=text_tracks,
            text_cues=text_cues,
            native_hint_count=self._count_native_prompt_hints(ctx),
        )
        project_paths = self.core.hyperframes_project_service.write_project(
            manifest,
            template_params=storyboard.config.template_params or {},
            master_audio_duration=master_audio_duration,
        )
        self._record_caption_rendering_summary(
            ctx,
            enabled=bool(hyperframes_caption_cues),
            caption_cue_count=len(hyperframes_caption_cues),
            style_profile=self._caption_style_profile_for_summary(ctx),
            renderer_targets=self._caption_renderer_targets_for_summary(ctx),
            artifacts=(
                {"captions_json": str(project_paths.captions_path)}
                if hyperframes_caption_cues
                else {}
            ),
        )

        final_video_path = self.core.hyperframes_renderer.render(
            str(project_paths.project_dir),
            output_path=ctx.final_video_path,
            width=canvas_width,
            height=canvas_height,
            fps=config.video_fps,
            expected_duration=master_audio_duration,
            expect_audio=bool(master_audio_path),
        )

        storyboard.final_video_path = final_video_path
        storyboard.completed_at = datetime.now()

        user_specified_output = ctx.params.get("output_path")
        if user_specified_output:
            Path(user_specified_output).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(final_video_path, user_specified_output)
            logger.info(f"Copied final video to user path: {user_specified_output}")
            ctx.final_video_path = user_specified_output
            storyboard.final_video_path = user_specified_output
        else:
            ctx.final_video_path = final_video_path
            storyboard.final_video_path = final_video_path

        logger.success(f"HyperFrames video generation completed: {ctx.final_video_path}")

    async def _materialize_element_motion_for_hyperframes_visual_clips(
        self,
        ctx: PipelineContext,
        visual_clips: list[VisualClip],
    ) -> None:
        if not getattr(ctx.config, "element_animation_enabled", False):
            return
        if not visual_clips:
            return

        frames_by_index = {
            frame.index: frame
            for frame in getattr(ctx.storyboard, "frames", []) or []
        }
        for clip in visual_clips:
            frame = frames_by_index.get(clip.frame_index)
            if frame is None:
                continue

            frame.duration = max(float(clip.end) - float(clip.start), 0.001)
            await self._materialize_element_motion_for_frame(ctx, frame)

    def _build_hyperframes_audio_tracks(
        self,
        ctx: PipelineContext,
        *,
        master_audio_path: str,
        master_audio_duration: float,
    ) -> list[RenderAudioTrack]:
        duration = max(float(master_audio_duration), 0.0)
        tracks = [
            RenderAudioTrack(
                id="narration-audio",
                path=master_audio_path,
                start=0.0,
                end=duration,
                volume=1.0,
                role="narration",
            )
        ]

        bgm_path = ctx.params.get("bgm_path")
        if not bgm_path:
            return tracks

        bgm_output_path = str(Path(master_audio_path).with_name("background_audio.wav"))
        prepared_bgm_path = self._prepare_bgm_audio_for_hyperframes(
            bgm_path,
            bgm_output_path,
            duration=duration,
            mode=ctx.params.get("bgm_mode", "loop"),
        )
        tracks.append(
            RenderAudioTrack(
                id="background-audio",
                path=prepared_bgm_path,
                start=0.0,
                end=duration,
                volume=float(ctx.params.get("bgm_volume", 0.2)),
                role="background",
            )
        )
        return tracks

    def _prepare_bgm_audio_for_hyperframes(
        self,
        input_path: str,
        output_path: str,
        *,
        duration: float,
        mode: str,
    ) -> str:
        resolved_bgm = VideoService().resolve_bgm_path(input_path)
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        command = ["ffmpeg"]
        if mode == "loop":
            command.extend(["-stream_loop", "-1"])
        command.extend(
            [
                "-i",
                resolved_bgm,
                "-t",
                self._format_ffmpeg_time(duration),
                "-c:a",
                "pcm_s16le",
                "-y",
                output_path,
            ]
        )
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip() or "unknown error"
            raise RuntimeError(f"Failed to prepare HyperFrames BGM audio: {detail}")
        return output_path

    def _get_text_rendering_result(self, ctx: PipelineContext):
        existing = getattr(ctx, "text_rendering_result", None)
        if existing is not None:
            return existing

        frame_texts = self._text_rendering_frame_texts(ctx)
        config = getattr(ctx, "config", None)
        template_id = None
        if config is not None:
            try:
                template_id = self._resolve_hyperframes_template_id(config)
            except Exception as exc:
                template_id = getattr(config, "frame_template", None)
                logger.warning(
                    "Falling back to frame_template for text rendering template "
                    f"style defaults after template resolution failed: {exc}"
                )
        result = TextRenderingOrchestrator().build(
            text_rendering=self._text_rendering_request_for_contract(ctx),
            narrations=frame_texts,
            render_backend=self._resolve_text_rendering_backend_label(ctx),
            frame_count=len(frame_texts),
            task_id=getattr(ctx, "task_id", None),
            config=config,
            template_id=template_id,
        )
        setattr(ctx, "text_rendering_result", result)
        self._set_text_render_package(ctx, result.text_render_package)
        self._attach_text_rendering_contract_to_creation_package(ctx, result)
        return result

    def _text_rendering_request_for_contract(self, ctx: PipelineContext) -> dict:
        params = getattr(ctx, "params", {}) or {}
        payload = dict(params.get("text_rendering") or {})
        caption_payload = dict(payload.get("caption") or {})

        if "punctuation_mode" not in caption_payload:
            punctuation_mode = self._caption_punctuation_mode_from_context(ctx)
            if punctuation_mode:
                caption_payload["punctuation_mode"] = punctuation_mode

        if caption_payload:
            payload["caption"] = caption_payload
        return payload

    def _prompt_text_rendering_request(self, ctx: PipelineContext) -> dict | None:
        params = getattr(ctx, "params", {}) or {}
        return project_prompt_text_rendering_request(params.get("text_rendering"))

    def _caption_punctuation_mode_from_context(self, ctx: PipelineContext) -> str | None:
        params = getattr(ctx, "params", {}) or {}
        if params.get("caption_punctuation_mode") is not None:
            return str(params["caption_punctuation_mode"])

        config = getattr(ctx, "config", None)
        if config is not None and getattr(config, "caption_punctuation_mode", None):
            return str(config.caption_punctuation_mode)
        return None

    def _text_rendering_frame_texts(self, ctx: PipelineContext) -> list[str]:
        storyboard_plan = getattr(ctx, "storyboard_plan", None)
        if storyboard_plan is not None:
            return [frame.source_text for frame in storyboard_plan.frames]
        storyboard = getattr(ctx, "storyboard", None)
        return [
            str(getattr(frame, "narration", "") or "")
            for frame in getattr(storyboard, "frames", []) or []
        ]

    def _resolve_text_rendering_backend_label(self, ctx: PipelineContext) -> str | None:
        config = getattr(ctx, "config", None)
        if config is None:
            return getattr(ctx, "params", {}).get("render_backend")

        try:
            return self._resolve_effective_render_backend(ctx)
        except Exception:
            return getattr(config, "render_backend", None)

    def _get_text_render_package(self, ctx: PipelineContext):
        package = getattr(ctx, "text_render_package", None)
        if package is not None:
            return package
        return self._get_text_rendering_result(ctx).text_render_package

    def _set_text_render_package(self, ctx: PipelineContext, package) -> None:
        setattr(ctx, "text_render_package", package)
        self._persist_text_render_package(ctx, package)

    def _attach_text_rendering_contract_to_creation_package(
        self,
        ctx: PipelineContext,
        result,
    ) -> None:
        existing = getattr(ctx, "creation_package", None)
        prompt_plan = dict(getattr(existing, "prompt_plan", {}) or {})
        prompt_plan["text_rendering_policy"] = result.overlay_policy.to_dict()
        if getattr(ctx, "task_dir", None):
            prompt_plan["text_render_package"] = TEXT_RENDER_PACKAGE_ARTIFACT_PATH

        if existing is None:
            ctx.creation_package = CreationPackage(
                task_id=getattr(ctx, "task_id", None) or "",
                text_overlay_plan=result.overlay_plan,
                prompt_plan=prompt_plan,
            )
            return

        text_overlay_plan = (
            existing.text_overlay_plan
            if existing.text_overlay_plan is not None
            else result.overlay_plan
        )
        ctx.creation_package = replace(
            existing,
            text_overlay_plan=text_overlay_plan,
            prompt_plan=prompt_plan,
        )

    def _persist_text_render_package(self, ctx: PipelineContext, package) -> None:
        task_dir = getattr(ctx, "task_dir", None)
        if not task_dir:
            return

        package_path = Path(task_dir) / TEXT_RENDER_PACKAGE_ARTIFACT_PATH
        package_path.parent.mkdir(parents=True, exist_ok=True)
        package_path.write_text(
            json.dumps(package.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _update_text_render_package(
        self,
        ctx: PipelineContext,
        *,
        caption_cues=None,
        text_tracks=None,
        text_cues=None,
    ):
        package = self._get_text_render_package(ctx)
        updated = replace(
            package,
            caption_cues=(
                tuple(caption_cues)
                if caption_cues is not None
                else package.caption_cues
            ),
            text_tracks=(
                tuple(text_tracks)
                if text_tracks is not None
                else package.text_tracks
            ),
            text_cues=(
                tuple(text_cues)
                if text_cues is not None
                else package.text_cues
            ),
        )
        self._set_text_render_package(ctx, updated)
        existing_result = getattr(ctx, "text_rendering_result", None)
        if existing_result is not None:
            setattr(
                ctx,
                "text_rendering_result",
                replace(
                    existing_result,
                    text_render_package=updated,
                    diagnostics=updated.diagnostics,
                ),
            )
        return updated

    def _text_style_profiles_for_manifest(self, ctx: PipelineContext) -> list:
        return list(self._get_text_render_package(ctx).text_style_profiles)

    def _caption_style_profile_for_summary(self, ctx: PipelineContext):
        package = self._get_text_render_package(ctx)
        style_profile_id = package.caption_settings.style_profile
        return next(
            (
                profile
                for profile in package.text_style_profiles
                if profile.id == style_profile_id
            ),
            style_profile_id,
        )

    def _caption_renderer_targets_for_summary(
        self,
        ctx: PipelineContext,
    ) -> tuple[str, ...]:
        return self._get_text_render_package(ctx).caption_settings.renderer_targets

    def _caption_renderer_enabled(self, ctx: PipelineContext, renderer: str) -> bool:
        settings = self._get_text_render_package(ctx).caption_settings
        return settings.enabled and renderer in settings.renderer_targets

    def _caption_punctuation_mode_for_manifest(self, ctx: PipelineContext) -> str:
        return self._get_text_render_package(ctx).caption_settings.punctuation_mode

    def _build_caption_cues_for_render(
        self,
        ctx: PipelineContext,
        *,
        rebuild: bool = False,
    ) -> list[CaptionCue]:
        package = self._get_text_render_package(ctx)
        if not package.caption_settings.enabled:
            return []
        if package.caption_cues and not rebuild:
            return list(package.caption_cues)

        timing_plan = getattr(ctx, "timing_plan", None)
        sentences = list(getattr(timing_plan, "sentences", []) or [])
        if not sentences:
            return []
        return build_caption_cues_from_sentences(
            sentences,
            style_profile=package.caption_settings.style_profile,
            punctuation_mode=package.caption_settings.punctuation_mode,
        )

    def _caption_cues_for_renderer(
        self,
        ctx: PipelineContext,
        *,
        caption_cues: list[CaptionCue],
        renderer: str,
    ) -> list[CaptionCue]:
        if not self._caption_renderer_enabled(ctx, renderer):
            return []
        return list(caption_cues)

    def _caption_text_layer_for_renderer(
        self,
        ctx: PipelineContext,
        *,
        caption_cues: list[CaptionCue],
        renderer: str,
    ) -> tuple[list[TextTrack], list[TextCue]]:
        package = self._get_text_render_package(ctx)
        settings = package.caption_settings
        if (
            not settings.enabled
            or renderer not in settings.renderer_targets
            or not caption_cues
        ):
            return [], []

        track = TextTrack(
            id=f"track-{renderer}-captions",
            kind="caption",
            name="Captions",
            renderer_targets=(renderer,),
            style_profile=settings.style_profile,
            layer=0,
        )
        cues = [
            TextCue(
                id=f"{renderer}-caption-{cue.id}",
                track_id=track.id,
                text=cue.text,
                start=cue.start,
                end=cue.end,
                role="subtitle",
                frame_indices=tuple(cue.frame_indices),
                style_profile=cue.style_profile or settings.style_profile,
                layer=0,
                source={"caption_cue_id": cue.id},
            )
            for cue in caption_cues
        ]
        return [track], cues

    def _ass_caption_artifacts(self, ass_outputs) -> dict[str, str]:
        if ass_outputs is None or getattr(ass_outputs, "subtitle_only", None) is None:
            return {}
        return {"subtitle_only_ass": str(ass_outputs.subtitle_only)}

    def _ass_text_layer_artifacts(self, ass_outputs) -> dict[str, str]:
        if ass_outputs is None:
            return {}
        artifacts = {}
        if getattr(ass_outputs, "master", None) is not None:
            artifacts["master_ass"] = str(ass_outputs.master)
        if getattr(ass_outputs, "overlay_only", None) is not None:
            artifacts["overlay_only_ass"] = str(ass_outputs.overlay_only)
        return artifacts

    def _ass_export_fallbacks(self, ass_outputs) -> list:
        diagnostics = getattr(ass_outputs, "diagnostics", None) or {}
        return list(diagnostics.get("fallbacks", []) or [])

    def _compile_text_layer_for_render(self, ctx: PipelineContext):
        package = getattr(ctx, "creation_package", None)
        timing_plan = getattr(ctx, "timing_plan", None)
        if package is None or package.text_overlay_plan is None or timing_plan is None:
            return [], []
        return TextCueCompiler().compile(
            package=package,
            sentence_units=list(getattr(timing_plan, "sentences", []) or []),
            frame_windows=self._build_text_layer_frame_windows(ctx),
        )

    def _build_text_layer_frame_windows(self, ctx: PipelineContext) -> dict[int, tuple[float, float]]:
        storyboard = getattr(ctx, "storyboard", None)
        frames = list(getattr(storyboard, "frames", []) or [])
        if not frames:
            return {}

        windows: dict[int, tuple[float, float]] = {}
        cursor = 0.0
        for frame in frames:
            try:
                duration = float(getattr(frame, "duration", 0.0) or 0.0)
            except (TypeError, ValueError):
                duration = 0.0
            if duration <= 0:
                continue
            frame_index = int(getattr(frame, "index", len(windows)))
            windows[frame_index] = (cursor, cursor + duration)
            cursor += duration
        return windows

    def _filter_text_layer_for_renderer(self, text_tracks, text_cues, *, renderer: str):
        filtered_tracks = [
            track for track in text_tracks if renderer in track.renderer_targets
        ]
        track_ids = {track.id for track in filtered_tracks}
        filtered_cues = [cue for cue in text_cues if cue.track_id in track_ids]
        return filtered_tracks, filtered_cues

    def _count_native_prompt_hints(self, ctx: PipelineContext) -> int:
        package = getattr(ctx, "creation_package", None)
        plan = getattr(package, "text_overlay_plan", None)
        if plan is None:
            return 0
        return sum(
            1
            for candidate in plan.candidates
            if candidate.role == "model_native_hint"
            and "native_prompt" in candidate.renderer_targets
        )

    def _record_text_layer_summary(
        self,
        ctx: PipelineContext,
        *,
        renderer: str,
        text_tracks,
        text_cues,
        native_hint_count: int = 0,
        artifacts: dict | None = None,
        fallbacks=(),
    ) -> None:
        overlay_tracks = [
            track
            for track in text_tracks
            if getattr(track, "kind", None) not in {"caption", "subtitle"}
        ]
        overlay_track_ids = {track.id for track in overlay_tracks}
        overlay_cues = [
            cue
            for cue in text_cues
            if getattr(cue, "role", None) not in {"caption", "subtitle"}
            and getattr(cue, "track_id", None) in overlay_track_ids
        ]
        style_profile_ids = sorted(
            {
                style_profile
                for style_profile in (
                    [
                        getattr(track, "style_profile", None)
                        for track in overlay_tracks
                    ]
                    + [
                        getattr(cue, "style_profile", None)
                        for cue in overlay_cues
                    ]
                )
                if style_profile
            }
        )
        text_rendering_result = getattr(ctx, "text_rendering_result", None)
        title_style = getattr(text_rendering_result, "title_style", None)
        ctx.observability["text_layer_summary"] = {
            "enabled": bool(overlay_tracks or overlay_cues or native_hint_count),
            "renderer": renderer,
            "track_count": len(overlay_tracks),
            "cue_count": len(overlay_cues),
            "native_prompt_hint_count": native_hint_count,
            "style_profile_ids": style_profile_ids,
            "title_style_profile_id": getattr(
                title_style, "id", DEFAULT_TITLE_STYLE_ID
            ),
            "artifacts": dict(artifacts or {}),
            "fallbacks": [dict(item) if isinstance(item, dict) else item for item in fallbacks],
            "targets": sorted(
                {
                    target
                    for track in overlay_tracks
                    for target in track.renderer_targets
                }
            ),
        }

    def _record_caption_rendering_summary(
        self,
        ctx: PipelineContext,
        *,
        enabled: bool | None = None,
        caption_cue_count: int,
        style_profile,
        renderer_targets,
        artifacts: dict | None,
        fallbacks=(),
    ) -> None:
        ctx.observability["caption_rendering_summary"] = {
            "enabled": bool(caption_cue_count) if enabled is None else bool(enabled),
            "caption_cue_count": int(caption_cue_count),
            "style_profile_id": getattr(style_profile, "id", style_profile),
            "renderer_targets": sorted(str(target) for target in renderer_targets),
            "artifacts": dict(artifacts or {}),
            "fallbacks": [dict(item) if isinstance(item, dict) else item for item in fallbacks],
        }

    def _align_hyperframes_timing_plan(self, ctx: PipelineContext) -> None:
        engine = (ctx.config.subtitle_alignment_engine or "qwen_forced_aligner").strip().lower()
        timing_plan = ctx.timing_plan

        if engine == "qwen_forced_aligner":
            self.core.alignment_service.align_blocks(timing_plan.blocks, timing_plan.sentences)
            return

        if engine == "direct_duration":
            self.core.alignment_service.align_blocks_by_duration(
                timing_plan.blocks,
                timing_plan.sentences,
            )
            return

        if engine in {"hyperframes_transcribe", "transcribe"}:
            raise NotImplementedError(
                "subtitle_alignment_engine='hyperframes_transcribe' is not implemented yet."
            )

        raise ValueError(f"Unsupported subtitle_alignment_engine: {ctx.config.subtitle_alignment_engine!r}")

    async def _synthesize_hyperframes_audio(self, ctx: PipelineContext) -> tuple[str, float]:
        task_id = ctx.task_id or ctx.config.task_id
        if ctx.task_dir:
            task_audio_dir = Path(ctx.task_dir) / "audio"
        else:
            task_audio_dir = Path(get_task_path(task_id, "audio"))
        task_audio_dir.mkdir(parents=True, exist_ok=True)

        block_paths: List[str] = []
        cursor = 0.0

        async with _maybe_local_comfyui_workflow_session(
            self.core,
            release_after_session=True,
        ):
            for block in ctx.timing_plan.blocks:
                block_output_path = task_audio_dir / f"{block.id}.wav"
                normalized_audio_path = await self._synthesize_audio_block(
                    ctx,
                    block_id=block.id,
                    block_text=block.text,
                    task_audio_dir=task_audio_dir,
                    block_output_path=block_output_path,
                )
                block.audio_path = normalized_audio_path
                duration = self._get_audio_duration(block.audio_path)
                block.start = cursor
                block.end = cursor + duration
                cursor = block.end
                block_paths.append(block.audio_path)

        master_audio_path = task_audio_dir / "master_audio.wav"
        self._concat_audio_files(
            block_paths,
            str(master_audio_path),
            fade_ms=ctx.config.tts_audio_boundary_fade_ms,
        )
        master_audio_duration = self._get_audio_duration(str(master_audio_path))

        return str(master_audio_path), master_audio_duration

    async def _synthesize_audio_block(
        self,
        ctx: PipelineContext,
        *,
        block_id: str,
        block_text: str,
        task_audio_dir: Path,
        block_output_path: Path,
    ) -> str:
        segments = [block_text]
        if (
            self._uses_index_tts2_workflow(ctx.config)
            and ctx.config.tts_split_mode != INTERNAL_ONLY_TTS_SPLIT_MODE
        ):
            plan = build_external_tts_segmentation_plan(
                block_text,
                max_chars_per_segment=ctx.config.max_chars_per_tts_segment,
                boundary_search_radius=ctx.config.tts_boundary_search_radius,
                soft_overflow_chars=ctx.config.tts_soft_overflow_chars,
                source_unit_type="audio_block",
                source_unit_id=block_id,
                overflow_policy=ctx.config.tts_split_overflow_policy,
            )
            self._record_tts_segmentation_plan(ctx, plan)
            segments = [segment.text for segment in plan.segments] or [block_text]

        source_extension = self._resolve_tts_source_extension(ctx.config)
        if len(segments) == 1:
            block_source_path = task_audio_dir / f"{block_id}_source{source_extension}"
            tts_params = self._build_tts_params(
                config=ctx.config,
                text=segments[0],
                output_path=str(block_source_path),
            )
            self._record_tts_workflow_text(ctx, block_id, 1, tts_params)
            await self.core.tts(**tts_params)
            return self._normalize_audio_for_hyperframes(
                str(block_source_path),
                str(block_output_path),
            )

        segment_paths: List[str] = []
        for index, segment_text in enumerate(segments, start=1):
            segment_source_path = task_audio_dir / (
                f"{block_id}_segment_{index}_source{source_extension}"
            )
            segment_output_path = task_audio_dir / f"{block_id}_segment_{index}.wav"
            tts_params = self._build_tts_params(
                config=ctx.config,
                text=segment_text,
                output_path=str(segment_source_path),
            )
            self._record_tts_workflow_text(ctx, block_id, index, tts_params)
            await self.core.tts(**tts_params)
            segment_paths.append(
                self._normalize_audio_for_hyperframes(
                    str(segment_source_path),
                    str(segment_output_path),
                )
            )

        self._concat_audio_files(
            segment_paths,
            str(block_output_path),
            fade_ms=ctx.config.tts_audio_boundary_fade_ms,
        )
        return str(block_output_path)

    def _build_tts_params(
        self,
        *,
        config: StoryboardConfig,
        text: str,
        output_path: str,
    ) -> dict:
        tts_params = {
            "text": text,
            "inference_mode": config.tts_inference_mode,
            "output_path": output_path,
        }

        if config.tts_inference_mode == "local":
            if config.voice_id:
                tts_params["voice"] = config.voice_id
            if config.tts_speed is not None:
                tts_params["speed"] = config.tts_speed
        else:
            if config.tts_workflow:
                tts_params["workflow"] = config.tts_workflow
            if config.voice_id:
                tts_params["voice"] = config.voice_id
            if config.tts_speed is not None:
                tts_params["speed"] = config.tts_speed
            if config.ref_audio:
                tts_params["ref_audio"] = config.ref_audio
            if config.ref_audio_text:
                tts_params["ref_audio_text"] = config.ref_audio_text

        return tts_params

    def _record_tts_segmentation_plan(self, ctx: PipelineContext, plan) -> None:
        segmentation = ctx.observability.setdefault(
            "tts_segmentation",
            {
                "version": "v1",
                "plans": [],
            },
        )
        segmentation.setdefault("plans", []).append(plan.to_dict())

    def _record_tts_workflow_text(
        self,
        ctx: PipelineContext,
        block_id: str,
        segment_index: int,
        tts_params: dict,
    ) -> None:
        synthesis = ctx.observability.setdefault(
            "tts_synthesis",
            {
                "version": "v1",
                "calls": [],
            },
        )
        synthesis.setdefault("calls", []).append(
            {
                "block_id": block_id,
                "segment_index": segment_index,
                "workflow": tts_params.get("workflow"),
                "workflow_params_text": tts_params.get("text", ""),
                "output_path": tts_params.get("output_path"),
            }
        )

    def _concat_audio_files(self, audio_paths: List[str], output_path: str, *, fade_ms: int = 0) -> None:
        if not audio_paths:
            raise ValueError("HyperFrames audio synthesis requires at least one block.")

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        if len(audio_paths) == 1:
            shutil.copy2(audio_paths[0], output_path)
            return

        fade_duration = max(float(fade_ms), 0.0) / 1000.0
        if fade_duration > 0:
            self._concat_audio_files_with_boundary_fade(audio_paths, output_path, fade_duration)
            return

        from tempfile import NamedTemporaryFile

        filelist_path = ""
        try:
            with NamedTemporaryFile(
                mode="w",
                delete=False,
                suffix=".txt",
                encoding="utf-8",
                dir=get_temp_path(),
            ) as handle:
                filelist_path = handle.name
                for audio_path in audio_paths:
                    escaped_path = str(Path(audio_path).resolve()).replace("'", "'\\''")
                    handle.write(f"file '{escaped_path}'\n")

            completed = subprocess.run(
                [
                    "ffmpeg",
                    "-f",
                    "concat",
                    "-safe",
                    "0",
                    "-i",
                    filelist_path,
                    "-c:a",
                    "pcm_s16le",
                    "-y",
                    output_path,
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if completed.returncode != 0:
                detail = completed.stderr.strip() or completed.stdout.strip() or "unknown error"
                raise RuntimeError(f"Failed to concatenate HyperFrames audio: {detail}")
        finally:
            if filelist_path and os.path.exists(filelist_path):
                os.remove(filelist_path)

    def _concat_audio_files_with_boundary_fade(
        self,
        audio_paths: List[str],
        output_path: str,
        fade_duration: float,
    ) -> None:
        command = ["ffmpeg"]
        filter_parts: List[str] = []
        labels: List[str] = []

        for index, audio_path in enumerate(audio_paths):
            command.extend(["-i", audio_path])
            duration = max(self._get_audio_duration(audio_path), 0.01)
            boundary_fade = min(fade_duration, duration / 4)
            filters = ["aresample=async=1:first_pts=0"]

            if index > 0:
                filters.append(f"afade=t=in:st=0:d={self._format_ffmpeg_time(boundary_fade)}")
            if index < len(audio_paths) - 1:
                fade_out_start = max(duration - boundary_fade, 0.0)
                filters.append(
                    "afade=t=out:"
                    f"st={self._format_ffmpeg_time(fade_out_start)}:"
                    f"d={self._format_ffmpeg_time(boundary_fade)}"
                )

            label = f"a{index}"
            filter_parts.append(f"[{index}:a]{','.join(filters)}[{label}]")
            labels.append(f"[{label}]")

        filter_complex = (
            ";".join(filter_parts)
            + f";{''.join(labels)}concat=n={len(audio_paths)}:v=0:a=1[out]"
        )
        command.extend(
            [
                "-filter_complex",
                filter_complex,
                "-map",
                "[out]",
                "-c:a",
                "pcm_s16le",
                "-y",
                output_path,
            ]
        )

        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip() or "unknown error"
            raise RuntimeError(f"Failed to concatenate HyperFrames audio with boundary fade: {detail}")

    def _normalize_audio_for_hyperframes(self, input_path: str, output_path: str) -> str:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        completed = subprocess.run(
            [
                "ffmpeg",
                "-i",
                input_path,
                "-c:a",
                "pcm_s16le",
                "-y",
                output_path,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip() or "unknown error"
            raise RuntimeError(f"Failed to normalize HyperFrames audio: {detail}")
        return output_path

    def _get_audio_duration(self, audio_path: str) -> float:
        try:
            import ffmpeg

            probe = ffmpeg.probe(audio_path)
            return float(probe["format"]["duration"])
        except Exception as exc:
            logger.warning(f"Failed to get audio duration for {audio_path}: {exc}, using estimate")
            file_size = os.path.getsize(audio_path)
            estimated_duration = file_size / 2000
            return max(1.0, estimated_duration)

    def _offset_sentence_timings_to_master_timeline(self, timing_plan) -> None:
        block_lookup = {block.id: block for block in timing_plan.blocks}
        for sentence in timing_plan.sentences:
            block = block_lookup.get(sentence.block_id)
            if block is None:
                continue
            if sentence.source_start is not None:
                sentence.source_start += block.start
            if sentence.source_end is not None:
                sentence.source_end += block.start

    def _build_hyperframes_visual_clips(
        self,
        storyboard: Storyboard,
        timing_plan,
    ) -> List[VisualClip]:
        clip_specs: List[dict] = []
        frame_timing_windows = {
            window.frame_index: window
            for window in allocate_frame_timing_windows(
                frame_count=len(storyboard.frames),
                sentence_units=getattr(timing_plan, "sentences", []) or [],
            )
        }

        for frame in storyboard.frames:
            window = frame_timing_windows.get(frame.index)
            if window is None:
                continue

            if frame.media_type == "video":
                raw_media_path = frame.video_path or frame.image_path
            else:
                raw_media_path = frame.image_path or frame.video_path
            media_path = raw_media_path
            if frame.media_type:
                media_type = frame.media_type
            else:
                media_type = "video" if raw_media_path == frame.video_path else "image"
            source_kind = "raw_media"
            media_role = "foreground"
            source_media_path = None

            if getattr(frame, "element_motion_video_path", None):
                media_path = frame.element_motion_video_path
                media_type = "video"
                source_kind = "element_motion_video"
                media_role = "final_frame"
                source_media_path = raw_media_path

            if not media_path:
                missing_media_label = (
                    "media"
                    if getattr(frame, "element_motion_video_path", None)
                    else "raw media"
                )
                logger.warning(
                    "Skipping HyperFrames visual clip for frame "
                    f"{frame.index + 1}: missing {missing_media_label}"
                )
                continue

            clip_specs.append(
                {
                    "frame_index": frame.index,
                    "raw_start": max(float(window.start), 0.0),
                    "raw_end": max(float(window.end), float(window.start)),
                    "media_path": media_path,
                    "media_type": media_type,
                    "source_kind": source_kind,
                    "media_role": media_role,
                    "element_animation_manifest_path": getattr(
                        frame,
                        "element_animation_manifest_path",
                        None,
                    ),
                    "source_media_path": source_media_path,
                }
            )

        if not clip_specs:
            return []

        duration_candidates = [float(storyboard.total_duration or 0.0)]
        duration_candidates.extend(
            float(block.end)
            for block in getattr(timing_plan, "blocks", [])
            if getattr(block, "end", None) is not None
        )
        duration_candidates.extend(spec["raw_end"] for spec in clip_specs)
        total_duration = max(duration_candidates, default=0.0)

        visual_clips: List[VisualClip] = []
        previous_boundary = 0.0

        for index, spec in enumerate(clip_specs):
            clip_start = previous_boundary if index > 0 else 0.0

            if index + 1 < len(clip_specs):
                next_raw_start = float(clip_specs[index + 1]["raw_start"])
                candidate_boundary = next_raw_start if next_raw_start > clip_start else spec["raw_end"]
                clip_end = max(candidate_boundary, clip_start + 0.001)
            else:
                clip_end = max(total_duration, spec["raw_end"], clip_start + 0.001)

            previous_boundary = clip_end
            visual_clips.append(
                VisualClip(
                    id=f"clip-{spec['frame_index'] + 1}",
                    frame_index=spec["frame_index"],
                    start=clip_start,
                    end=clip_end,
                    media_path=spec["media_path"],
                    media_type=spec["media_type"],
                    source_kind=spec["source_kind"],
                    media_role=spec["media_role"],
                    element_animation_manifest_path=spec[
                        "element_animation_manifest_path"
                    ],
                    source_media_path=spec["source_media_path"],
                )
            )

        return visual_clips

    def _remap_timing_plan_to_auto_editor_timeline(self, timing_plan, timeline) -> None:
        for block in timing_plan.blocks:
            remapped_start = timeline.remap_time(block.start)
            remapped_end = timeline.remap_time(block.end)
            if remapped_start is not None:
                block.start = remapped_start
            if remapped_end is not None:
                block.end = remapped_end

    async def finalize(self, ctx: PipelineContext) -> VideoGenerationResult:
        """Step 8: Create result object and persist metadata."""
        self._report_progress(ctx.progress_callback, ProgressEventType.COMPLETED, 1.0)
        
        video_path_obj = Path(ctx.final_video_path)
        file_size = video_path_obj.stat().st_size
        
        result = VideoGenerationResult(
            video_path=ctx.final_video_path,
            storyboard=ctx.storyboard,
            duration=ctx.storyboard.total_duration,
            file_size=file_size
        )
        
        ctx.result = result
        
        logger.info(f"✅ Generated video: {ctx.final_video_path}")
        logger.info(f"   Duration: {ctx.storyboard.total_duration:.2f}s")
        logger.info(f"   Size: {file_size / (1024*1024):.2f} MB")
        logger.info(f"   Frames: {len(ctx.storyboard.frames)}")
        
        # Persist metadata
        await self._persist_task_data(ctx)
        
        return result

    async def _persist_task_data(self, ctx: PipelineContext):
        """
        Persist task metadata and storyboard to filesystem
        """
        try:
            storyboard = ctx.storyboard
            result = ctx.result
            task_id = storyboard.config.task_id
            
            if not task_id:
                logger.warning("No task_id in storyboard, skipping persistence")
                return
            
            # Build metadata
            input_with_title = ctx.params.copy()
            input_with_title.pop("forbid_embedded_text_in_image", None)
            input_with_title["text"] = ctx.input_text # Ensure text is included
            if not input_with_title.get("title"):
                input_with_title["title"] = storyboard.title
            requested_backend = storyboard.config.render_backend
            effective_backend = self._resolve_effective_render_backend(ctx)
            input_with_title["render_backend"] = effective_backend
            input_with_title["render_backend_requested"] = requested_backend
            input_with_title["render_backend_effective"] = effective_backend
            render_execution_plan = self._render_execution_plan_for_metadata(ctx)
            result_metadata = {
                "video_path": result.video_path,
                "duration": result.duration,
                "file_size": result.file_size,
                "n_frames": len(storyboard.frames),
                "render_execution_plan": render_execution_plan,
                **build_text_rendering_result_metadata(
                    ctx.observability,
                    text_render_package_path=TEXT_RENDER_PACKAGE_ARTIFACT_PATH,
                ),
            }
            
            metadata = {
                "task_id": task_id,
                "created_at": storyboard.created_at.isoformat() if storyboard.created_at else None,
                "completed_at": storyboard.completed_at.isoformat() if storyboard.completed_at else None,
                "status": "completed",
                
                "input": input_with_title,
                
                "result": result_metadata,
                
                "config": {
                    "llm_model": self.core.config.get("llm", {}).get("model", "unknown"),
                    "llm_base_url": self.core.config.get("llm", {}).get("base_url", "unknown"),
                    "comfyui_url": self.core.config.get("comfyui", {}).get("comfyui_url", "unknown"),
                    "runninghub_enabled": bool(self.core.config.get("comfyui", {}).get("runninghub_api_key")),
                    "render_backend": effective_backend,
                    "render_backend_requested": requested_backend,
                    "render_backend_effective": effective_backend,
                },
                "observability": ctx.observability,
            }
            
            # Save metadata
            await self.core.persistence.save_task_metadata(task_id, metadata)
            logger.info(f"💾 Saved task metadata: {task_id}")
            
            # Save storyboard
            await self.core.persistence.save_storyboard(task_id, storyboard)
            logger.info(f"💾 Saved storyboard: {task_id}")
            
        except Exception as e:
            logger.error(f"Failed to persist task data: {e}")
            # Don't raise - persistence failure shouldn't break video generation

    async def _persist_failed_task_data(self, ctx: PipelineContext, error: Exception) -> None:
        if not ctx.task_id:
            return

        metadata = {
            "task_id": ctx.task_id,
            "created_at": datetime.now().isoformat(),
            "completed_at": datetime.now().isoformat(),
            "status": "failed",
            "error": str(error),
            "input": {
                key: value
                for key, value in {"text": ctx.input_text, **ctx.params}.items()
                if key != "forbid_embedded_text_in_image"
            },
            "config": {},
            "observability": ctx.observability,
        }
        await self.core.persistence.save_task_metadata(ctx.task_id, metadata)
