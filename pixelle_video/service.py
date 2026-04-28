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
Pixelle-Video Core - Service Layer

Provides unified access to all capabilities (LLM, TTS, Image, etc.)
"""

import asyncio
import hashlib
import json
from contextlib import asynccontextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Optional

from comfykit import ComfyKit
from loguru import logger

from pixelle_video.config import config_manager
from pixelle_video.models.video_generation_contract import (
    normalize_standard_video_generation_params,
    validate_standard_video_generation_params,
)
from pixelle_video.pipelines.asset_based import AssetBasedPipeline
from pixelle_video.pipelines.standard import StandardPipeline
from pixelle_video.services.alignment_service import AlignmentService
from pixelle_video.services.audio_edit_service import AudioEditService
from pixelle_video.services.comfyui_maintenance import ComfyUIMaintenanceClient
from pixelle_video.services.frame_processor import FrameProcessor
from pixelle_video.services.generation_coordinator import (
    GenerationCoordinator,
    build_generation_fingerprint,
)
from pixelle_video.services.history_manager import HistoryManager
from pixelle_video.services.hyperframes_project_service import HyperFramesProjectService
from pixelle_video.services.hyperframes_renderer import HyperFramesRenderer
from pixelle_video.services.image_analysis import ImageAnalysisService
from pixelle_video.services.llm_service import LLMService
from pixelle_video.services.media import MediaService
from pixelle_video.services.persistence import PersistenceService
from pixelle_video.services.tts_service import TTSService
from pixelle_video.services.video import VideoService
from pixelle_video.services.video_analysis import VideoAnalysisService
from pixelle_video.utils.os_util import get_output_path


class _LocalComfyUIWorkflowSession:
    def __init__(self) -> None:
        self.init_lock = asyncio.Lock()
        self.execute_lock = asyncio.Lock()
        self.lock_acquired = False
        self.prepared = False


class _LocalComfyUITaskScope:
    def __init__(self) -> None:
        self.used_local_comfyui = False
        self.registered_active_task = False


class PixelleVideoCore:
    """
    Pixelle-Video Core - Service Layer
    
    Provides unified access to all capabilities.
    
    Usage:
        from pixelle_video import pixelle_video
        
        # Initialize
        await pixelle_video.initialize()
        
        # Use capabilities directly
        answer = await pixelle_video.llm("Explain atomic habits")
        audio = await pixelle_video.tts("Hello world")
        media = await pixelle_video.media(prompt="a cat")
        
        # Check active capabilities
        print(f"Using LLM: {pixelle_video.llm.active}")
        print(f"Available TTS: {pixelle_video.tts.available}")
    
    Architecture (Simplified):
        PixelleVideoCore (this class)
          ├── config (configuration)
          ├── llm (LLM service - direct OpenAI SDK)
          ├── tts (TTS service - ComfyKit workflows)
          ├── media (Media service - ComfyKit workflows, supports image & video)
          └── pipelines (video generation pipelines)
              ├── standard (standard workflow)
              ├── asset_based (asset-driven workflow)
              └── ... (explicitly registered private workflows)
    """
    
    def __init__(self, config_path: str = "config.yaml"):
        """
        Initialize Pixelle-Video Core
        
        Args:
            config_path: Path to configuration file
        """
        # Use global config manager singleton
        self.config = config_manager.config.to_dict()
        self._initialized = False
        
        # ComfyKit lazy initialization (created on first use, recreated on config change)
        self._comfykit: Optional[ComfyKit] = None
        self._comfykit_config_hash: Optional[str] = None
        
        # Core services (initialized in initialize())
        self.llm: Optional[LLMService] = None
        self.tts: Optional[TTSService] = None
        self.media: Optional[MediaService] = None
        self.video: Optional[VideoService] = None
        self.frame_processor: Optional[FrameProcessor] = None
        self.persistence: Optional[PersistenceService] = None
        self.history: Optional[HistoryManager] = None
        self.alignment_service: Optional[AlignmentService] = None
        self.audio_edit_service: Optional[AudioEditService] = None
        self.hyperframes_project_service: Optional[HyperFramesProjectService] = None
        self.hyperframes_renderer: Optional[HyperFramesRenderer] = None
        
        # Video generation pipelines (dictionary of pipeline_name -> pipeline_instance)
        self.pipelines = {}
        self.generation_coordinator = GenerationCoordinator()
        self._local_comfyui_execution_lock = asyncio.Lock()
        self._local_comfyui_workflow_session: ContextVar[_LocalComfyUIWorkflowSession | None] = (
            ContextVar("local_comfyui_workflow_session", default=None)
        )
        self._local_comfyui_task_scope: ContextVar[_LocalComfyUITaskScope | None] = (
            ContextVar("local_comfyui_task_scope", default=None)
        )
        self._local_comfyui_task_count_lock = asyncio.Lock()
        self._local_comfyui_active_task_count = 0
        
        # Default pipeline callable (for backward compatibility)
        self.generate_video = None
    
    def _get_comfykit_config(self) -> dict:
        """
        Get current ComfyKit configuration from config_manager
        
        Returns:
            ComfyKit configuration dict
        """
        # Reload config from global config_manager (to support hot reload)
        self.config = config_manager.config.to_dict()
        
        comfyui_config = self.config.get("comfyui", {})
        kit_config = {}
        
        if comfyui_config.get("comfyui_url"):
            kit_config["comfyui_url"] = comfyui_config["comfyui_url"]
        executor_type = comfyui_config.get("executor_type")
        if executor_type:
            kit_config["executor_type"] = executor_type
        elif comfyui_config.get("comfyui_api_key"):
            # WebSocketExecutor in the current ComfyKit version does not send
            # bearer auth headers during the WS handshake, so authenticated
            # selfhost deployments need HTTP unless the user overrides it.
            kit_config["executor_type"] = "http"
        else:
            kit_config["executor_type"] = "websocket"
        if comfyui_config.get("comfyui_api_key"):
            kit_config["api_key"] = comfyui_config["comfyui_api_key"]
        if comfyui_config.get("runninghub_api_key"):
            kit_config["runninghub_api_key"] = comfyui_config["runninghub_api_key"]
        # Only pass instance_type if it has a non-empty value
        instance_type = comfyui_config.get("runninghub_instance_type")
        if instance_type and instance_type.strip():
            kit_config["runninghub_instance_type"] = instance_type
        
        return kit_config
    
    def _compute_comfykit_config_hash(self, config: dict) -> str:
        """
        Compute hash of ComfyKit configuration for change detection
        
        Args:
            config: ComfyKit configuration dict
        
        Returns:
            MD5 hash of config
        """
        # Sort keys for consistent hash
        config_str = json.dumps(config, sort_keys=True)
        return hashlib.md5(config_str.encode()).hexdigest()
    
    async def _get_or_create_comfykit(self) -> ComfyKit:
        """
        Get or create ComfyKit instance (lazy initialization with config change detection)
        
        This method:
        1. Creates ComfyKit on first use (lazy initialization)
        2. Detects configuration changes and recreates instance if needed
        3. Ensures proper cleanup of old instances
        
        Returns:
            ComfyKit instance
        """
        current_config = self._get_comfykit_config()
        current_hash = self._compute_comfykit_config_hash(current_config)
        
        # Check if we need to create or recreate ComfyKit
        if self._comfykit is None or self._comfykit_config_hash != current_hash:
            # Close old instance if exists
            if self._comfykit is not None:
                logger.info("🔄 ComfyUI configuration changed, recreating ComfyKit instance...")
                try:
                    await self._comfykit.close()
                except Exception as e:
                    logger.warning(f"Failed to close old ComfyKit instance: {e}")
                self._comfykit = None
            
            # Create new instance with current config
            logger.info("✨ Creating ComfyKit instance...")
            logger.debug(f"ComfyKit config: {current_config}")
            self._comfykit = ComfyKit(**current_config)
            self._comfykit_config_hash = current_hash
            logger.info("✅ ComfyKit instance created")
        
        return self._comfykit
    
    async def initialize(self):
        """
        Initialize core capabilities
        
        This initializes all services and must be called before using any capabilities.
        Note: ComfyKit is NOT initialized here - it's lazily initialized on first use.
        
        Example:
            await pixelle_video.initialize()
        """
        if self._initialized:
            logger.warning("Pixelle-Video already initialized")
            return
        
        logger.info("🚀 Initializing Pixelle-Video...")
        
        # 1. Initialize core services (ComfyKit will be lazy-loaded later)
        # Initialize services
        self.llm = LLMService(self.config)
        self.tts = TTSService(self.config, core=self)
        self.media = MediaService(self.config, core=self)
        self.image = self.media  # Alias for backward compatibility
        self.image_analysis = ImageAnalysisService(self.config, core=self)
        self.video_analysis = VideoAnalysisService(self.config, core=self)
        self.video = VideoService()
        self.frame_processor = FrameProcessor(self)
        self.persistence = PersistenceService(output_dir=get_output_path())
        self.history = HistoryManager(self.persistence)
        self.alignment_service = AlignmentService()
        self.audio_edit_service = AudioEditService()
        self.hyperframes_project_service = HyperFramesProjectService(output_dir=get_output_path())
        self.hyperframes_renderer = HyperFramesRenderer(self.config)
        
        # 2. Register video generation pipelines
        self.pipelines = {
            "standard": StandardPipeline(self),
            "asset_based": AssetBasedPipeline(self),
        }
        logger.info(f"📹 Registered pipelines: {', '.join(self.pipelines.keys())}")
        
        # 3. Set default pipeline callable (for backward compatibility)
        self.generate_video = self._create_generate_video_wrapper()
        
        self._initialized = True
        logger.info("✅ Pixelle-Video initialized successfully\n")
    
    async def cleanup(self):
        """
        Cleanup resources (close ComfyKit session)
        
        Example:
            await pixelle_video.cleanup()
        """
        if self._comfykit:
            logger.info("🧹 Closing ComfyKit session...")
            try:
                await self._close_comfykit_instance()
                logger.info("✅ ComfyKit session closed")
            except Exception as e:
                logger.error(f"Failed to close ComfyKit: {e}")
            finally:
                self._comfykit = None
                self._comfykit_config_hash = None

    async def _close_comfykit_instance(self) -> None:
        if self._comfykit is None:
            return

        for attr_name in ("_runninghub_executor", "_http_executor", "_websocket_executor"):
            executor = getattr(self._comfykit, attr_name, None)
            close = getattr(executor, "close", None)
            if callable(close):
                await close()

    async def prepare_comfyui_for_local_workflow(self) -> None:
        """Prepare self-hosted ComfyUI before a local workflow execution."""
        self.config = config_manager.config.to_dict()
        comfyui_config = self.config.get("comfyui", {})
        base_url = comfyui_config.get("comfyui_url")
        if not base_url:
            return

        mode = (comfyui_config.get("pre_generation_cleanup_mode") or "force").lower()
        if mode not in {"force", "conservative"}:
            logger.warning(f"Unsupported ComfyUI pre-generation cleanup mode: {mode}")
            return

        client = ComfyUIMaintenanceClient(
            base_url,
            api_key=comfyui_config.get("comfyui_api_key"),
        )
        try:
            await client.cleanup_before_generation(mode)
        except Exception as e:
            raise RuntimeError(f"ComfyUI pre-workflow cleanup failed: {e}") from e

    async def release_comfyui_after_local_workflow(self) -> None:
        """Release self-hosted ComfyUI model/cache state after a local workflow."""
        self.config = config_manager.config.to_dict()
        comfyui_config = self.config.get("comfyui", {})
        base_url = comfyui_config.get("comfyui_url")
        if not base_url:
            return

        client = ComfyUIMaintenanceClient(
            base_url,
            api_key=comfyui_config.get("comfyui_api_key"),
        )
        try:
            await client.free_memory()
        except Exception as e:
            logger.warning(f"ComfyUI post-workflow memory release failed, continuing: {e}")

    async def release_comfyui_after_local_task(self) -> None:
        """Release self-hosted ComfyUI memory once no local video task is active."""
        self.config = config_manager.config.to_dict()
        comfyui_config = self.config.get("comfyui", {})
        base_url = comfyui_config.get("comfyui_url")
        if not base_url:
            return

        mode = (comfyui_config.get("post_generation_cleanup_mode") or "idle").lower()
        if mode == "disabled":
            logger.info("Skipping ComfyUI post-generation memory release by configuration")
            return
        if mode != "idle":
            logger.warning(f"Unsupported ComfyUI post-generation cleanup mode: {mode}")
            return

        client = ComfyUIMaintenanceClient(
            base_url,
            api_key=comfyui_config.get("comfyui_api_key"),
        )
        try:
            async with self._local_comfyui_execution_lock:
                await client.free_memory_when_idle()
        except Exception as e:
            logger.warning(f"ComfyUI post-task memory release failed, continuing: {e}")

    async def _register_local_comfyui_task_use(self) -> None:
        scope = self._local_comfyui_task_scope.get()
        if scope is None:
            return

        scope.used_local_comfyui = True
        if scope.registered_active_task:
            return

        async with self._local_comfyui_task_count_lock:
            if not scope.registered_active_task:
                self._local_comfyui_active_task_count += 1
                scope.registered_active_task = True

    async def _execute_local_comfykit_workflow(self, workflow_input, workflow_params: dict):
        kit = await self._get_or_create_comfykit()
        return await kit.execute(workflow_input, workflow_params)

    async def _execute_scoped_local_comfykit_workflow(self, workflow_input, workflow_params: dict):
        session = self._local_comfyui_workflow_session.get()
        if session is None:
            return await self._execute_local_comfykit_workflow(workflow_input, workflow_params)

        async with session.init_lock:
            if not session.lock_acquired:
                await self._local_comfyui_execution_lock.acquire()
                session.lock_acquired = True
                try:
                    await self.prepare_comfyui_for_local_workflow()
                    session.prepared = True
                    await self._register_local_comfyui_task_use()
                except Exception:
                    session.lock_acquired = False
                    self._local_comfyui_execution_lock.release()
                    raise

        async with session.execute_lock:
            return await self._execute_local_comfykit_workflow(workflow_input, workflow_params)

    @asynccontextmanager
    async def local_comfyui_workflow_session(self):
        """Keep local ComfyUI prepared across a deliberate batch of selfhost workflows."""
        existing_session = self._local_comfyui_workflow_session.get()
        if existing_session is not None:
            yield
            return

        session = _LocalComfyUIWorkflowSession()
        token = self._local_comfyui_workflow_session.set(session)
        try:
            yield
        finally:
            try:
                if session.prepared and self._local_comfyui_task_scope.get() is None:
                    await self.release_comfyui_after_local_workflow()
            finally:
                if session.lock_acquired:
                    self._local_comfyui_execution_lock.release()
                self._local_comfyui_workflow_session.reset(token)

    @asynccontextmanager
    async def local_comfyui_task_scope(self):
        """Defer local ComfyUI memory release until a full video task is finished."""
        existing_scope = self._local_comfyui_task_scope.get()
        if existing_scope is not None:
            yield
            return

        scope = _LocalComfyUITaskScope()
        token = self._local_comfyui_task_scope.set(scope)
        try:
            yield
        finally:
            should_release = False
            try:
                if scope.registered_active_task:
                    async with self._local_comfyui_task_count_lock:
                        self._local_comfyui_active_task_count = max(
                            self._local_comfyui_active_task_count - 1,
                            0,
                        )
                        should_release = self._local_comfyui_active_task_count == 0
            finally:
                self._local_comfyui_task_scope.reset(token)

            if scope.used_local_comfyui and should_release:
                await self.release_comfyui_after_local_task()

    async def execute_comfykit_workflow(
        self,
        workflow_input,
        workflow_params: dict,
        *,
        workflow_source: str,
    ):
        normalized_source = str(workflow_source or "selfhost").lower()
        if normalized_source == "runninghub":
            kit = await self._get_or_create_comfykit()
            return await kit.execute(workflow_input, workflow_params)

        if self._local_comfyui_workflow_session.get() is not None:
            return await self._execute_scoped_local_comfykit_workflow(
                workflow_input,
                workflow_params,
            )

        async with self._local_comfyui_execution_lock:
            await self.prepare_comfyui_for_local_workflow()
            await self._register_local_comfyui_task_use()
            try:
                return await self._execute_local_comfykit_workflow(workflow_input, workflow_params)
            finally:
                if self._local_comfyui_task_scope.get() is None:
                    await self.release_comfyui_after_local_workflow()

    async def execute_comfykit_workflow_file(
        self,
        workflow_path: str | Path,
        workflow_params: dict,
    ):
        path = Path(workflow_path)
        if not path.exists():
            raise FileNotFoundError(f"Workflow file does not exist: {path}")

        with path.open("r", encoding="utf-8") as f:
            workflow_config = json.load(f)

        if not isinstance(workflow_config, dict):
            raise ValueError(f"Workflow file must contain a JSON object: {path}")

        workflow_source = str(workflow_config.get("source") or "selfhost").lower()
        if workflow_source == "runninghub":
            workflow_id = workflow_config.get("workflow_id")
            if not workflow_id:
                raise ValueError(f"RunningHub workflow missing workflow_id: {path}")
            workflow_input = workflow_id
        else:
            workflow_input = str(path)

        return await self.execute_comfykit_workflow(
            workflow_input,
            workflow_params,
            workflow_source=workflow_source,
        )
    
    async def __aenter__(self):
        """Async context manager entry"""
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.cleanup()
    
    def _create_generate_video_wrapper(self):
        """
        Create a wrapper function for generate_video that supports pipeline selection
        
        This maintains backward compatibility while adding pipeline support.
        """
        async def generate_video_wrapper(
            text: str,
            pipeline: str = "standard",
            **kwargs
        ):
            """
            Generate video using specified pipeline
            
            Args:
                text: Input text
                pipeline: Pipeline name ("standard", "book_summary", etc.)
                **kwargs: Pipeline-specific parameters
            
            Returns:
                VideoGenerationResult
            
            Examples:
                # Use standard pipeline (default)
                result = await pixelle_video.generate_video(
                    text="如何提高学习效率",
                    storyboard_mode="smart",
                    storyboard_count_mode="auto",
                )
                
                # Register a private BasePipeline subclass explicitly when building your own workflow.
            """
            if pipeline not in self.pipelines:
                available = ", ".join(self.pipelines.keys())
                raise ValueError(
                    f"Unknown pipeline: '{pipeline}'. "
                    f"Available pipelines: {available}"
                )

            normalized_kwargs = dict(kwargs)
            if pipeline == "standard":
                normalized_kwargs = normalize_standard_video_generation_params(kwargs)
                validate_standard_video_generation_params(
                    normalized_kwargs,
                    config=self.config,
                )

            pipeline_instance = self.pipelines[pipeline]
            fingerprint = build_generation_fingerprint(
                text=text,
                pipeline=pipeline,
                params=normalized_kwargs,
            )

            async def execute_generation():
                return await pipeline_instance(text=text, **normalized_kwargs)

            return await self.generation_coordinator.run(fingerprint, execute_generation)
        
        return generate_video_wrapper
    
    @property
    def project_name(self) -> str:
        """Get project name from config"""
        return self.config.get("project_name", "Pixelle-Video")
    
    def __repr__(self) -> str:
        """String representation"""
        status = "initialized" if self._initialized else "not initialized"
        pipelines = f"pipelines={list(self.pipelines.keys())}" if self._initialized else ""
        return f"<PixelleVideoCore project={self.project_name!r} status={status} {pipelines}>"


# Global instance
pixelle_video = PixelleVideoCore()
