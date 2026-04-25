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
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, List, Literal, Optional

from loguru import logger

from pixelle_video.config.workflow_defaults import infer_workflow_domain
from pixelle_video.models.creation_package import CreationPackage
from pixelle_video.models.progress import ProgressEvent
from pixelle_video.models.render_package import RenderManifest, VisualClip
from pixelle_video.models.storyboard import (
    Storyboard,
    StoryboardConfig,
    StoryboardFrame,
    VideoGenerationResult,
    build_storyboard_config_planning_kwargs,
    build_storyboard_frame_planning_kwargs,
)
from pixelle_video.models.text_overlay import (
    build_text_rendering_policy,
    build_text_rendering_settings,
)
from pixelle_video.pipelines.linear import LinearVideoPipeline, PipelineContext
from pixelle_video.pipelines.storyboard_config import resolve_storyboard_render_kwargs
from pixelle_video.render_backend import (
    HYPERFRAMES_COMPILED_RENDER_BACKEND,
    LEGACY_RENDER_BACKEND,
)
from pixelle_video.services.ass_text_adapter import AssTextAdapter
from pixelle_video.services.native_prompt_projection import NativePromptProjection
from pixelle_video.services.text_cue_compiler import TextCueCompiler
from pixelle_video.services.text_overlay_planner import TextOverlayPlanner
from pixelle_video.services.timing_planner import TimingPlanner
from pixelle_video.services.tts_segmentation import build_external_tts_segmentation_plan
from pixelle_video.services.video import VideoService
from pixelle_video.tts_audio_strategy import (
    AUTO_TTS_AUDIO_STRATEGY,
    MASTER_TRACK_TTS_AUDIO_STRATEGY,
    PER_FRAME_TTS_AUDIO_STRATEGY,
)
from pixelle_video.tts_split_strategy import INTERNAL_ONLY_TTS_SPLIT_MODE
from pixelle_video.tts_workflow_contract import is_index_tts2_workflow_key
from pixelle_video.utils.content_generators import (
    generate_narrations_from_topic,
    generate_styled_image_prompt_batch,
    generate_title,
    split_narration_script,
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
)
from pixelle_video.utils.prompt_generation_performance import (
    LLM_PROMPT_BATCH_CONCURRENT_LIMIT_PARAM,
    LLM_PROMPT_BATCH_SIZE_PARAM,
)
from pixelle_video.utils.template_util import get_template_type, parse_template_size


@dataclass(frozen=True)
class AssetExecutionMode:
    template_type: Literal["static", "image", "video"]
    tts_workflow_key: Optional[str]
    media_workflow_key: Optional[str]
    media_domain: Literal["static", "image", "video"]
    is_runninghub: bool
    use_runninghub_parallel: bool
    use_staged_mode: bool




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
        n_scenes = ctx.params.get("n_scenes", 5)
        min_words = ctx.params.get("min_narration_words", 5)
        max_words = ctx.params.get("max_narration_words", 20)
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
                narration_count=n_scenes,
                pipeline="standard",
                workflow=ctx.params.get("media_workflow"),
                template=ctx.params.get("frame_template"),
            )
        
        if mode == "generate":
            self._report_progress(ctx.progress_callback, "generating_narrations", 0.05)
            render_kwargs = resolve_storyboard_render_kwargs(self.core.config, ctx.params)
            ctx.narrations = await generate_narrations_from_topic(
                self.llm,
                topic=text,
                n_scenes=n_scenes,
                min_words=min_words,
                max_words=max_words,
                stage_callback=stage_callback,
                preserve_natural_punctuation=render_kwargs["preserve_natural_punctuation"],
            )
            logger.info(f"✅ Generated {len(ctx.narrations)} narrations")
        else:  # fixed
            self._report_progress(ctx.progress_callback, "splitting_script", 0.05)
            split_mode = ctx.params.get("split_mode", "paragraph")
            ctx.narrations = await split_narration_script(
                text,
                split_mode=split_mode,
                stage_callback=stage_callback,
            )
            logger.info(f"✅ Split script into {len(ctx.narrations)} segments (mode={split_mode})")
            logger.info(f"   Note: n_scenes={n_scenes} is ignored in fixed mode")

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
            self._report_progress(ctx.progress_callback, "generating_title", 0.10)
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
        # Detect template type to determine if media generation is needed
        frame_template = ctx.params.get("frame_template") or "1080x1920/default.html"
        
        template_name = Path(frame_template).name
        template_type = get_template_type(template_name)
        template_requires_media = (template_type in ["image", "video"])
        stage_callback = self._ai_stage_callback(ctx)
        
        if template_type == "image":
            logger.info("📸 Template requires image generation")
        elif template_type == "video":
            logger.info("🎬 Template requires video generation")
        else:  # static
            logger.info("⚡ Static template - skipping media generation pipeline")
            logger.info("   💡 Benefits: Faster generation + Lower cost + No ComfyUI dependency")
        
        # Only generate image prompts if template requires media
        if template_requires_media:
            self._report_progress(ctx.progress_callback, "generating_image_prompts", 0.15)
            
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
            def image_prompt_progress(completed: int, total: int, message: str):
                batch_progress = completed / total if total > 0 else 0
                overall_progress = 0.15 + (batch_progress * 0.15)
                self._report_progress(
                    ctx.progress_callback,
                    "generating_image_prompts",
                    overall_progress,
                    extra_info=message
                )
            
            image_config = self.core.config.get("comfyui", {}).get(media_type, {})
            text_rendering_settings = build_text_rendering_settings(
                ctx.params.get("text_rendering")
            )
            text_policy = build_text_rendering_policy(text_rendering_settings.overlay)
            text_plan = TextOverlayPlanner().plan(
                narrations=ctx.narrations,
                policy=text_policy,
            )
            ctx.creation_package = CreationPackage(
                task_id=ctx.task_id or "",
                text_overlay_plan=text_plan,
                prompt_plan={"text_rendering_policy": text_policy.to_dict()},
            )
            native_hints = NativePromptProjection().project(
                plan=text_plan,
                policy=text_policy,
            )
            styled_batch = await generate_styled_image_prompt_batch(
                llm_service=self.llm,
                narrations=ctx.narrations,
                image_config=image_config,
                prompt_prefix=prompt_prefix,
                workflow=ctx.params.get("media_workflow"),
                media_service=self.core.media,
                media_type=media_type,
                min_words=min_words,
                max_words=max_words,
                batch_size=ctx.params.get(LLM_PROMPT_BATCH_SIZE_PARAM),
                max_concurrency=ctx.params.get(LLM_PROMPT_BATCH_CONCURRENT_LIMIT_PARAM),
                progress_callback=image_prompt_progress,
                world_preset_id=ctx.params.get("world_preset_id"),
                shot_preset_id=ctx.params.get("shot_preset_id"),
                consistency_strength=ctx.params.get("consistency_strength", "standard"),
                content_mode=ctx.params.get("content_mode"),
                role_strategy=ctx.params.get("role_strategy"),
                role_locking_strength=ctx.params.get("role_locking_strength"),
                shot_strategy=ctx.params.get("shot_strategy"),
                frame_overrides=ctx.params.get("frame_overrides"),
                text_rendering=ctx.params.get("text_rendering"),
                native_prompt_hints_by_frame=native_hints,
                stage_callback=stage_callback,
            )

            ctx.image_prompts = styled_batch.prompts
            ctx.resolved_style = styled_batch.resolved_style
            ctx.media_negative_prompt = styled_batch.negative_prompt
            ctx.planning_snapshot = dict(styled_batch.planning_snapshot or {}) or None
            
            logger.info(f"✅ Generated {len(ctx.image_prompts)} image prompts")
        else:
            # Static template - skip image prompt generation entirely
            ctx.image_prompts = [None] * len(ctx.narrations)
            ctx.resolved_style = None
            ctx.media_negative_prompt = None
            ctx.planning_snapshot = None
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
                narration_count=len(ctx.narrations),
                reason="static template",
            )
            logger.info("⚡ Skipped image prompt generation (static template)")
            logger.info(f"   💡 Savings: {len(ctx.narrations)} LLM calls + {len(ctx.narrations)} media generations")

        self._emit_ai_creation_total(ctx, status="success")

    async def initialize_storyboard(self, ctx: PipelineContext):
        """Step 5: Create Storyboard object and frames."""
        # === Handle TTS parameter compatibility ===
        tts_inference_mode = ctx.params.get("tts_inference_mode")
        tts_voice = ctx.params.get("tts_voice")
        voice_id = ctx.params.get("voice_id")
        tts_workflow = ctx.params.get("tts_workflow")
        
        final_voice_id = None
        final_tts_workflow = tts_workflow
        
        if tts_inference_mode:
            # New API from web UI
            if tts_inference_mode == "local":
                final_voice_id = tts_voice or "zh-CN-YunjianNeural"
                final_tts_workflow = None
                logger.debug(f"TTS Mode: local (voice={final_voice_id})")
            elif tts_inference_mode == "comfyui":
                final_voice_id = None
                logger.debug(f"TTS Mode: comfyui (workflow={final_tts_workflow})")
        else:
            # Old API
            final_voice_id = voice_id or tts_voice or "zh-CN-YunjianNeural"
            logger.debug(f"TTS Mode: legacy (voice_id={final_voice_id}, workflow={final_tts_workflow})")
            
        # Create config
        ctx.config = StoryboardConfig(
            task_id=ctx.task_id,
            n_storyboard=len(ctx.narrations), # Use actual length
            min_narration_words=ctx.params.get("min_narration_words", 5),
            max_narration_words=ctx.params.get("max_narration_words", 20),
            min_image_prompt_words=ctx.params.get("min_image_prompt_words", 30),
            max_image_prompt_words=ctx.params.get("max_image_prompt_words", 60),
            video_fps=ctx.params.get("video_fps", 30),
            tts_inference_mode=tts_inference_mode or "local",
            voice_id=final_voice_id,
            tts_workflow=final_tts_workflow,
            tts_speed=ctx.params.get("tts_speed", 1.2),
            ref_audio=ctx.params.get("ref_audio"),
            ref_audio_text=ctx.params.get("ref_audio_text") or ctx.params.get("prompt_text"),
            **resolve_storyboard_render_kwargs(self.core.config, ctx.params),
            media_width=ctx.params.get("media_width"),
            media_height=ctx.params.get("media_height"),
            media_workflow=ctx.params.get("media_workflow"),
            media_negative_prompt=ctx.media_negative_prompt,
            frame_template=ctx.params.get("frame_template") or "1080x1920/default.html",
            template_params=ctx.params.get("template_params"),
            **build_storyboard_config_planning_kwargs(ctx.planning_snapshot, ctx.params),
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
        for i, (narration, image_prompt) in enumerate(zip(ctx.narrations, ctx.image_prompts)):
            frame = StoryboardFrame(
                index=i,
                narration=narration,
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
        ctx.timing_plan = planner.build(ctx.storyboard.frames)
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
            "split_mode": config.tts_split_mode,
            "narrations": [
                {
                    "frame_index": frame.index,
                    "raw_narration": frame.narration,
                }
                for frame in ctx.storyboard.frames
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

        tts_workflow_key = None
        if config.tts_inference_mode == "comfyui":
            tts_workflow_key = self.core.tts._resolve_workflow(
                workflow=config.tts_workflow,
            )["key"]

        media_workflow_key = None
        if media_domain != "static":
            media_workflow_key = self.core.media._resolve_workflow(
                workflow=config.media_workflow,
                workflow_domain=media_domain,
            )["key"]

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
            and config.tts_inference_mode == "comfyui"
            and bool(tts_workflow_key and tts_workflow_key.startswith("selfhost/"))
            and bool(media_workflow_key and media_workflow_key.startswith("selfhost/"))
        )

        return AssetExecutionMode(
            template_type=template_type,
            tts_workflow_key=tts_workflow_key,
            media_workflow_key=media_workflow_key,
            media_domain=media_domain,
            is_runninghub=is_runninghub,
            use_runninghub_parallel=use_runninghub_parallel,
            use_staged_mode=use_staged_mode,
        )

    def _resolve_hyperframes_template_id(self, config: StoryboardConfig) -> str:
        template_id = Path(config.frame_template).stem
        if template_id == "default":
            return "image_default"
        return template_id

    def _resolve_hyperframes_canvas_size(
        self,
        config: StoryboardConfig,
    ) -> tuple[int, int]:
        try:
            return parse_template_size(config.frame_template)
        except ValueError as exc:
            logger.warning(
                "Failed to parse HyperFrames canvas size from template "
                f"{config.frame_template!r}: {exc}. Falling back to media size."
            )
            return int(config.media_width), int(config.media_height)

    def _get_hyperframes_fallback_reason(self, ctx: PipelineContext) -> Optional[str]:
        config = ctx.config
        if config.render_backend != HYPERFRAMES_COMPILED_RENDER_BACKEND:
            return None

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

    def _is_hyperframes_render_path(self, ctx: PipelineContext) -> bool:
        if ctx.config.render_backend != HYPERFRAMES_COMPILED_RENDER_BACKEND:
            return False
        return self._get_hyperframes_fallback_reason(ctx) is None

    def _resolve_effective_render_backend(self, ctx: PipelineContext) -> str:
        if self._is_hyperframes_render_path(ctx):
            return HYPERFRAMES_COMPILED_RENDER_BACKEND
        return LEGACY_RENDER_BACKEND

    def _resolve_effective_tts_audio_strategy(self, ctx: PipelineContext) -> str:
        if self._is_hyperframes_render_path(ctx):
            return MASTER_TRACK_TTS_AUDIO_STRATEGY

        requested_strategy = getattr(ctx.config, "tts_audio_strategy", AUTO_TTS_AUDIO_STRATEGY)
        if requested_strategy == AUTO_TTS_AUDIO_STRATEGY:
            if ctx.config.tts_inference_mode == "comfyui":
                return MASTER_TRACK_TTS_AUDIO_STRATEGY
            return PER_FRAME_TTS_AUDIO_STRATEGY
        return requested_strategy

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

    async def _prepare_legacy_master_track_audio(self, ctx: PipelineContext) -> None:
        storyboard = ctx.storyboard
        if not storyboard.frames:
            return
        if all(frame.audio_path for frame in storyboard.frames):
            return
        if any(frame.audio_path for frame in storyboard.frames):
            logger.warning(
                "Skipping legacy master-track audio preparation because some frames already contain audio."
            )
            return
        if ctx.timing_plan is None or not ctx.timing_plan.blocks:
            logger.warning("Skipping legacy master-track audio preparation: timing plan is empty.")
            return

        master_audio_path, _ = await self._synthesize_hyperframes_audio(ctx)
        self._align_legacy_master_track_timings(ctx)
        self._offset_sentence_timings_to_master_timeline(ctx.timing_plan)

        for frame in storyboard.frames:
            sentence_units = [
                sentence
                for sentence in ctx.timing_plan.sentences
                if frame.index in sentence.frame_indices
            ]
            clip_start = self._resolve_sentence_time(sentence_units, minimum=True)
            clip_end = self._resolve_sentence_time(sentence_units, minimum=False)
            if clip_start is None or clip_end is None or clip_end <= clip_start:
                raise RuntimeError(
                    f"Unable to resolve master-track timing window for frame {frame.index + 1}."
                )

            output_path = get_task_frame_path(ctx.config.task_id, frame.index, "audio")
            output_path = str(Path(output_path).with_suffix(".wav"))
            self._extract_audio_clip(
                master_audio_path,
                output_path,
                start_time=clip_start,
                end_time=clip_end,
                fade_ms=ctx.config.tts_audio_boundary_fade_ms,
            )
            frame.audio_path = output_path
            frame.duration = self._get_audio_duration(output_path)

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
        action: str,
    ) -> None:
        self._report_progress(
            callback,
            "frame_step",
            self._stage_progress(stage_start, stage_end, frame_current, frame_total),
            frame_current=frame_current,
            frame_total=frame_total,
            step=step,
            action=action,
        )

    async def _produce_assets_staged(self, ctx: PipelineContext):
        storyboard = ctx.storyboard
        config = ctx.config
        total_frames = len(storyboard.frames)

        logger.info("Using staged selfhost image processing")

        for frame in storyboard.frames:
            if not frame.audio_path:
                self._report_staged_frame_progress(
                    ctx.progress_callback,
                    stage_start=0.20,
                    stage_end=0.35,
                    frame_current=frame.index + 1,
                    frame_total=total_frames,
                    step=1,
                    action="audio",
                )
                await self.core.frame_processor._step_generate_audio(frame, config)

        for frame in storyboard.frames:
            has_existing_media = frame.image_path is not None or frame.video_path is not None
            needs_generation = frame.image_prompt is not None

            if needs_generation:
                self._report_staged_frame_progress(
                    ctx.progress_callback,
                    stage_start=0.35,
                    stage_end=0.50,
                    frame_current=frame.index + 1,
                    frame_total=total_frames,
                    step=2,
                    action="media",
                )
                await self.core.frame_processor._step_generate_media(frame, config)
            elif not has_existing_media:
                frame.image_path = None
                frame.media_type = None

        for frame in storyboard.frames:
            self._report_staged_frame_progress(
                ctx.progress_callback,
                stage_start=0.50,
                stage_end=0.65,
                frame_current=frame.index + 1,
                frame_total=total_frames,
                step=3,
                action="compose",
            )
            await self.core.frame_processor._step_compose_frame(
                frame,
                storyboard,
                config,
            )

        for frame in storyboard.frames:
            self._report_staged_frame_progress(
                ctx.progress_callback,
                stage_start=0.65,
                stage_end=0.80,
                frame_current=frame.index + 1,
                frame_total=total_frames,
                step=4,
                action="video",
            )
            await self.core.frame_processor._step_create_video_segment(frame, config)
            storyboard.total_duration += frame.duration

    async def produce_assets(self, ctx: PipelineContext):
        """Step 6: Generate audio, images, and render frames (Core processing)."""
        storyboard = ctx.storyboard
        config = ctx.config
        if self._is_hyperframes_render_path(ctx):
            await self._produce_assets_hyperframes(ctx)
            logger.info("All frames processed in HyperFrames image mode")
            return

        if self._resolve_effective_tts_audio_strategy(ctx) == MASTER_TRACK_TTS_AUDIO_STRATEGY:
            await self._prepare_legacy_master_track_audio(ctx)

        execution_mode = self._resolve_asset_execution_mode(ctx)
        
        # Get concurrent limit from config_manager (supports hot reload without restart)
        from pixelle_video.config import config_manager
        runninghub_concurrent_limit = config_manager.config.comfyui.runninghub_concurrent_limit or 1

        if execution_mode.use_staged_mode:
            await self._produce_assets_staged(ctx)
            logger.info(
                f"All frames processed in staged mode (total duration: {storyboard.total_duration:.2f}s)"
            )
            return
        
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
                        "processing_frame",
                        base_progress + (per_frame_progress * completed_count),
                        frame_current=i+1,
                        frame_total=len(storyboard.frames)
                    )
                    
                    processed_frame = await self.core.frame_processor(
                        frame=frame,
                        storyboard=storyboard,
                        config=config,
                        total_frames=len(storyboard.frames),
                        progress_callback=frame_progress_callback
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
                    "processing_frame",
                    base_progress + (per_frame_progress * i),
                    frame_current=i+1,
                    frame_total=len(storyboard.frames)
                )
                
                processed_frame = await self.core.frame_processor(
                    frame=frame,
                    storyboard=storyboard,
                    config=config,
                    total_frames=len(storyboard.frames),
                    progress_callback=frame_progress_callback
                )
                storyboard.total_duration += processed_frame.duration
                logger.info(f"✅ Frame {i+1} completed ({processed_frame.duration:.2f}s)")

    async def _produce_assets_hyperframes(self, ctx: PipelineContext):
        storyboard = ctx.storyboard
        config = ctx.config
        total_frames = len(storyboard.frames)

        logger.info("Using HyperFrames image asset production path")

        for frame in storyboard.frames:
            has_existing_media = frame.image_path is not None or frame.video_path is not None
            needs_generation = frame.image_prompt is not None

            if needs_generation:
                self._report_staged_frame_progress(
                    ctx.progress_callback,
                    stage_start=0.25,
                    stage_end=0.55,
                    frame_current=frame.index + 1,
                    frame_total=total_frames,
                    step=2,
                    action="media",
                )
                await self.core.frame_processor._step_generate_media(frame, config)
            elif not has_existing_media:
                frame.image_path = None
                frame.media_type = None

            self._report_staged_frame_progress(
                ctx.progress_callback,
                stage_start=0.55,
                stage_end=0.80,
                frame_current=frame.index + 1,
                frame_total=total_frames,
                step=3,
                action="compose",
            )
            await self.core.frame_processor._step_compose_frame(
                frame,
                storyboard,
                config,
                body_text_override="",
            )

    async def post_production(self, ctx: PipelineContext):
        """Step 7: Concatenate videos and add BGM."""
        if self._is_hyperframes_render_path(ctx):
            await self._post_production_hyperframes(ctx)
            return

        fallback_reason = self._get_hyperframes_fallback_reason(ctx)
        if fallback_reason is not None:
            logger.warning(f"HyperFrames backend requested but falling back to legacy rendering: {fallback_reason}")

        self._report_progress(ctx.progress_callback, "concatenating", 0.85)
        
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

        text_tracks, text_cues = self._compile_text_layer_for_render(ctx)
        ass_tracks, ass_cues = self._filter_text_layer_for_renderer(
            text_tracks,
            text_cues,
            renderer="ass",
        )
        if ass_cues:
            ass_dir = Path(ctx.task_dir or Path(final_video_path).parent) / "text_layer"
            manifest = RenderManifest(
                task_id=ctx.task_id or storyboard.config.task_id or "",
                title=storyboard.title,
                width=storyboard.config.media_width,
                height=storyboard.config.media_height,
                fps=storyboard.config.video_fps,
                template_id="legacy",
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
        self._record_text_layer_summary(
            ctx,
            renderer="ass" if ass_cues else "disabled",
            text_tracks=ass_tracks,
            text_cues=ass_cues,
            native_hint_count=self._count_native_prompt_hints(ctx),
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

    async def _post_production_hyperframes(self, ctx: PipelineContext):
        self._report_progress(ctx.progress_callback, "rendering_hyperframes", 0.85)

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
        text_tracks, text_cues = self._compile_text_layer_for_render(ctx)
        text_tracks, text_cues = self._filter_text_layer_for_renderer(
            text_tracks,
            text_cues,
            renderer="hyperframes",
        )

        manifest = RenderManifest(
            task_id=ctx.task_id,
            title=storyboard.title,
            canvas_width=canvas_width,
            canvas_height=canvas_height,
            media_width=config.media_width,
            media_height=config.media_height,
            fps=config.video_fps,
            template_id=self._resolve_hyperframes_template_id(config),
            master_audio_path=master_audio_path,
            master_audio_duration=master_audio_duration,
            audio_blocks=list(timing_plan.blocks),
            sentence_units=list(timing_plan.sentences),
            visual_clips=self._build_hyperframes_visual_clips(storyboard, timing_plan),
            text_tracks=text_tracks,
            text_cues=text_cues,
            caption_punctuation_mode=config.caption_punctuation_mode,
            canonical_timeline=(
                "remapped"
                if any(
                    sentence.remapped_start is not None and sentence.remapped_end is not None
                    for sentence in timing_plan.sentences
                )
                else "source"
            ),
        )
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

        bgm_path = ctx.params.get("bgm_path")
        render_output_path = ctx.final_video_path
        if bgm_path:
            final_output_path = Path(ctx.final_video_path)
            final_suffix = final_output_path.suffix or ".mp4"
            render_output_path = str(
                final_output_path.with_name(
                    f"{final_output_path.stem}_no_bgm{final_suffix}"
                )
            )

        final_video_path = self.core.hyperframes_renderer.render(
            str(project_paths.project_dir),
            output_path=render_output_path,
            width=canvas_width,
            height=canvas_height,
            fps=config.video_fps,
            expected_duration=master_audio_duration,
            expect_audio=bool(master_audio_path),
        )
        if bgm_path:
            logger.info(
                "Adding BGM to HyperFrames render: "
                f"{bgm_path} (volume={ctx.params.get('bgm_volume', 0.2)}, "
                f"mode={ctx.params.get('bgm_mode', 'loop')})"
            )
            final_video_path = VideoService()._add_bgm_to_video(
                video=final_video_path,
                bgm_path=bgm_path,
                output=ctx.final_video_path,
                volume=ctx.params.get("bgm_volume", 0.2),
                mode=ctx.params.get("bgm_mode", "loop"),
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
    ) -> None:
        ctx.observability["text_layer_summary"] = {
            "enabled": bool(text_tracks or text_cues or native_hint_count),
            "renderer": renderer,
            "track_count": len(text_tracks),
            "cue_count": len(text_cues),
            "native_prompt_hint_count": native_hint_count,
            "targets": sorted(
                {
                    target
                    for track in text_tracks
                    for target in track.renderer_targets
                }
            ),
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

        if len(segments) == 1:
            block_source_path = task_audio_dir / f"{block_id}_source.mp3"
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
            segment_source_path = task_audio_dir / f"{block_id}_segment_{index}_source.mp3"
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
            with NamedTemporaryFile(mode="w", delete=False, suffix=".txt", encoding="utf-8") as handle:
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

        for frame in storyboard.frames:
            sentence_units = [
                sentence
                for sentence in timing_plan.sentences
                if frame.index in sentence.frame_indices
            ]
            clip_start = self._resolve_sentence_time(sentence_units, minimum=True)
            clip_end = self._resolve_sentence_time(sentence_units, minimum=False)
            if clip_start is None or clip_end is None:
                continue

            raw_media_path = frame.video_path if frame.media_type == "video" else frame.image_path
            if not raw_media_path:
                logger.warning(
                    f"Skipping HyperFrames visual clip for frame {frame.index + 1}: missing raw media"
                )
                continue

            clip_specs.append(
                {
                    "frame_index": frame.index,
                    "raw_start": max(float(clip_start), 0.0),
                    "raw_end": max(float(clip_end), float(clip_start)),
                    "media_path": raw_media_path,
                    "media_type": frame.media_type or "image",
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

    def _resolve_sentence_time(
        self,
        sentence_units,
        *,
        minimum: bool,
    ) -> Optional[float]:
        values = []
        for sentence in sentence_units:
            preferred = sentence.remapped_start if minimum else sentence.remapped_end
            fallback = sentence.source_start if minimum else sentence.source_end
            value = preferred if preferred is not None else fallback
            if value is not None:
                values.append(float(value))

        if not values:
            return None
        return min(values) if minimum else max(values)

    async def finalize(self, ctx: PipelineContext) -> VideoGenerationResult:
        """Step 8: Create result object and persist metadata."""
        self._report_progress(ctx.progress_callback, "completed", 1.0)
        
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
            
            metadata = {
                "task_id": task_id,
                "created_at": storyboard.created_at.isoformat() if storyboard.created_at else None,
                "completed_at": storyboard.completed_at.isoformat() if storyboard.completed_at else None,
                "status": "completed",
                
                "input": input_with_title,
                
                "result": {
                    "video_path": result.video_path,
                    "duration": result.duration,
                    "file_size": result.file_size,
                    "n_frames": len(storyboard.frames),
                    "text_layer_summary": ctx.observability.get("text_layer_summary"),
                },
                
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
