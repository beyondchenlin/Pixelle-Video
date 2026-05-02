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
from typing import Any, Callable, Dict, List, Optional

from loguru import logger

from pixelle_video.models.caption_speech_plan import CaptionSpeechPlan
from pixelle_video.models.creation_package import CreationPackage
from pixelle_video.models.progress import (
    CallbackProgressSink,
    ProgressDispatcher,
    ProgressEvent,
)
from pixelle_video.models.prompt_plan import PromptPlanBundle
from pixelle_video.models.storyboard import Storyboard, StoryboardConfig, VideoGenerationResult
from pixelle_video.models.storyboard_plan import StoryboardPlan
from pixelle_video.models.style_resolution import ResolvedStyleSpec
from pixelle_video.pipelines.base import BasePipeline
from pixelle_video.services.timing_planner import TimingPlan
from pixelle_video.utils.logging_util import bind_log_context


@asynccontextmanager
async def _noop_async_context():
    yield


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
    resolved_style: Optional[ResolvedStyleSpec] = None
    media_negative_prompt: Optional[str] = None
    planning_snapshot: Optional[Dict[str, Any]] = None
    prompt_plan_bundle: Optional[PromptPlanBundle] = None
    creation_package: Optional[CreationPackage] = None
    timing_plan: Optional[TimingPlan] = None
    
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

                    # === Phase 2: Content Creation ===
                    await self.generate_content(ctx)
                    await self.determine_title(ctx)

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
