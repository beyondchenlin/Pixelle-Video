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
Asset-Based Video Pipeline

Generates marketing videos from user-provided assets (images/videos) rather than
AI-generated media. Ideal for small businesses with existing media libraries.

Workflow:
1. Analyze uploaded assets (images/videos)
2. Generate script based on user intent and available assets
3. Match assets to script scenes
4. Compose final video with narrations

Example:
    pipeline = AssetBasedPipeline(pixelle_video)
    result = await pipeline(
        assets=["/path/img1.jpg", "/path/img2.jpg"],
        video_title="Pet Store Year-End Sale",
        intent="Promote our pet store's year-end sale with a warm and friendly tone",
        duration=30
    )
"""

from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional

from loguru import logger

from pixelle_video.config.tts_defaults import resolve_tts_inference_mode
from pixelle_video.models.asset_script import AssetCatalogEntry, AssetScriptResponse
from pixelle_video.models.llm_interaction_trace import (
    LLMTraceContext,
    trace_context_with_prompt_template,
)
from pixelle_video.models.progress import ProgressEvent
from pixelle_video.pipelines.linear import LinearVideoPipeline, PipelineContext
from pixelle_video.pipelines.storyboard_config import resolve_storyboard_render_kwargs
from pixelle_video.platform_context import resolve_workspace_id
from pixelle_video.services.llm_interaction_recorder import LLMInteractionRecorder
from pixelle_video.services.text_rendering_contract_summary import (
    TEXT_RENDER_PACKAGE_ARTIFACT_PATH,
    build_text_rendering_result_metadata,
    record_text_rendering_contract_summary,
    resolve_overlay_disabled_reason,
)
from pixelle_video.utils.logging_util import attach_task_log_sinks
from pixelle_video.utils.os_util import create_task_output_dir, get_task_final_video_path

# Type alias for progress callback
ProgressCallback = Optional[Callable[[ProgressEvent], None]]


class AssetBasedPipeline(LinearVideoPipeline):
    """
    Asset-Based Video Pipeline
    
    Generates videos from user-provided assets instead of AI-generated media.
    """
    
    def __init__(self, core):
        """
        Initialize pipeline
        
        Args:
            core: PixelleVideoCore instance
        """
        super().__init__(core)
        self.asset_index: Dict[str, Any] = {}  # In-memory asset metadata
        self._progress_callback: ProgressCallback = None

    @staticmethod
    def _build_asset_id(index: int) -> str:
        return f"asset_{index:03d}"

    def _serialize_asset_catalog(self) -> list[AssetCatalogEntry]:
        return [
            AssetCatalogEntry(
                asset_id=str(asset_id),
                asset_path=str(metadata["path"]),
                asset_type=str(metadata["type"]),
                asset_name=str(metadata["name"]),
                description=str(metadata["description"]),
            )
            for asset_id, metadata in self.asset_index.items()
        ]

    def _llm_trace_context(
        self,
        context: PipelineContext,
        *,
        operation: str,
        stage: str | None = None,
        frame_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> LLMTraceContext:
        if not context.task_id:
            raise ValueError("task_id is required before creating LLM trace contexts")
        resolved_metadata = {
            "chain_id": f"{context.task_id}:{operation}",
            "pipeline": "asset_based",
        }
        if context.request_id:
            resolved_metadata["request_id"] = context.request_id
        if context.session_id:
            resolved_metadata["session_id"] = context.session_id
        if context.api_task_id:
            resolved_metadata["api_task_id"] = context.api_task_id
        if metadata:
            resolved_metadata.update(dict(metadata))
        return LLMTraceContext(
            workspace_id=resolve_workspace_id(context.params),
            task_id=context.task_id,
            operation=operation,
            stage=stage,
            frame_id=frame_id,
            metadata=resolved_metadata,
        )

    def _llm_trace_recorder(self, context: PipelineContext) -> LLMInteractionRecorder:
        trace_repository = getattr(self.core, "trace_repository", None)
        if trace_repository is None:
            raise ValueError("trace_repository is required for LLM generation trace capture")

        raw_payload_store = getattr(self.core, "raw_payload_store", None)
        if raw_payload_store is None:
            raise ValueError("raw_payload_store is required for LLM generation trace capture")

        return LLMInteractionRecorder(
            trace_repository=trace_repository,
            raw_payload_store=raw_payload_store,
        )
    
    async def __call__(
        self,
        assets: List[str],
        video_title: str = "",
        intent: Optional[str] = None,
        duration: int = 30,
        source: str = "runninghub",
        bgm_path: Optional[str] = None,
        bgm_volume: float = 0.2,
        bgm_mode: str = "loop",
        progress_callback: ProgressCallback = None,
        **kwargs
    ) -> PipelineContext:
        """
        Execute pipeline with user-provided assets
        
        Args:
            assets: List of asset file paths
            video_title: Video title
            intent: Video intent/purpose (defaults to video_title)
            duration: Target duration in seconds
            source: Workflow source ("runninghub" or "selfhost")
            bgm_path: Path to background music file (optional)
            bgm_volume: BGM volume (0.0-1.0, default 0.2)
            bgm_mode: BGM mode ("loop" or "once", default "loop")
            progress_callback: Optional callback for progress updates
            **kwargs: Additional parameters
        
        Returns:
            Pipeline context with generated video
        """
        from pixelle_video.pipelines.linear import PipelineContext
        
        # Store progress callback
        self._progress_callback = progress_callback
        
        # Create custom context with asset-specific parameters
        ctx = PipelineContext(
            input_text=intent or video_title,  # Use intent or title as input_text
            params={
                "assets": assets,
                "video_title": video_title,
                "intent": intent or video_title,
                "duration": duration,
                "source": source,
                "bgm_path": bgm_path,
                "bgm_volume": bgm_volume,
                "bgm_mode": bgm_mode,
                **kwargs
            },
            progress_callback=progress_callback,
            request_id=kwargs.get("request_id"),
            session_id=kwargs.get("session_id"),
            api_task_id=kwargs.get("api_task_id"),
        )
        
        # Store request parameters in context for easy access
        ctx.request = ctx.params
        
        try:
            # Execute pipeline lifecycle
            await self.setup_environment(ctx)
            await self.determine_title(ctx)
            await self.generate_content(ctx)
            await self.plan_visuals(ctx)
            await self.initialize_storyboard(ctx)
            await self.produce_assets(ctx)
            await self.post_production(ctx)
            await self.finalize(ctx)
            
            return ctx
            
        except Exception as e:
            await self.handle_exception(ctx, e)
            raise
        finally:
            if getattr(ctx, "task_log_session", None) is not None:
                ctx.task_log_session.close()
    
    def _emit_progress(self, event: ProgressEvent):
        """Emit progress event to callback if available"""
        if self._progress_callback:
            self._progress_callback(event)
    
    async def setup_environment(self, context: PipelineContext) -> PipelineContext:
        """
        Analyze uploaded assets and build asset index
        
        Args:
            context: Pipeline context with assets list
        
        Returns:
            Updated context with asset_index
        """
        # Create isolated task directory
        task_dir, task_id = create_task_output_dir()
        context.task_id = task_id
        context.task_dir = Path(task_dir)  # Convert to Path for easier usage
        context.observability.update(
            {
                "version": "v1",
                "request_id": context.request_id,
                "session_id": context.session_id,
                "api_task_id": context.api_task_id,
                "task_id": task_id,
                "runtime_log_path": str(self.core.persistence.get_task_runtime_log_path(task_id)),
                "ai_creation_log_path": None,
            }
        )
        context.task_log_session = attach_task_log_sinks(
            task_id=task_id,
            task_dir=Path(task_dir),
            service_name="pipeline",
            ai_creation_enabled=False,
        )
        logger.bind(channel="runtime", pipeline="asset_based").info("asset task log context bound")
        
        # Determine final video path
        context.final_video_path = get_task_final_video_path(task_id)
        
        logger.info(f"📁 Task directory created: {task_dir}")
        logger.info("🔍 Analyzing uploaded assets...")
        
        assets: List[str] = context.request.get("assets", [])
        if not assets:
            raise ValueError("No assets provided. Please upload at least one image or video.")
        
        total_assets = len(assets)
        logger.info(f"Found {total_assets} assets to analyze")
        
        # Emit initial progress (0-15% for asset analysis)
        self._emit_progress(ProgressEvent(
            event_type="analyzing_assets",
            progress=0.01,
            frame_current=0,
            frame_total=total_assets,
            extra_info="start"
        ))
        
        self.asset_index = {}
        
        for i, asset_path in enumerate(assets, 1):
            asset_path_obj = Path(asset_path)
            
            if not asset_path_obj.exists():
                logger.warning(f"Asset not found: {asset_path}")
                continue
            
            logger.info(f"Analyzing asset {i}/{total_assets}: {asset_path_obj.name}")
            
            # Emit progress for this asset
            progress = 0.01 + (i - 1) / total_assets * 0.14  # 1% - 15%
            self._emit_progress(ProgressEvent(
                event_type="analyzing_asset",
                progress=progress,
                frame_current=i,
                frame_total=total_assets,
                extra_info=asset_path_obj.name
            ))
            
            # Determine asset type
            asset_type = self._get_asset_type(asset_path_obj)
            
            if asset_type == "image":
                # Analyze image using ImageAnalysisService
                analysis_source = context.request.get("source", "runninghub")
                description = await self.core.image_analysis(asset_path, source=analysis_source)

                asset_id = self._build_asset_id(i)
                self.asset_index[asset_id] = {
                    "asset_id": asset_id,
                    "path": asset_path,
                    "type": "image",
                    "name": asset_path_obj.name,
                    "description": description,
                }
                
                logger.info(f"✅ Image analyzed: {description[:50]}...")
            
            elif asset_type == "video":
                # Analyze video using VideoAnalysisService
                analysis_source = context.request.get("source", "runninghub")
                try:
                    description = await self.core.video_analysis(asset_path, source=analysis_source)

                    asset_id = self._build_asset_id(i)
                    self.asset_index[asset_id] = {
                        "asset_id": asset_id,
                        "path": asset_path,
                        "type": "video",
                        "name": asset_path_obj.name,
                        "description": description,
                    }
                    
                    logger.info(f"✅ Video analyzed: {description[:50]}...")
                except Exception as e:
                    logger.warning(f"Video analysis failed for {asset_path_obj.name}: {e}, using fallback")
                    asset_id = self._build_asset_id(i)
                    self.asset_index[asset_id] = {
                        "asset_id": asset_id,
                        "path": asset_path,
                        "type": "video",
                        "name": asset_path_obj.name,
                        "description": "Video asset (analysis failed)",
                    }
            
            else:
                logger.warning(f"Unknown asset type: {asset_path}")

        if not self.asset_index:
            raise ValueError("No valid assets could be analyzed. Please upload supported image or video files.")
        
        logger.success(f"✅ Asset analysis complete: {len(self.asset_index)} assets indexed")
        
        # Store asset index in context
        context.asset_index = self.asset_index
        
        # Emit completion of asset analysis
        self._emit_progress(ProgressEvent(
            event_type="analyzing_assets",
            progress=0.15,
            frame_current=total_assets,
            frame_total=total_assets,
            extra_info="complete"
        ))
        
        return context
    
    async def determine_title(self, context: PipelineContext) -> PipelineContext:
        """
        Use user-provided title if available, otherwise leave empty
        
        Args:
            context: Pipeline context
        
        Returns:
            Updated context with title (may be empty)
        """
        title = context.request.get("video_title")
        
        if title:
            context.title = title
            logger.info(f"📝 Video title: {title} (user-specified)")
        else:
            context.title = ""
            logger.info("📝 No video title specified (will be hidden in template)")
        
        return context
    
    async def generate_content(self, context: PipelineContext) -> PipelineContext:
        """
        Generate video script using LLM with structured output.

        The LLM selects stable asset_ids and the pipeline resolves them to local paths.
        
        Args:
            context: Pipeline context
        
        Returns:
            Updated context with generated script and resolved asset paths
        """
        from pixelle_video.prompts.asset_script_generation import render_asset_script_prompt
        
        logger.info("🤖 Generating video script with LLM...")
        
        # Emit progress for script generation (15% - 25%)
        self._emit_progress(ProgressEvent(
            event_type="generating_script",
            progress=0.16
        ))
        
        # Build prompt for LLM
        intent = context.request.get("intent", context.input_text)
        duration = context.request.get("duration", 30)
        title = context.title  # May be empty if user didn't provide one
        
        asset_catalog = self._serialize_asset_catalog()
        
        # Build prompt using the centralized prompt function
        rendered_prompt = render_asset_script_prompt(
            intent=intent,
            duration=duration,
            assets=asset_catalog,
            title=title
        )
        trace_context = trace_context_with_prompt_template(
            self._llm_trace_context(
                context,
                operation="asset_script_generation",
                stage="asset_script_generation",
            ),
            rendered_prompt=rendered_prompt,
            attempt=1,
            stage="asset_script_generation",
        )
        
        # Call LLM with structured output
        script: AssetScriptResponse = await self.core.llm(
            prompt=rendered_prompt.text,
            response_type=AssetScriptResponse,
            temperature=0.8,
            max_tokens=4000,
            trace_context=trace_context,
            trace_recorder=self._llm_trace_recorder(context),
        )

        context.script = []
        for scene in script.scenes:
            asset_metadata = self.asset_index.get(scene.asset_id)
            if asset_metadata is None:
                raise ValueError(f"asset-based script references unknown asset_id: {scene.asset_id}")

            scene_payload = scene.model_dump()
            scene_payload["asset_path"] = asset_metadata["path"]
            scene_payload["asset_name"] = asset_metadata["name"]
            scene_payload["asset_type"] = asset_metadata["type"]
            context.script.append(scene_payload)
        
        logger.success(f"✅ Generated script with {len(context.script)} scenes")
        
        # Emit progress after script generation
        self._emit_progress(ProgressEvent(
            event_type="generating_script",
            progress=0.25,
            extra_info="complete"
        ))
        
        # Log script preview
        for scene in context.script:
            narrations = scene.get("narrations", [])
            if isinstance(narrations, str):
                narrations = [narrations]
            narration_preview = " | ".join([n[:30] + "..." if len(n) > 30 else n for n in narrations[:2]])
            asset_name = scene.get("asset_name") or Path(scene.get("asset_path", "unknown")).name
            logger.info(f"Scene {scene['scene_number']} [{asset_name}]: {narration_preview}")
        
        return context
    
    async def plan_visuals(self, context: PipelineContext) -> PipelineContext:
        """
        Prepare matched scenes from LLM-generated script
        
        Since generate_content already resolved asset_id to asset_path, this method
        simply converts the script format to matched_scenes format.
        
        Args:
            context: Pipeline context
        
        Returns:
            Updated context with matched_scenes
        """
        logger.info("🎯 Preparing scene-asset mapping...")
        
        # Generate downstream-compatible scene mappings with both asset_id and resolved path.
        context.matched_scenes = [
            {
                **scene,
                "matched_asset_id": scene["asset_id"],
                "matched_asset": scene["asset_path"]
            }
            for scene in context.script
        ]
        
        # Log asset usage summary
        asset_usage = {}
        for scene in context.matched_scenes:
            asset_id = scene["matched_asset_id"]
            asset_usage[asset_id] = asset_usage.get(asset_id, 0) + 1
        
        logger.info("📊 Asset usage summary:")
        for asset_id, count in asset_usage.items():
            asset_metadata = self.asset_index.get(asset_id, {})
            logger.info(f"   {asset_metadata.get('name', asset_id)}: {count} scene(s)")
        
        return context
    
    async def initialize_storyboard(self, context: PipelineContext) -> PipelineContext:
        """
        Initialize storyboard from matched scenes
        
        Args:
            context: Pipeline context
        
        Returns:
            Updated context with storyboard
        """
        from datetime import datetime

        from pixelle_video.models.size_contract import GenerationSizeContract
        from pixelle_video.models.storyboard import Storyboard, StoryboardConfig, StoryboardFrame
        
        # Extract all narrations in order for compatibility
        all_narrations = []
        for scene in context.matched_scenes:
            narrations = scene.get("narrations", [scene.get("narration", "")])
            if isinstance(narrations, str):
                narrations = [narrations]
            all_narrations.extend(narrations)
        
        context.narrations = all_narrations
        
        # Get template dimensions
        # Use asset_default.html template which supports both image and video assets
        # (conditionally shows background image or provides transparent overlay)
        template_name = "1080x1920/asset_default.html"
        size_contract = GenerationSizeContract.from_params(context.params)
        
        requested_tts_inference_mode = context.params.get("tts_inference_mode")
        if (
            not requested_tts_inference_mode
            and (context.params.get("voice_id") or context.params.get("tts_voice"))
            and not context.params.get("tts_workflow")
        ):
            requested_tts_inference_mode = "local"
        resolved_tts_inference_mode = resolve_tts_inference_mode(
            self.core.config,
            requested_tts_inference_mode,
        )
        voice_id = None
        if resolved_tts_inference_mode == "local":
            voice_id = (
                context.params.get("tts_voice")
                or context.params.get("voice_id")
                or "zh-CN-YunjianNeural"
            )

        # Create StoryboardConfig
        context.config = StoryboardConfig(
            task_id=context.task_id,
            n_storyboard=len(context.matched_scenes),  # Number of scenes
            min_narration_words=5,
            max_narration_words=50,
            video_fps=30,
            tts_inference_mode=resolved_tts_inference_mode,
            voice_id=voice_id,
            tts_workflow=context.params.get("tts_workflow"),
            ref_audio=context.params.get("ref_audio"),
            ref_audio_text=context.params.get("ref_audio_text"),
            tts_speed=context.params.get("tts_speed", 1.2),
            **resolve_storyboard_render_kwargs(self.core.config, context.params),
            **size_contract.to_params(),
            media_placement=context.params.get("media_placement"),
            frame_template=template_name,
            template_params=context.params.get("template_params")
        )
        self._record_text_rendering_contract_summary(
            context,
            supported_overlay=False,
            disabled_reason=resolve_overlay_disabled_reason(
                context.request.get("text_rendering"),
                "overlay_unsupported",
            ),
        )
        
        # Create Storyboard
        context.storyboard = Storyboard(
            title=context.title,
            config=context.config,
            created_at=datetime.now()
        )
        
        # Create StoryboardFrames - one per scene
        for i, scene in enumerate(context.matched_scenes):
            # Get first narration for the frame (we'll combine audios later)
            narrations = scene.get("narrations", [scene.get("narration", "")])
            if isinstance(narrations, str):
                narrations = [narrations]
            
            # Use first narration as the main text (for subtitle)
            # We'll combine all narrations in the audio
            main_narration = " ".join(narrations)  # Combine for subtitle display
            
            frame = StoryboardFrame(
                index=i,
                narration=main_narration,
                image_prompt=None,  # We're using user assets, not generating images
                created_at=datetime.now()
            )
            
            # Get asset metadata and determine actual media type from asset_index
            asset_id = scene["matched_asset_id"]
            asset_metadata = self.asset_index.get(asset_id)
            if asset_metadata is None:
                raise ValueError(f"matched scene references unknown asset_id: {asset_id}")
            asset_path = str(asset_metadata["path"])
            asset_type = asset_metadata.get("type", "image")
            
            # Set media type and path based on actual asset type
            if asset_type == "video":
                frame.media_type = "video"
                frame.video_path = asset_path
                logger.debug(f"Scene {i}: Using video asset: {Path(asset_path).name}")
            else:
                frame.media_type = "image"
                frame.image_path = asset_path
                logger.debug(f"Scene {i}: Using image asset: {Path(asset_path).name}")
            
            # Store scene info for later audio generation
            frame._scene_data = scene  # Temporary storage for multi-narration
            
            context.storyboard.frames.append(frame)
        
        logger.info(f"✅ Created storyboard with {len(context.storyboard.frames)} scenes")
        
        return context
    
    async def produce_assets(self, context: PipelineContext) -> PipelineContext:
        """
        Generate scene videos using FrameProcessor (asset + multiple narrations + template)
        
        Args:
            context: Pipeline context
        
        Returns:
            Updated context with processed frames
        """
        logger.info("🎬 Producing scene videos...")
        
        storyboard = context.storyboard
        config = context.config
        total_frames = len(storyboard.frames)
        
        # Progress range: 30% - 85% for frame production
        base_progress = 0.30
        progress_range = 0.55  # 85% - 30%
        
        for i, frame in enumerate(storyboard.frames, 1):
            logger.info(f"Producing scene {i}/{total_frames}...")
            
            # Emit progress for this frame (each frame has 4 steps: audio, combine, duration, compose)
            frame_progress = base_progress + (i - 1) / total_frames * progress_range
            self._emit_progress(ProgressEvent(
                event_type="frame_step",
                progress=frame_progress,
                frame_current=i,
                frame_total=total_frames,
                step=1,
                action="audio"
            ))
            
            # Get scene data with narrations
            scene = frame._scene_data
            narrations = scene.get("narrations", [scene.get("narration", "")])
            if isinstance(narrations, str):
                narrations = [narrations]
            
            logger.info(f"Scene {i} has {len(narrations)} narration(s)")
            
            # Step 1: Generate audio for each narration and combine
            narration_audios = []
            for j, narration_text in enumerate(narrations, 1):
                audio_path = Path(context.task_dir) / "frames" / f"{i:02d}_narration_{j}.mp3"
                audio_path.parent.mkdir(parents=True, exist_ok=True)
                
                await self.core.tts(
                    text=narration_text,
                    output_path=str(audio_path),
                    voice_id=config.voice_id,
                    speed=config.tts_speed
                )
                
                narration_audios.append(str(audio_path))
                logger.debug(f"  Narration {j}/{len(narrations)}: {narration_text[:30]}...")
            
            # Concatenate all narration audios for this scene
            if len(narration_audios) > 1:
                
                # Emit progress for combining audio
                frame_progress = base_progress + ((i - 1) + 0.25) / total_frames * progress_range
                self._emit_progress(ProgressEvent(
                    event_type="frame_step",
                    progress=frame_progress,
                    frame_current=i,
                    frame_total=total_frames,
                    step=2,
                    action="audio"
                ))
                
                combined_audio_path = Path(context.task_dir) / "frames" / f"{i:02d}_audio.mp3"
                
                # Use FFmpeg to concatenate audio files
                import subprocess
                
                # Create a file list for FFmpeg concat
                filelist_path = Path(context.task_dir) / "frames" / f"{i:02d}_audiolist.txt"
                with open(filelist_path, 'w') as f:
                    for audio_file in narration_audios:
                        escaped_path = str(Path(audio_file).absolute()).replace("'", "'\\''")
                        f.write(f"file '{escaped_path}'\n")
                
                # Concatenate audio files
                concat_cmd = [
                    'ffmpeg',
                    '-f', 'concat',
                    '-safe', '0',
                    '-i', str(filelist_path),
                    '-c', 'copy',
                    '-y',
                    str(combined_audio_path)
                ]
                
                subprocess.run(concat_cmd, check=True, capture_output=True)
                frame.audio_path = str(combined_audio_path)
                
                logger.info(f"✅ Combined {len(narration_audios)} narrations into one audio")
            else:
                frame.audio_path = narration_audios[0]
            
            # Step 2: Use FrameProcessor to generate composed frame and video
            # FrameProcessor will handle:
            # - Template rendering (with proper dimensions)
            # - Subtitle composition
            # - Video segment creation
            # - Proper file naming in frames/
            
            # Since we already have the audio and image, we bypass some steps
            # by manually calling the composition steps
            
            # Emit progress for duration calculation
            frame_progress = base_progress + ((i - 1) + 0.5) / total_frames * progress_range
            self._emit_progress(ProgressEvent(
                event_type="frame_step",
                progress=frame_progress,
                frame_current=i,
                frame_total=total_frames,
                step=3,
                action="compose"
            ))
            
            # Get audio duration for frame duration
            import subprocess
            duration_cmd = [
                'ffprobe',
                '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                frame.audio_path
            ]
            duration_result = subprocess.run(duration_cmd, capture_output=True, text=True, check=True)
            frame.duration = float(duration_result.stdout.strip())
            
            # Emit progress for video composition
            frame_progress = base_progress + ((i - 1) + 0.75) / total_frames * progress_range
            self._emit_progress(ProgressEvent(
                event_type="frame_step",
                progress=frame_progress,
                frame_current=i,
                frame_total=total_frames,
                step=4,
                action="video"
            ))
            
            # Use FrameProcessor for proper composition
            await self.core.frame_processor(
                frame=frame,
                storyboard=storyboard,
                config=config,
                total_frames=total_frames
            )
            
            logger.success(f"✅ Scene {i} complete")
        
        # Emit completion of frame production
        self._emit_progress(ProgressEvent(
            event_type="processing_frame",
            progress=0.85,
            frame_current=total_frames,
            frame_total=total_frames
        ))
        
        return context
    
    async def post_production(self, context: PipelineContext) -> PipelineContext:
        """
        Concatenate scene videos and add BGM
        
        Args:
            context: Pipeline context
        
        Returns:
            Updated context with final video path
        """
        logger.info("🎞️ Concatenating scenes...")
        
        # Emit progress for concatenation (85% - 95%)
        self._emit_progress(ProgressEvent(
            event_type="concatenating",
            progress=0.86
        ))
        
        # Collect video segments from storyboard frames
        scene_videos = [frame.video_segment_path for frame in context.storyboard.frames]
        
        # Generate filename: use title if provided, otherwise use task_id or default name
        if context.title:
            filename = f"{context.title}.mp4"
        else:
            filename = f"{context.task_id}.mp4"  # Use task_id as filename when title is empty
        
        final_video_path = Path(context.task_dir) / filename
        
        # Get BGM parameters
        bgm_path = context.request.get("bgm_path")
        bgm_volume = context.request.get("bgm_volume", 0.2)
        bgm_mode = context.request.get("bgm_mode", "loop")
        
        if bgm_path:
            logger.info(f"🎵 Adding BGM: {bgm_path} (volume={bgm_volume}, mode={bgm_mode})")
        
        self.core.video.concat_videos(
            videos=scene_videos,
            output=str(final_video_path),
            bgm_path=bgm_path,
            bgm_volume=bgm_volume,
            bgm_mode=bgm_mode
        )
        
        context.final_video_path = str(final_video_path)
        context.storyboard.final_video_path = str(final_video_path)
        
        logger.success(f"✅ Final video: {final_video_path}")
        
        # Emit completion of concatenation
        self._emit_progress(ProgressEvent(
            event_type="concatenating",
            progress=0.95,
            extra_info="complete"
        ))
        
        return context
    
    async def finalize(self, context: PipelineContext) -> PipelineContext:
        """
        Finalize and return result
        
        Args:
            context: Pipeline context
        
        Returns:
            Final context
        """
        logger.success("🎉 Asset-based video generation complete!")
        logger.info(f"Video: {context.final_video_path}")
        
        # Emit completion
        self._emit_progress(ProgressEvent(
            event_type="completed",
            progress=1.0
        ))
        
        # Persist metadata for history tracking
        await self._persist_task_data(context)
        
        return context
    
    async def _persist_task_data(self, ctx: PipelineContext):
        """
        Persist task metadata and storyboard to filesystem for history tracking
        """
        from pathlib import Path
        
        try:
            storyboard = ctx.storyboard
            task_id = ctx.task_id
            
            if not task_id:
                logger.warning("No task_id in context, skipping persistence")
                return
            
            # Get file size
            video_path_obj = Path(ctx.final_video_path)
            file_size = video_path_obj.stat().st_size if video_path_obj.exists() else 0
            
            # Build metadata
            input_params = {
                "text": ctx.input_text,
                "mode": "asset_based",
                "title": ctx.title or "",
                "n_scenes": len(storyboard.frames) if storyboard else 0,
                "assets": ctx.request.get("assets", []),
                "intent": ctx.request.get("intent"),
                "duration": ctx.request.get("duration"),
                "source": ctx.request.get("source"),
                "voice_id": ctx.request.get("voice_id"),
                "tts_speed": ctx.request.get("tts_speed"),
                "render_backend": storyboard.config.render_backend if storyboard else None,
                "text_rendering": ctx.request.get("text_rendering"),
            }
            
            metadata = {
                "task_id": task_id,
                "created_at": storyboard.created_at.isoformat() if storyboard and storyboard.created_at else None,
                "completed_at": storyboard.completed_at.isoformat() if storyboard and storyboard.completed_at else None,
                "status": "completed",
                
                "input": input_params,
                
                "result": {
                    "video_path": ctx.final_video_path,
                    "duration": storyboard.total_duration if storyboard else 0,
                    "file_size": file_size,
                    "n_frames": len(storyboard.frames) if storyboard else 0,
                    **build_text_rendering_result_metadata(
                        ctx.observability,
                        text_render_package_path=TEXT_RENDER_PACKAGE_ARTIFACT_PATH,
                    ),
                },
                
                "config": {
                    "llm_model": self.core.config.get("llm", {}).get("model", "unknown"),
                    "llm_base_url": self.core.config.get("llm", {}).get("base_url", "unknown"),
                    "source": ctx.request.get("source", "runninghub"),
                    "render_backend": storyboard.config.render_backend if storyboard else None,
                },
                "observability": ctx.observability,
            }
            
            # Save metadata
            await self.core.persistence.save_task_metadata(task_id, metadata)
            logger.info(f"💾 Saved task metadata: {task_id}")
            
            # Save storyboard
            if storyboard:
                await self.core.persistence.save_storyboard(task_id, storyboard)
                logger.info(f"💾 Saved storyboard: {task_id}")
            
        except Exception as e:
            logger.error(f"Failed to persist task data: {e}")
            # Don't raise - persistence failure shouldn't break video generation
    
    # Helper methods

    def _record_text_rendering_contract_summary(
        self,
        context: PipelineContext,
        *,
        supported_overlay: bool = False,
        disabled_reason: str = "overlay_unsupported",
    ):
        return record_text_rendering_contract_summary(
            context,
            text_rendering=context.request.get("text_rendering"),
            narrations=getattr(context, "narrations", ()) or (),
            render_backend=getattr(
                getattr(context, "config", None),
                "render_backend",
                None,
            ),
            frame_count=len(getattr(context, "matched_scenes", ()) or ()),
            task_id=getattr(context, "task_id", None),
            task_dir=getattr(context, "task_dir", None),
            supported_overlay=supported_overlay,
            disabled_reason=disabled_reason,
            image_text_status="not_applicable",
        )
    
    def _get_asset_type(self, path: Path) -> str:
        """Determine asset type from file extension"""
        image_exts = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
        video_exts = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
        
        ext = path.suffix.lower()
        
        if ext in image_exts:
            return "image"
        elif ext in video_exts:
            return "video"
        else:
            return "unknown"
    
