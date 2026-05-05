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
from typing import Any, Optional

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
from pixelle_video.services.comfyui_backend_manager import ManagedComfyUIBackend
from pixelle_video.services.comfyui_backend_registry import ComfyUIBackendRegistry
from pixelle_video.services.comfyui_errors import (
    looks_like_backend_connection_loss,
    looks_like_memory_exhaustion,
)
from pixelle_video.services.comfyui_maintenance import (
    ComfyUIExtensionName,
    ComfyUIMaintenanceClient,
)
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
from pixelle_video.tts_workflow_contract import is_index_tts2_workflow_key
from pixelle_video.tts_workflow_family import is_omnivoice_workflow_key
from pixelle_video.utils.os_util import get_output_path

_GGUF_WORKFLOW_NODE_CLASS_TYPES = frozenset(
    {
        "UnetLoaderGGUF",
        "UnetLoaderGGUFAdvanced",
        "CLIPLoaderGGUF",
        "DualCLIPLoaderGGUF",
        "TripleCLIPLoaderGGUF",
        "QuadrupleCLIPLoaderGGUF",
    }
)
_EXTENSION_RELEASE_CONTEXTS: dict[ComfyUIExtensionName, str] = {
    "indextts2": "index-tts2",
    "gguf": "gguf",
    "omnivoice": "omnivoice",
}


class _LocalComfyUIWorkflowSession:
    def __init__(
        self,
        *,
        backend_role: str,
        release_after_session: bool = False,
    ) -> None:
        self.backend_role = backend_role
        self.init_lock = asyncio.Lock()
        self.execute_lock = asyncio.Lock()
        self.lock_acquired = False
        self.prepared = False
        self.used_extensions: set[ComfyUIExtensionName] = set()
        self.preflighted_extensions: set[ComfyUIExtensionName] = set()
        self.release_after_session = release_after_session


class _LocalComfyUIRoleTaskState:
    def __init__(self) -> None:
        self.used_local_comfyui = False
        self.pending_memory_release = False
        self.pending_extensions: set[ComfyUIExtensionName] = set()
        self.registered_active_task = False
        self.release_failed = False

    @property
    def pending_extension_memory_release(self) -> bool:
        return bool(self.pending_extensions)


class _LocalComfyUITaskScope:
    def __init__(self) -> None:
        self.role_states: dict[str, _LocalComfyUIRoleTaskState] = {}

    def state_for(self, backend_role: str) -> _LocalComfyUIRoleTaskState:
        state = self.role_states.get(backend_role)
        if state is None:
            state = _LocalComfyUIRoleTaskState()
            self.role_states[backend_role] = state
        return state


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
        
        # ComfyKit lazy initialization per backend role (created on first use,
        # recreated on config change)
        self._comfykit_by_backend: dict[str, ComfyKit] = {}
        self._comfykit_config_hash_by_backend: dict[str, str] = {}
        
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
        self._local_comfyui_execution_locks: dict[str, asyncio.Lock] = {}
        self._comfyui_restart_tasks: dict[str, asyncio.Task] = {}
        self._local_comfyui_workflow_session: ContextVar[_LocalComfyUIWorkflowSession | None] = (
            ContextVar("local_comfyui_workflow_session", default=None)
        )
        self._local_comfyui_task_scope: ContextVar[_LocalComfyUITaskScope | None] = (
            ContextVar("local_comfyui_task_scope", default=None)
        )
        self._local_comfyui_task_count_lock = asyncio.Lock()
        self._local_comfyui_active_task_count_by_backend: dict[str, int] = {}
        
        # Default pipeline callable (for backward compatibility)
        self.generate_video = None
    
    def _normalize_comfyui_backend_role(self, backend_role: str | None = "default") -> str:
        return str(backend_role or "default").strip() or "default"

    def _get_backend_lock(self, backend_role: str = "default") -> asyncio.Lock:
        role = self._normalize_comfyui_backend_role(backend_role)
        lock = self._local_comfyui_execution_locks.get(role)
        if lock is None:
            lock = asyncio.Lock()
            self._local_comfyui_execution_locks[role] = lock
        return lock

    def _get_comfykit_config(self, backend_role: str = "default") -> dict:
        """
        Get current ComfyKit configuration from config_manager
        
        Returns:
            ComfyKit configuration dict
        """
        # Reload config from global config_manager (to support hot reload)
        self.config = config_manager.config.to_dict()
        role = self._normalize_comfyui_backend_role(backend_role)
        return self._get_comfyui_backend_registry().get_comfykit_config(role)

    def _get_comfyui_backend_registry(self) -> ComfyUIBackendRegistry:
        self.config = config_manager.config.to_dict()
        return ComfyUIBackendRegistry(
            config_manager.config.comfyui,
            repo_root=Path(__file__).resolve().parents[1],
        )

    def schedule_comfyui_backend_restart(self, backend_role: str, reason: str) -> None:
        role = self._normalize_comfyui_backend_role(backend_role)
        existing_task = self._comfyui_restart_tasks.get(role)
        if existing_task is not None:
            if not existing_task.done():
                logger.info(
                    "ComfyUI backend restart already scheduled; skipping duplicate request "
                    f"for role '{role}' ({reason})"
                )
                return
            if existing_task.cancelled() or existing_task.exception() is not None:
                logger.warning(
                    "ComfyUI backend restart already failed and must be awaited before a new "
                    f"restart can be scheduled for role '{role}'"
                )
                return
            self._comfyui_restart_tasks.pop(role, None)

        self._comfyui_restart_tasks[role] = asyncio.create_task(
            self._restart_comfyui_backend_role(role, reason)
        )

    async def await_comfyui_backend_ready(self, backend_role: str) -> None:
        role = self._normalize_comfyui_backend_role(backend_role)
        task = self._comfyui_restart_tasks.get(role)
        if task is None:
            return

        try:
            await task
        finally:
            if self._comfyui_restart_tasks.get(role) is task and task.done():
                self._comfyui_restart_tasks.pop(role, None)
    
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
    
    async def _get_or_create_comfykit(self, backend_role: str = "default") -> ComfyKit:
        """
        Get or create ComfyKit instance (lazy initialization with config change detection)
        
        This method:
        1. Creates ComfyKit on first use (lazy initialization)
        2. Detects configuration changes and recreates instance if needed
        3. Ensures proper cleanup of old instances
        
        Returns:
            ComfyKit instance
        """
        role = self._normalize_comfyui_backend_role(backend_role)
        current_config = self._get_comfykit_config(role)
        current_hash = self._compute_comfykit_config_hash(current_config)
        existing_kit = self._comfykit_by_backend.get(role)
        existing_hash = self._comfykit_config_hash_by_backend.get(role)
        
        # Check if we need to create or recreate ComfyKit
        if existing_kit is None or existing_hash != current_hash:
            # Close old instance if exists
            if existing_kit is not None:
                logger.info("🔄 ComfyUI configuration changed, recreating ComfyKit instance...")
                try:
                    await existing_kit.close()
                except Exception as e:
                    logger.warning(f"Failed to close old ComfyKit instance: {e}")
                self._comfykit_by_backend.pop(role, None)
                self._comfykit_config_hash_by_backend.pop(role, None)
            
            # Create new instance with current config
            logger.info("✨ Creating ComfyKit instance...")
            logger.debug(f"ComfyKit config: {current_config}")
            self._comfykit_by_backend[role] = ComfyKit(**current_config)
            self._comfykit_config_hash_by_backend[role] = current_hash
            logger.info("✅ ComfyKit instance created")
        
        return self._comfykit_by_backend[role]
    
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
        if self._comfykit_by_backend:
            logger.info("🧹 Closing ComfyKit session...")
            try:
                await self._close_comfykit_instance()
                logger.info("✅ ComfyKit session closed")
            except Exception as e:
                logger.error(f"Failed to close ComfyKit: {e}")
            finally:
                self._comfykit_by_backend.clear()
                self._comfykit_config_hash_by_backend.clear()

    async def _close_comfykit_instance(self, backend_role: str | None = None) -> None:
        if backend_role is None:
            roles = list(self._comfykit_by_backend.keys())
        else:
            role = self._normalize_comfyui_backend_role(backend_role)
            roles = [role] if role in self._comfykit_by_backend else []

        for role in roles:
            kit = self._comfykit_by_backend.get(role)
            if kit is None:
                continue
            for attr_name in ("_runninghub_executor", "_http_executor", "_websocket_executor"):
                executor = getattr(kit, attr_name, None)
                close = getattr(executor, "close", None)
                if callable(close):
                    await close()
            self._comfykit_by_backend.pop(role, None)
            self._comfykit_config_hash_by_backend.pop(role, None)

    def _get_comfyui_maintenance_client(
        self,
        backend_role: str = "default",
    ) -> ComfyUIMaintenanceClient | None:
        role = self._normalize_comfyui_backend_role(backend_role)
        registry = self._get_comfyui_backend_registry()
        try:
            return registry.maintenance_client(role)
        except ValueError:
            return None

    async def prepare_comfyui_for_local_workflow(
        self,
        *,
        backend_role: str = "default",
    ) -> None:
        """Prepare self-hosted ComfyUI before a local workflow execution."""
        role = self._normalize_comfyui_backend_role(backend_role)
        await self.await_comfyui_backend_ready(role)
        self.config = config_manager.config.to_dict()
        comfyui_config = self.config.get("comfyui", {})
        client = self._get_comfyui_maintenance_client(role)
        if client is None:
            return

        mode = (comfyui_config.get("pre_generation_cleanup_mode") or "force").lower()
        if mode not in {"force", "conservative"}:
            logger.warning(f"Unsupported ComfyUI pre-generation cleanup mode: {mode}")
            return

        try:
            await client.cleanup_before_generation(mode)
        except Exception as e:
            raise RuntimeError(f"ComfyUI pre-workflow cleanup failed: {e}") from e

    def _get_comfyui_model_cleanup_mode(self, comfyui_config: dict) -> str:
        mode = (comfyui_config.get("model_cleanup_mode") or "comfyui_and_extensions").lower()
        if mode == "disabled":
            logger.warning(
                "Retired ComfyUI model cleanup mode 'disabled' was ignored; "
                "using 'comfyui_and_extensions' so Pixelle-owned stages release models."
            )
            return "comfyui_and_extensions"
        if mode not in {"comfyui", "comfyui_and_extensions"}:
            logger.warning(f"Unsupported ComfyUI model cleanup mode: {mode}")
            return "comfyui_and_extensions"
        return mode

    def _get_comfyui_backend_management_mode(self, comfyui_config: dict) -> str:
        mode = (comfyui_config.get("backend_management_mode") or "auto").lower()
        if mode not in {"auto", "required", "disabled"}:
            logger.warning(f"Unsupported ComfyUI backend management mode: {mode}")
            return "auto"
        return mode

    def _get_managed_comfyui_backend(
        self,
        backend_role: str = "default",
    ) -> ManagedComfyUIBackend | None:
        role = self._normalize_comfyui_backend_role(backend_role)
        registry = self._get_comfyui_backend_registry()
        try:
            return registry.managed_backend(role)
        except ValueError:
            return None

    async def _restart_comfyui_backend_role(self, backend_role: str, reason: str) -> bool:
        role = self._normalize_comfyui_backend_role(backend_role)
        backend = self._get_managed_comfyui_backend(role)
        if backend is None:
            return False
        restarted = await backend.restart(reason=reason)
        if restarted:
            await self._close_comfykit_instance(role)
        return restarted

    async def restart_managed_comfyui_backend(
        self,
        reason: str,
        *,
        backend_role: str = "default",
    ) -> bool:
        return await self._restart_comfyui_backend_role(backend_role, reason)

    def _log_comfyui_memory_release(
        self,
        *,
        context: str,
        model_cleanup_mode: str,
        result,
    ) -> None:
        if hasattr(result, "to_log_fields"):
            fields = result.to_log_fields()
        else:
            fields = {"released": bool(result)}
        bound_logger = logger.bind(
            channel="runtime",
            event="comfyui_memory_release",
            context=context,
            model_cleanup_mode=model_cleanup_mode,
            **fields,
        )
        if self._is_comfyui_release_confirmed(result):
            bound_logger.info(f"ComfyUI {context} memory release completed")
        else:
            bound_logger.warning(f"ComfyUI {context} memory release not confirmed")

    def _is_comfyui_release_confirmed(self, result) -> bool:
        if hasattr(result, "released"):
            return bool(result.released)
        return bool(result)

    def _log_comfyui_extension_release_preflight(
        self,
        *,
        context: str,
        model_cleanup_mode: str,
        results,
    ) -> None:
        logger.bind(
            channel="runtime",
            event="comfyui_extension_release_preflight",
            context=context,
            model_cleanup_mode=model_cleanup_mode,
            extension_results=[
                result.to_log_dict() if hasattr(result, "to_log_dict") else result
                for result in results
            ],
        ).info(f"ComfyUI {context} extension release preflight completed")

    async def _release_comfyui_memory_when_idle(
        self,
        context: str,
        *,
        backend_role: str = "default",
        include_extensions: bool = False,
        extensions: tuple[ComfyUIExtensionName, ...] = ("indextts2",),
        missing_endpoint: str = "optional",
    ) -> bool:
        self.config = config_manager.config.to_dict()
        comfyui_config = self.config.get("comfyui", {})
        client = self._get_comfyui_maintenance_client(backend_role)
        if client is None:
            return False

        model_cleanup_mode = self._get_comfyui_model_cleanup_mode(comfyui_config)
        try:
            if include_extensions:
                result = await client.free_memory_with_extensions_when_idle(
                    intensity="high",
                    extensions=extensions,
                    missing_endpoint=missing_endpoint,
                )
            else:
                result = await client.free_memory_when_idle(intensity="high")
            self._log_comfyui_memory_release(
                context=context,
                model_cleanup_mode=model_cleanup_mode,
                result=result,
            )
            return self._is_comfyui_release_confirmed(result)
        except Exception as e:
            raise RuntimeError(f"ComfyUI {context} memory release failed: {e}") from e

    async def force_release_comfyui_memory(
        self,
        *,
        context: str,
        backend_role: str = "default",
        include_extensions: bool = False,
        extensions: tuple[ComfyUIExtensionName, ...] = ("indextts2",),
    ) -> bool:
        self.config = config_manager.config.to_dict()
        comfyui_config = self.config.get("comfyui", {})
        client = self._get_comfyui_maintenance_client(backend_role)
        if client is None:
            return False

        try:
            model_cleanup_mode = self._get_comfyui_model_cleanup_mode(comfyui_config)
            if include_extensions or model_cleanup_mode == "comfyui_and_extensions":
                result = await client.free_memory_with_extensions(
                    "high",
                    extensions=extensions,
                    missing_endpoint="required",
                )
            else:
                result = await client.free_memory("high")
            self._log_comfyui_memory_release(
                context=context,
                model_cleanup_mode=model_cleanup_mode,
                result=result,
            )
            return self._is_comfyui_release_confirmed(result)
        except Exception as e:
            logger.warning(f"ComfyUI {context} memory release failed, continuing: {e}")
            return False

    async def preflight_comfyui_extension_release_endpoints(
        self,
        *,
        context: str,
        backend_role: str = "default",
        extensions: tuple[ComfyUIExtensionName, ...] = ("indextts2",),
    ) -> bool:
        self.config = config_manager.config.to_dict()
        comfyui_config = self.config.get("comfyui", {})
        model_cleanup_mode = self._get_comfyui_model_cleanup_mode(comfyui_config)
        client = self._get_comfyui_maintenance_client(backend_role)
        if client is None:
            return False

        try:
            results = await client.preflight_extension_release_endpoints(
                extensions=extensions,
            )
        except Exception as e:
            raise RuntimeError(
                f"ComfyUI {context} extension release endpoint preflight failed: {e}"
            ) from e
        self._log_comfyui_extension_release_preflight(
            context=context,
            model_cleanup_mode=model_cleanup_mode,
            results=results,
        )
        return True

    async def release_comfyui_after_local_workflow_extensions(
        self,
        *,
        context: str,
        backend_role: str = "default",
        extensions: tuple[ComfyUIExtensionName, ...],
        missing_endpoint: str = "required",
    ) -> bool:
        """Restart ComfyUI backend to fully release GPU memory including extension caches."""
        if not extensions:
            return await self.release_comfyui_after_local_workflow(
                backend_role=backend_role
            )

        logger.info(f"[MEMORY_RELEASE] Restarting ComfyUI backend '{backend_role}' (extensions: {extensions}) to release GPU memory...")
        try:
            restarted = await self._restart_comfyui_backend_role(backend_role, f"{context} memory release")
            if restarted:
                logger.info(f"[MEMORY_RELEASE] ComfyUI backend '{backend_role}' restarted successfully (extensions: {extensions})")
            else:
                logger.warning(f"[MEMORY_RELEASE] ComfyUI backend '{backend_role}' restart returned False (extensions: {extensions})")
            self._mark_local_comfyui_released(backend_role=backend_role)
            return True
        except Exception as e:
            logger.error(f"[MEMORY_RELEASE] Failed to restart ComfyUI backend '{backend_role}': {e}")
            raise RuntimeError(
                f"ComfyUI {context} memory release (restart) failed for backend '{backend_role}': {e}"
            ) from e

    async def release_comfyui_after_local_workflow(
        self,
        *,
        backend_role: str = "default",
    ) -> bool:
        """Restart ComfyUI backend to fully release GPU memory after a workflow batch."""
        logger.info(f"[MEMORY_RELEASE] Restarting ComfyUI backend '{backend_role}' (post-workflow) to release GPU memory...")
        try:
            restarted = await self._restart_comfyui_backend_role(backend_role, "post-workflow memory release")
            if restarted:
                logger.info(f"[MEMORY_RELEASE] ComfyUI backend '{backend_role}' restarted successfully (post-workflow)")
            else:
                logger.warning(f"[MEMORY_RELEASE] ComfyUI backend '{backend_role}' restart returned False (post-workflow)")
            self._mark_local_comfyui_released(backend_role=backend_role)
            return True
        except Exception as e:
            logger.error(f"[MEMORY_RELEASE] Failed to restart ComfyUI backend '{backend_role}': {e}")
            raise RuntimeError(
                f"ComfyUI post-workflow memory release (restart) failed for backend '{backend_role}': {e}"
            ) from e

    async def release_comfyui_after_local_task(
        self,
        *,
        backend_role: str = "default",
    ) -> bool:
        """Restart ComfyUI backend once no local video task is active to fully release GPU memory."""
        async with self._get_backend_lock(backend_role):
            logger.info(f"[MEMORY_RELEASE] Restarting ComfyUI backend '{backend_role}' to release GPU memory...")
            try:
                restarted = await self._restart_comfyui_backend_role(backend_role, "post-task memory release")
                if restarted:
                    logger.info(f"[MEMORY_RELEASE] ComfyUI backend '{backend_role}' restarted successfully")
                else:
                    logger.warning(f"[MEMORY_RELEASE] ComfyUI backend '{backend_role}' restart returned False")
                self._mark_local_comfyui_released(backend_role=backend_role)
                return True
            except Exception as e:
                logger.error(f"[MEMORY_RELEASE] Failed to restart ComfyUI backend '{backend_role}': {e}")
                raise RuntimeError(
                    f"ComfyUI post-task memory release (restart) failed for backend '{backend_role}': {e}"
                ) from e

    async def release_comfyui_after_index_tts2_workflow(
        self,
        *,
        context: str,
        backend_role: str = "default",
        missing_endpoint: str = "optional",
    ) -> bool:
        """Release standard ComfyUI memory plus IndexTTS2 plugin-private model cache."""
        return await self.release_comfyui_after_local_workflow_extensions(
            context=context,
            backend_role=backend_role,
            extensions=("indextts2",),
            missing_endpoint=missing_endpoint,
        )

    async def release_comfyui_after_omnivoice_workflow(
        self,
        *,
        context: str,
        backend_role: str = "default",
        missing_endpoint: str = "optional",
    ) -> bool:
        """Release standard ComfyUI memory plus OmniVoice plugin-private model cache."""
        return await self.release_comfyui_after_local_workflow_extensions(
            context=context,
            backend_role=backend_role,
            extensions=("omnivoice",),
            missing_endpoint=missing_endpoint,
        )

    def _mark_local_comfyui_released(self, *, backend_role: str = "default") -> None:
        scope = self._local_comfyui_task_scope.get()
        if scope is not None:
            role_state = scope.state_for(
                self._normalize_comfyui_backend_role(backend_role)
            )
            role_state.pending_memory_release = False
            role_state.pending_extensions.clear()

    def _workflow_extensions(self, workflow_input: Any) -> tuple[ComfyUIExtensionName, ...]:
        extensions: list[ComfyUIExtensionName] = []
        # MARKER_v2: Debug logging added
        logger.warning(f"[MARKER_v2] _workflow_extensions called with: {workflow_input}")
        if is_index_tts2_workflow_key(workflow_input):
            extensions.append("indextts2")
            logger.warning("[MARKER_v2] Detected indextts2 workflow")
        if is_omnivoice_workflow_key(workflow_input):
            extensions.append("omnivoice")
            logger.warning("[MARKER_v2] Detected omnivoice workflow")
        if self._is_gguf_workflow_key(workflow_input):
            extensions.append("gguf")
            logger.warning("[MARKER_v2] Detected gguf workflow")
        logger.warning(f"[MARKER_v2] Final extensions: {extensions}")
        return tuple(dict.fromkeys(extensions))

    def _is_gguf_workflow_key(self, workflow_input: Any) -> bool:
        workflow = self._load_workflow_mapping(workflow_input)
        if workflow is None:
            return False
        return self._workflow_uses_gguf(workflow)

    def _load_workflow_mapping(self, workflow_input: Any) -> dict[str, Any] | None:
        if isinstance(workflow_input, dict):
            return workflow_input

        path = Path(str(workflow_input or ""))
        candidates = [path, Path("workflows") / path]
        if len(path.parts) == 1:
            candidates.append(Path("workflows") / "selfhost" / path)

        for candidate in candidates:
            if not candidate.exists():
                continue
            try:
                with candidate.open("r", encoding="utf-8") as handle:
                    workflow = json.load(handle)
            except Exception:
                continue
            if isinstance(workflow, dict):
                return workflow
        return None

    def _workflow_uses_gguf(self, workflow: dict[str, Any]) -> bool:
        for value in workflow.values():
            if not isinstance(value, dict):
                continue
            class_type = value.get("class_type")
            if class_type in _GGUF_WORKFLOW_NODE_CLASS_TYPES:
                return True
            if self._workflow_uses_gguf(value):
                return True
        return False

    def _register_workflow_extensions(
        self,
        workflow_input: Any,
        *,
        backend_role: str = "default",
    ) -> tuple[ComfyUIExtensionName, ...]:
        extensions = self._workflow_extensions(workflow_input)
        logger.info(f"_register_workflow_extensions: input={workflow_input}, extensions={extensions}")
        if not extensions:
            return ()

        role = self._normalize_comfyui_backend_role(backend_role)
        session = self._local_comfyui_workflow_session.get()
        if session is not None:
            if session.backend_role != role:
                raise RuntimeError(
                    "Current local ComfyUI workflow session is bound to backend role "
                    f"'{session.backend_role}' and cannot register extensions for role '{role}'"
                )
            session.used_extensions.update(extensions)
            logger.info(f"Updated session.used_extensions: {session.used_extensions}")

        scope = self._local_comfyui_task_scope.get()
        if scope is not None:
            scope.state_for(role).pending_extensions.update(extensions)
            logger.info(f"Updated scope.pending_extensions for role {role}: {scope.state_for(role).pending_extensions}")
        else:
            logger.warning(f"No task scope found, extensions not added to pending_extensions for role {role}")
        return extensions

    async def _preflight_extension_release_endpoint_once(
        self,
        extension: ComfyUIExtensionName,
        session: _LocalComfyUIWorkflowSession | None,
        *,
        backend_role: str = "default",
    ) -> None:
        context_suffix = _EXTENSION_RELEASE_CONTEXTS[extension]
        role = session.backend_role if session is not None else self._normalize_comfyui_backend_role(
            backend_role
        )
        if session is not None:
            if extension in session.preflighted_extensions:
                return
            await self.preflight_comfyui_extension_release_endpoints(
                context=f"pre-{context_suffix}-workflow",
                backend_role=role,
                extensions=(extension,),
            )
            session.preflighted_extensions.add(extension)
            return

        await self.preflight_comfyui_extension_release_endpoints(
            context=f"pre-{context_suffix}-workflow",
            backend_role=role,
            extensions=(extension,),
        )

    async def _preflight_workflow_extensions_once(
        self,
        extensions: tuple[ComfyUIExtensionName, ...],
        session: _LocalComfyUIWorkflowSession | None,
        *,
        backend_role: str = "default",
    ) -> None:
        for extension in extensions:
            await self._preflight_extension_release_endpoint_once(
                extension,
                session,
                backend_role=backend_role,
            )

    async def _release_workflow_extensions(
        self,
        extensions: tuple[ComfyUIExtensionName, ...],
        *,
        context_prefix: str,
        backend_role: str = "default",
        missing_endpoint: str = "required",
    ) -> bool:
        role = self._normalize_comfyui_backend_role(backend_role)
        if not extensions:
            released = await self.release_comfyui_after_local_workflow(
                backend_role=role
            )
            if released:
                self._mark_local_comfyui_released(backend_role=role)
            return released
        if extensions == ("indextts2",):
            released = await self.release_comfyui_after_index_tts2_workflow(
                context=f"{context_prefix}-index-tts2-workflow",
                backend_role=role,
                missing_endpoint=missing_endpoint,
            )
            if released:
                self._mark_local_comfyui_released(backend_role=role)
            return released
        if len(extensions) == 1:
            suffix = _EXTENSION_RELEASE_CONTEXTS[extensions[0]]
            context = f"{context_prefix}-{suffix}-workflow"
        else:
            suffix = "-".join(_EXTENSION_RELEASE_CONTEXTS[extension] for extension in extensions)
            context = f"{context_prefix}-{suffix}-workflow"
        released = await self.release_comfyui_after_local_workflow_extensions(
            context=context,
            backend_role=role,
            extensions=extensions,
            missing_endpoint=missing_endpoint,
        )
        if released:
            self._mark_local_comfyui_released(backend_role=role)
        return released

    async def _release_local_comfyui_after_workflow_session(
        self,
        session: _LocalComfyUIWorkflowSession,
    ) -> None:
        if not session.prepared:
            return

        # Determine whether to release based on session flag or task scope.
        # When inside a task scope, always defer release to task exit to avoid
        # unload/reload thrash between frames (e.g., GGUF model batch generation).
        in_task_scope = self._local_comfyui_task_scope.get() is not None
        if in_task_scope:
            should_release = False
        else:
            should_release = session.release_after_session

        extensions = tuple(sorted(session.used_extensions))
        if extensions:
            if should_release:
                try:
                    released = await self._release_workflow_extensions(
                        extensions,
                        context_prefix="post",
                        backend_role=session.backend_role,
                        missing_endpoint="required",
                    )
                    if released:
                        self._mark_local_comfyui_released(backend_role=session.backend_role)
                except Exception:
                    scope = self._local_comfyui_task_scope.get()
                    if scope is not None:
                        scope.state_for(session.backend_role).release_failed = True
                    raise
            return

        if should_release:
            try:
                await self.release_comfyui_after_local_workflow(
                    backend_role=session.backend_role
                )
            except Exception:
                scope = self._local_comfyui_task_scope.get()
                if scope is not None:
                    scope.state_for(session.backend_role).release_failed = True
                raise

    async def _register_local_comfyui_task_use(
        self,
        *,
        backend_role: str = "default",
    ) -> None:
        scope = self._local_comfyui_task_scope.get()
        if scope is None:
            return

        role = self._normalize_comfyui_backend_role(backend_role)
        role_state = scope.state_for(role)
        role_state.used_local_comfyui = True
        role_state.pending_memory_release = True
        if role_state.registered_active_task:
            return

        async with self._local_comfyui_task_count_lock:
            if not role_state.registered_active_task:
                current_count = self._local_comfyui_active_task_count_by_backend.get(role, 0)
                self._local_comfyui_active_task_count_by_backend[role] = current_count + 1
                role_state.registered_active_task = True

    async def _execute_local_comfykit_workflow_once(
        self,
        workflow_input,
        workflow_params: dict,
        *,
        backend_role: str = "default",
    ):
        kit = await self._get_or_create_comfykit(backend_role)
        return await kit.execute(workflow_input, workflow_params)

    async def _execute_local_comfykit_workflow(
        self,
        workflow_input,
        workflow_params: dict,
        *,
        backend_role: str = "default",
    ):
        role = self._normalize_comfyui_backend_role(backend_role)
        try:
            return await self._execute_local_comfykit_workflow_once(
                workflow_input,
                workflow_params,
                backend_role=role,
            )
        except Exception as exc:
            if looks_like_backend_connection_loss(str(exc)):
                restarted = await self._restart_comfyui_backend_role(
                    role,
                    "connection_lost_during_workflow",
                )
                if restarted:
                    logger.warning(
                        "Local ComfyUI workflow lost its backend connection; "
                        "restarted managed backend and retrying once."
                    )
                    await self.prepare_comfyui_for_local_workflow(backend_role=role)
                    await self._register_local_comfyui_task_use(backend_role=role)
                    return await self._execute_local_comfykit_workflow_once(
                        workflow_input,
                        workflow_params,
                        backend_role=role,
                    )
            if not looks_like_memory_exhaustion(str(exc)):
                raise

            logger.warning(
                "Local ComfyUI workflow ran out of memory on backend role "
                f"'{role}'; releasing memory and retrying once after backend recovery."
            )
            extensions = self._workflow_extensions(workflow_input)
            if extensions:
                released = await self.force_release_comfyui_memory(
                    context="oom-recovery",
                    backend_role=role,
                    include_extensions=True,
                    extensions=extensions,
                )
            else:
                released = await self.force_release_comfyui_memory(
                    context="oom-recovery",
                    backend_role=role,
                )
            restarted = await self._restart_comfyui_backend_role(role, "oom-recovery")
            if not released and not restarted:
                raise RuntimeError(
                    "Local ComfyUI workflow ran out of memory and Pixelle stopped "
                    "before retrying without confirmed memory release."
                ) from exc
            await self.prepare_comfyui_for_local_workflow(backend_role=role)
            await self._register_local_comfyui_task_use(backend_role=role)
            return await self._execute_local_comfykit_workflow_once(
                workflow_input,
                workflow_params,
                backend_role=role,
            )

    async def _execute_scoped_local_comfykit_workflow(
        self,
        workflow_input,
        workflow_params: dict,
        *,
        backend_role: str = "default",
    ):
        role = self._normalize_comfyui_backend_role(backend_role)
        session = self._local_comfyui_workflow_session.get()
        if session is None:
            return await self._execute_local_comfykit_workflow(
                workflow_input,
                workflow_params,
                backend_role=role,
            )
        if session.backend_role != role:
            raise RuntimeError(
                "Current local ComfyUI workflow session is bound to backend role "
                f"'{session.backend_role}' and cannot execute role '{role}'"
            )

        backend_lock = self._get_backend_lock(role)
        async with session.init_lock:
            if not session.lock_acquired:
                await self.await_comfyui_backend_ready(role)
                await backend_lock.acquire()
                session.lock_acquired = True
                try:
                    await self.prepare_comfyui_for_local_workflow(backend_role=role)
                    session.prepared = True
                    await self._register_local_comfyui_task_use(backend_role=role)
                except Exception:
                    session.lock_acquired = False
                    backend_lock.release()
                    raise

        async with session.execute_lock:
            extensions = self._register_workflow_extensions(
                workflow_input,
                backend_role=role,
            )
            if extensions:
                await self._preflight_workflow_extensions_once(
                    extensions,
                    session,
                    backend_role=role,
                )
            return await self._execute_local_comfykit_workflow(
                workflow_input,
                workflow_params,
                backend_role=role,
            )

    @asynccontextmanager
    async def local_comfyui_workflow_session(
        self,
        *,
        backend_role: str = "default",
        release_after_session: bool = False,
    ):
        """Keep local ComfyUI prepared across a deliberate batch of selfhost workflows."""
        role = self._normalize_comfyui_backend_role(backend_role)
        existing_session = self._local_comfyui_workflow_session.get()
        if existing_session is not None:
            if existing_session.backend_role == role and release_after_session:
                existing_session.release_after_session = True
            if existing_session.backend_role == role:
                yield
                return

        session = _LocalComfyUIWorkflowSession(
            backend_role=role,
            release_after_session=release_after_session
        )
        token = self._local_comfyui_workflow_session.set(session)
        body_failed = False
        try:
            yield
        except BaseException:
            body_failed = True
            raise
        finally:
            try:
                try:
                    await self._release_local_comfyui_after_workflow_session(session)
                except Exception as exc:
                    if not body_failed:
                        raise
                    logger.warning(
                        "ComfyUI workflow-session memory release failed while "
                        f"unwinding a failed workflow; preserving original error: {exc}"
                    )
            finally:
                if session.lock_acquired:
                    self._get_backend_lock(session.backend_role).release()
                self._local_comfyui_workflow_session.reset(token)

    @asynccontextmanager
    async def local_comfyui_task_scope(self):
        """Track local ComfyUI use so failed batch releases can be retried at task exit."""
        existing_scope = self._local_comfyui_task_scope.get()
        if existing_scope is not None:
            yield
            return

        scope = _LocalComfyUITaskScope()
        token = self._local_comfyui_task_scope.set(scope)
        body_failed = False
        try:
            yield
        except BaseException:
            body_failed = True
            raise
        finally:
            try:
                roles_ready_for_release: list[str] = []
                for role, role_state in scope.role_states.items():
                    if not role_state.registered_active_task:
                        continue
                    async with self._local_comfyui_task_count_lock:
                        current_count = self._local_comfyui_active_task_count_by_backend.get(
                            role,
                            0,
                        )
                        next_count = max(current_count - 1, 0)
                        if next_count == 0:
                            self._local_comfyui_active_task_count_by_backend.pop(role, None)
                            roles_ready_for_release.append(role)
                        else:
                            self._local_comfyui_active_task_count_by_backend[role] = next_count

                for role in roles_ready_for_release:
                    role_state = scope.state_for(role)
                    if (
                        role_state.pending_extension_memory_release
                        and not role_state.release_failed
                    ):
                        try:
                            await self._release_workflow_extensions(
                                tuple(sorted(role_state.pending_extensions)),
                                context_prefix="post-task",
                                backend_role=role,
                                missing_endpoint="required",
                            )
                        except Exception as exc:
                            role_state.release_failed = True
                            if not body_failed:
                                raise
                            logger.warning(
                                "ComfyUI post-task extension fallback release failed while "
                                f"unwinding a failed task; preserving original error: {exc}"
                            )

                    if (
                        role_state.used_local_comfyui
                        and role_state.pending_memory_release
                        and not role_state.release_failed
                    ):
                        try:
                            await self.release_comfyui_after_local_task(
                                backend_role=role
                            )
                        except Exception as exc:
                            role_state.release_failed = True
                            if not body_failed:
                                raise
                            logger.warning(
                                "ComfyUI post-task fallback release failed while unwinding "
                                f"a failed task; preserving original error: {exc}"
                            )
            finally:
                self._local_comfyui_task_scope.reset(token)

    def _should_release_local_comfyui_after_workflow(self) -> bool:
        # A task scope means more selfhost workflows are likely imminent inside the
        # same Pixelle pipeline. Deferring release to task exit avoids unload/reload
        # thrash and the server-side GGUF unload crashes we observed between frames.
        return self._local_comfyui_task_scope.get() is None

    async def execute_comfykit_workflow(
        self,
        workflow_input,
        workflow_params: dict,
        *,
        workflow_source: str,
        backend_role: str = "default",
    ):
        normalized_source = str(workflow_source or "selfhost").lower()
        if normalized_source == "runninghub":
            kit = await self._get_or_create_comfykit("default")
            return await kit.execute(workflow_input, workflow_params)

        role = self._normalize_comfyui_backend_role(backend_role)
        session = self._local_comfyui_workflow_session.get()
        if session is not None:
            return await self._execute_scoped_local_comfykit_workflow(
                workflow_input,
                workflow_params,
                backend_role=role,
            )

        await self.await_comfyui_backend_ready(role)
        async with self._get_backend_lock(role):
            await self.prepare_comfyui_for_local_workflow(backend_role=role)
            await self._register_local_comfyui_task_use(backend_role=role)
            extensions = self._register_workflow_extensions(
                workflow_input,
                backend_role=role,
            )
            if extensions:
                await self._preflight_workflow_extensions_once(
                    extensions,
                    session,
                    backend_role=role,
                )
            workflow_failed = False
            try:
                return await self._execute_local_comfykit_workflow(
                    workflow_input,
                    workflow_params,
                    backend_role=role,
                )
            except BaseException:
                workflow_failed = True
                raise
            finally:
                if self._should_release_local_comfyui_after_workflow():
                    try:
                        await self._release_workflow_extensions(
                            extensions,
                            context_prefix="post",
                            backend_role=role,
                            missing_endpoint="required",
                        )
                    except Exception as exc:
                        if not workflow_failed:
                            raise
                        logger.warning(
                            "ComfyUI workflow release failed while unwinding a failed "
                            f"workflow; preserving original error: {exc}"
                        )

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
            backend_role = "default"
        else:
            workflow_input = str(path)
            backend_role = self._get_comfyui_backend_registry().resolve_role_for_workflow(
                str(path)
            )

        return await self.execute_comfykit_workflow(
            workflow_input,
            workflow_params,
            workflow_source=workflow_source,
            backend_role=backend_role,
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
