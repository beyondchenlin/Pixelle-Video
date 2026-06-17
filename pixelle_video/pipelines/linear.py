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

Linear Video Pipeline Base Class

This module defines the template method pattern for linear video generation workflows.
It introduces `PipelineContext` for state management and `LinearVideoPipeline` for
process orchestration.
"""

from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional

from loguru import logger

from pixelle_video.config import config_manager
from pixelle_video.models.caption_speech_plan import CaptionSpeechPlan
from pixelle_video.models.creation_package import CreationPackage
from pixelle_video.models.final_visual_prompt_contract import RenderedMediaPrompt
from pixelle_video.models.progress import (
    CallbackProgressSink,
    ProgressDispatcher,
    ProgressEvent,
)
from pixelle_video.models.prompt_plan import PromptPlanBundle
from pixelle_video.models.reference_image import ReferenceImageAsset
from pixelle_video.models.reference_image_analysis import (
    ReferenceImageAnalysis,
    ReferenceImageAnalysisResult,
)
from pixelle_video.models.reference_image_visual_context import ReferenceImageVisualContext
from pixelle_video.models.storyboard import Storyboard, StoryboardConfig, VideoGenerationResult
from pixelle_video.models.storyboard_plan import StoryboardPlan
from pixelle_video.models.style_resolution import ResolvedStyleSpec
from pixelle_video.pipelines.base import BasePipeline
from pixelle_video.services.reference_image_analysis import (
    ReferenceImageAnalysisService,
    resolve_reference_image_analysis_mode,
)
from pixelle_video.services.reference_image_asset_service import (
    ReferenceImageAssetService,
    resolve_reference_image_input,
)
from pixelle_video.services.reference_image_visual_context_adapter import (
    ReferenceImageVisualContextAdapter,
)
from pixelle_video.services.timing_planner import TimingPlan
from pixelle_video.services.vision_llm_service import VisionLLMService
from pixelle_video.utils.logging_util import bind_log_context


_REFERENCE_IMAGE_ENABLED_PARAM_NAMES = (
    "reference_image_enabled",
    "enable_reference_image",
    "ref_image_enabled",
)


@asynccontextmanager
async def _noop_async_context():
    yield


def _config_mapping_get(config: Any, key: str, default: Any = None) -> Any:
    if isinstance(config, Mapping):
        return config.get(key, default)
    return getattr(config, key, default)


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "enabled"}
    return bool(value)


def _resolve_reference_image_config(core_config: Any) -> Any:
    reference_image_config = _config_mapping_get(core_config, "reference_image")
    if reference_image_config is not None:
        return reference_image_config
    return config_manager.get("reference_image", {})


def _resolve_vision_llm_config(core_config: Any) -> Mapping[str, Any]:
    vision_config = _config_mapping_get(core_config, "vision_llm")
    if isinstance(vision_config, Mapping):
        return dict(vision_config)
    configured = config_manager.get("vision_llm", {})
    return dict(configured) if isinstance(configured, Mapping) else {}


def _reference_image_enabled(params: Mapping[str, Any], reference_image_config: Any) -> bool:
    for param_name in _REFERENCE_IMAGE_ENABLED_PARAM_NAMES:
        if param_name in params and params[param_name] is not None:
            return _coerce_bool(params[param_name])
    return _coerce_bool(_config_mapping_get(reference_image_config, "enabled", False))


def _resolve_reference_image_merge_mode(params: Mapping[str, Any], reference_image_config: Any) -> str:
    explicit_mode = params.get("reference_image_profile_merge_mode") or params.get("profile_merge_mode")
    if explicit_mode is None:
        structured_input = params.get("reference_image")
        if isinstance(structured_input, Mapping):
            explicit_mode = structured_input.get("profile_merge_mode")
    configured_mode = explicit_mode or _config_mapping_get(
        reference_image_config,
        "profile_merge_mode",
        "supplement",
    )
    normalized = str(configured_mode or "supplement").strip().lower()
    return normalized if normalized in {"supplement", "override", "strict"} else "supplement"


def _append_reference_image_hint(existing_hint: Any, prompt_hint: str) -> str:
    prompt_hint = str(prompt_hint or "").strip()
    if not prompt_hint:
        return str(existing_hint or "").strip()
    prefix = "参考图视觉一致性提示："
    existing = str(existing_hint or "").strip()
    reference_clause = f"{prefix}{prompt_hint}"
    if not existing:
        return reference_clause
    if reference_clause in existing:
        return existing
    return f"{existing}\n\n{reference_clause}"


@dataclass
class PipelineContext:
    """
    Context object holding the state of a single pipeline execution.

    This object is passed between steps in the LinearVideoPipeline lifecycle.
    """
    # === Input ===
    input_text: str
    params: Dict[str, Any]
    progress_callback: Optional[Callable[[ProgressEvent], None]] = None
    progress_dispatcher: Optional[ProgressDispatcher] = None
    request_id: Optional[str] = None
    session_id: Optional[str] = None
    api_task_id: Optional[str] = None

    # === Task State ===
    task_id: Optional[str] = None
    task_dir: Optional[str] = None
    task_log_session: Any = None
    observability: Dict[str, Any] = field(default_factory=dict)

    # === Content ===
    title: Optional[str] = None
    source_text: Optional[str] = None
    caption_speech_plan: Optional[CaptionSpeechPlan] = None
    storyboard_plan: Optional[StoryboardPlan] = None

    # === Visuals ===
    image_prompts: List[Optional[str]] = field(default_factory=list)
    rendered_media_prompts: List[RenderedMediaPrompt] = field(default_factory=list)
    resolved_style: Optional[ResolvedStyleSpec] = None
    media_negative_prompt: Optional[str] = None
    planning_snapshot: Optional[Dict[str, Any]] = None
    prompt_plan_bundle: Optional[PromptPlanBundle] = None
    llm_trace_refs: List[Dict[str, str]] = field(default_factory=list)
    creation_package: Optional[CreationPackage] = None
    timing_plan: Optional[TimingPlan] = None
    reference_image_asset: Optional[ReferenceImageAsset] = None
    reference_image_analysis: Optional[ReferenceImageAnalysis] = None
    reference_image_analysis_result: Optional[ReferenceImageAnalysisResult] = None
    reference_image_visual_context: Optional[ReferenceImageVisualContext] = None

    # === Configuration & Storyboard ===
    config: Optional[StoryboardConfig] = None
    storyboard: Optional[Storyboard] = None

    # === Output ===
    final_video_path: Optional[str] = None
    result: Optional[VideoGenerationResult] = None


class LinearVideoPipeline(BasePipeline):
    """
    Base class for linear video generation pipelines using the Template Method pattern.

    This class orchestrates the video generation process into distinct lifecycle steps:
    1. setup_environment
    2. generate_content
    3. determine_title
    4. plan_visuals
    5. initialize_storyboard
    6. produce_assets
    7. post_production
    8. finalize

    Subclasses should override specific steps to customize behavior while maintaining
    the overall workflow structure.
    """

    async def __call__(
        self,
        text: str,
        progress_callback: Optional[Callable[[ProgressEvent], None]] = None,
        **kwargs
    ) -> VideoGenerationResult:
        """
        Execute the pipeline using the template method.
        """
        incoming_dispatcher = kwargs.get("progress_dispatcher")
        sinks = []
        if progress_callback is not None:
            sinks.append(CallbackProgressSink(progress_callback))
        if incoming_dispatcher is not None:
            sinks.extend(incoming_dispatcher.sinks)
        progress_dispatcher = ProgressDispatcher(sinks) if sinks else None
        effective_progress_callback = (
            progress_dispatcher.emit if progress_dispatcher is not None else progress_callback
        )
        pipeline_params = {
            key: value
            for key, value in kwargs.items()
            if key != "progress_dispatcher"
        }

        # 1. Initialize context
        ctx = PipelineContext(
            input_text=text,
            params=pipeline_params,
            progress_callback=effective_progress_callback,
            progress_dispatcher=progress_dispatcher,
            request_id=pipeline_params.get("request_id"),
            session_id=pipeline_params.get("session_id"),
            api_task_id=pipeline_params.get("api_task_id"),
        )

        with bind_log_context(
            request_id=ctx.request_id,
            session_id=ctx.session_id,
            api_task_id=ctx.api_task_id,
        ):
            task_scope = getattr(self.core, "local_comfyui_task_scope", None)
            scope_manager = task_scope() if callable(task_scope) else _noop_async_context()
            try:
                async with scope_manager:
                    # === Phase 1: Preparation ===
                    await self.setup_environment(ctx)
                    await self.prepare_reference_image(ctx)

                    # === Phase 2: Content Creation ===
                    await self.generate_content(ctx)
                    await self.determine_title(ctx)
                    await self.analyze_reference_image(ctx)
                    await self.prepare_reference_image_visual_context(ctx)

                    # === Phase 3: Visual Planning ===
                    await self.plan_visuals(ctx)
                    await self.initialize_storyboard(ctx)

                    # === Phase 4: Asset Production ===
                    await self.produce_assets(ctx)

                    # === Phase 5: Post Production ===
                    await self.post_production(ctx)

                    # === Phase 6: Finalization ===
                    return await self.finalize(ctx)

            except Exception as e:
                persist_failed_task_data = getattr(self, "_persist_failed_task_data", None)
                if persist_failed_task_data is not None:
                    await persist_failed_task_data(ctx, e)
                await self.handle_exception(ctx, e)
                raise
            finally:
                if ctx.task_log_session is not None:
                    ctx.task_log_session.close()

    # ==================== Lifecycle Methods ====================

    async def setup_environment(self, ctx: PipelineContext):
        """Step 1: Setup task directory and environment."""
        pass

    async def prepare_reference_image(self, ctx: PipelineContext):
        """Prepare an optional reference image as a task-local asset."""

        raw_reference_image = resolve_reference_image_input(ctx.params)
        if raw_reference_image is None:
            return

        reference_image_config = _resolve_reference_image_config(getattr(self.core, "config", None))
        if not _reference_image_enabled(ctx.params, reference_image_config):
            ctx.observability.setdefault("reference_image", {})["status"] = "disabled"
            ctx.params.pop("ref_image_asset", None)
            ctx.params.pop("ref_image", None)
            logger.info("Reference image supplied but reference_image.enabled is false; ignoring it")
            return

        if not ctx.task_dir:
            raise ValueError("task_dir is required before reference image assetization")

        asset = ReferenceImageAssetService(reference_image_config).prepare(
            raw_reference_image,
            task_dir=ctx.task_dir,
        )
        ctx.reference_image_asset = asset
        trace_payload = asset.to_trace_dict()
        ctx.params["ref_image"] = asset.workflow_asset_path
        ctx.params["ref_image_asset"] = trace_payload
        ctx.observability["reference_image_asset"] = trace_payload
        logger.info(
            "Reference image assetized: {}",
            asset.workflow_asset_relative_path,
        )

    async def analyze_reference_image(self, ctx: PipelineContext):
        """Run optional structured reference image analysis before visual planning."""
        if ctx.reference_image_asset is None or not ctx.task_dir:
            return

        reference_image_config = _resolve_reference_image_config(getattr(self.core, "config", None))
        analysis_mode = resolve_reference_image_analysis_mode(
            ctx.params,
            reference_image_config,
        )
        vision_config = _resolve_vision_llm_config(getattr(self.core, "config", None))
        prompt_language = str(ctx.params.get("storyboard_prompt_language") or "zh_CN")

        trace_context = None
        trace_context_factory = getattr(self, "_llm_trace_context", None)
        if callable(trace_context_factory) and ctx.task_id:
            trace_context = trace_context_factory(
                ctx,
                operation="reference_image_analysis",
            )
        trace_recorder = None
        trace_recorder_factory = getattr(self, "_llm_trace_recorder", None)
        if callable(trace_recorder_factory):
            trace_recorder = trace_recorder_factory(ctx)

        result = await ReferenceImageAnalysisService().analyze(
            vision_llm_service=VisionLLMService(vision_config),
            asset=ctx.reference_image_asset,
            prompt_language=prompt_language,
            task_dir=ctx.task_dir,
            analysis_mode=analysis_mode,
            trace_context=trace_context,
            trace_recorder=trace_recorder,
            vision_config=vision_config,
        )
        ctx.reference_image_analysis_result = result
        ctx.reference_image_analysis = result.analysis
        trace_payload = result.to_trace_dict()
        ctx.params["reference_image_analysis"] = trace_payload
        ctx.observability["reference_image_analysis"] = trace_payload

    async def prepare_reference_image_visual_context(self, ctx: PipelineContext):
        """Build prompt-only visual context and inject it into visual planning params."""
        if (
            ctx.reference_image_asset is None
            or ctx.reference_image_analysis_result is None
            or not ctx.task_dir
        ):
            return

        reference_image_config = _resolve_reference_image_config(getattr(self.core, "config", None))
        merge_mode = _resolve_reference_image_merge_mode(ctx.params, reference_image_config)
        build_result = ReferenceImageVisualContextAdapter().build(
            asset=ctx.reference_image_asset,
            analysis_result=ctx.reference_image_analysis_result,
            ip_profile=None,
            merge_mode=merge_mode,
        )
        visual_context = ReferenceImageVisualContextAdapter.write_artifact(
            ctx.task_dir,
            build_result.visual_context,
        )
        ctx.reference_image_visual_context = visual_context
        visual_context_payload = visual_context.to_trace_dict()
        ctx.params["reference_image_visual_context"] = visual_context_payload
        ctx.params["reference_image_visual_story_context_patch"] = build_result.visual_story_context_patch
        ctx.observability["reference_image_visual_context"] = visual_context_payload

        if visual_context.enabled and visual_context.prompt_fallback_hint:
            ctx.params["reference_image_prompt_fallback_hint"] = visual_context.prompt_fallback_hint
            ctx.params["generation_world_hint"] = _append_reference_image_hint(
                ctx.params.get("generation_world_hint"),
                visual_context.prompt_fallback_hint,
            )

    async def generate_content(self, ctx: PipelineContext):
        """Step 2: Generate or process script/narrations."""
        pass

    async def determine_title(self, ctx: PipelineContext):
        """Step 3: Determine or generate video title."""
        pass

    async def plan_visuals(self, ctx: PipelineContext):
        """Step 4: Generate image prompts or visual descriptions."""
        pass

    async def initialize_storyboard(self, ctx: PipelineContext):
        """Step 5: Create Storyboard object and frames."""
        pass

    async def produce_assets(self, ctx: PipelineContext):
        """Step 6: Generate audio, images, and render frames (Core processing)."""
        pass

    async def post_production(self, ctx: PipelineContext):
        """Step 7: Concatenate videos and add BGM."""
        pass

    async def finalize(self, ctx: PipelineContext) -> VideoGenerationResult:
        """Step 8: Create result object and persist metadata."""
        raise NotImplementedError("finalize must be implemented by subclass")

    async def handle_exception(self, ctx: PipelineContext, error: Exception):
        """Handle exceptions during pipeline execution."""
        logger.error(f"Pipeline execution failed: {error}")
