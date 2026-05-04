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
Configuration Manager - Singleton pattern

Provides unified access to configuration with automatic validation.
"""
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from .loader import load_config_dict, save_config_dict
from .schema import PixelleVideoConfig


class ConfigManager:
    """
    Configuration Manager (Singleton)
    
    Provides unified access to configuration with automatic validation.
    """
    _instance: Optional['ConfigManager'] = None
    
    def __new__(cls, config_path: str = "config.yaml"):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, config_path: str = "config.yaml"):
        # Only initialize once
        if hasattr(self, '_initialized'):
            return
        
        self.config_path = Path(config_path)
        self.config: PixelleVideoConfig = self._load()
        self._initialized = True
    
    def _load(self) -> PixelleVideoConfig:
        """Load configuration from file"""
        data = load_config_dict(str(self.config_path))
        config = PixelleVideoConfig(**data)
        
        # Validate template path exists
        self._validate_template(config.template.default_template)
        
        return config
    
    def _validate_template(self, template_path: str):
        """Validate that the configured template exists"""
        from pixelle_video.utils.template_util import DEFAULT_IMAGE_TEMPLATE, resolve_template_path
        
        try:
            # Try to resolve the template path
            resolved_path = resolve_template_path(template_path)
            logger.debug(f"Template validation passed: {template_path} -> {resolved_path}")
        except FileNotFoundError as e:
            logger.warning(
                f"Configured default template '{template_path}' not found. "
                f"Will fall back to '{DEFAULT_IMAGE_TEMPLATE}' if needed. Error: {e}"
            )
    
    def reload(self):
        """Reload configuration from file"""
        self.config = self._load()
        logger.info("Configuration reloaded")
    
    def save(self):
        """Save current configuration to file"""
        save_config_dict(self.config.to_dict(), str(self.config_path))
    
    def update(self, updates: dict):
        """
        Update configuration with new values
        
        Args:
            updates: Dictionary of updates (e.g., {"llm": {"api_key": "xxx"}})
        """
        current = self.config.to_dict()
        
        # Deep merge
        def deep_merge(base: dict, updates: dict) -> dict:
            for key, value in updates.items():
                if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                    deep_merge(base[key], value)
                else:
                    base[key] = value
            return base
        
        merged = deep_merge(current, updates)
        self.config = PixelleVideoConfig(**merged)
    
    def get(self, key: str, default: Any = None) -> Any:
        """Dict-like access (for backward compatibility)"""
        return self.config.to_dict().get(key, default)
    
    def validate(self) -> bool:
        """Validate configuration completeness"""
        return self.config.validate_required()
    
    def get_llm_config(self) -> dict:
        """Get LLM configuration as dict"""
        return {
            "api_key": self.config.llm.api_key,
            "base_url": self.config.llm.base_url,
            "model": self.config.llm.model,
        }
    
    def set_llm_config(
        self,
        api_key: str,
        base_url: str,
        model: str,
    ):
        """Set LLM configuration"""
        updates = {
            "api_key": api_key,
            "base_url": base_url,
            "model": model,
        }
        self.update({"llm": updates})
    
    def get_comfyui_config(self) -> dict:
        """Get ComfyUI configuration as dict"""
        return {
            "comfyui_url": self.config.comfyui.comfyui_url,
            "executor_type": self.config.comfyui.executor_type,
            "backend_management_mode": self.config.comfyui.backend_management_mode,
            "pre_generation_cleanup_mode": self.config.comfyui.pre_generation_cleanup_mode,
            "pre_generation_cleanup_timeout_seconds": self.config.comfyui.pre_generation_cleanup_timeout_seconds,
            "model_cleanup_mode": self.config.comfyui.model_cleanup_mode,
            "gguf_cleanup_strategy": self.config.comfyui.gguf_cleanup_strategy,
            "comfyui_api_key": self.config.comfyui.comfyui_api_key,
            "runninghub_api_key": self.config.comfyui.runninghub_api_key,
            "runninghub_concurrent_limit": self.config.comfyui.runninghub_concurrent_limit,
            "runninghub_instance_type": self.config.comfyui.runninghub_instance_type,
            "tts": {
                "default_workflow": self.config.comfyui.tts.default_workflow,
                "inference_mode": self.config.comfyui.tts.inference_mode,
                "local": self.config.comfyui.tts.local.model_dump(),
                "comfyui": self.config.comfyui.tts.comfyui.model_dump(),
            },
            "image": {
                "default_workflow": self.config.comfyui.image.default_workflow,
                "prompt_prefix": self.config.comfyui.image.prompt_prefix,
                "prompt_prefix_library": self.config.comfyui.image.prompt_prefix_library.model_dump(),
            },
            "video": {
                "default_workflow": self.config.comfyui.video.default_workflow,
                "prompt_prefix": self.config.comfyui.video.prompt_prefix,
            }
        }

    def get_image_prompt_prefix_library(self) -> dict:
        """Get image prompt prefix library as dict."""
        return self.config.comfyui.image.prompt_prefix_library.model_dump()

    def get_storyboard_world_preset_library(self) -> dict:
        """Get storyboard world preset library as dict."""
        return self.config.storyboard.world_preset_library.model_dump()

    def get_storyboard_shot_preset_library(self) -> dict:
        """Get storyboard shot preset library as dict."""
        return self.config.storyboard.shot_preset_library.model_dump()

    def set_image_prompt_prefix_library(self, library: dict):
        """Replace image prompt prefix library configuration."""
        self.update({"comfyui": {"image": {"prompt_prefix_library": library}}})

    def set_active_image_prompt_prefix(self, prefix_id: Optional[str]):
        """Set the active image prompt prefix id."""
        library = self.get_image_prompt_prefix_library()
        library["active_prefix_id"] = prefix_id
        self.set_image_prompt_prefix_library(library)
    
    def set_comfyui_config(
        self, 
        comfyui_url: Optional[str] = None,
        executor_type: Optional[str] = None,
        backend_management_mode: Optional[str] = None,
        pre_generation_cleanup_mode: Optional[str] = None,
        pre_generation_cleanup_timeout_seconds: Optional[float] = None,
        model_cleanup_mode: Optional[str] = None,
        gguf_cleanup_strategy: Optional[str] = None,
        comfyui_api_key: Optional[str] = None,
        runninghub_api_key: Optional[str] = None,
        runninghub_concurrent_limit: Optional[int] = None,
        runninghub_instance_type: Optional[str] = None
    ):
        """Set ComfyUI global configuration"""
        updates = {}
        if comfyui_url is not None:
            updates["comfyui_url"] = comfyui_url
        if executor_type is not None:
            updates["executor_type"] = executor_type if executor_type else None
        if backend_management_mode is not None:
            updates["backend_management_mode"] = backend_management_mode
        if pre_generation_cleanup_mode is not None:
            updates["pre_generation_cleanup_mode"] = pre_generation_cleanup_mode
        if pre_generation_cleanup_timeout_seconds is not None:
            updates["pre_generation_cleanup_timeout_seconds"] = pre_generation_cleanup_timeout_seconds
        if model_cleanup_mode is not None:
            updates["model_cleanup_mode"] = model_cleanup_mode
        if gguf_cleanup_strategy is not None:
            updates["gguf_cleanup_strategy"] = gguf_cleanup_strategy
        if comfyui_api_key is not None:
            updates["comfyui_api_key"] = comfyui_api_key
        if runninghub_api_key is not None:
            updates["runninghub_api_key"] = runninghub_api_key
        if runninghub_concurrent_limit is not None:
            updates["runninghub_concurrent_limit"] = runninghub_concurrent_limit
        if runninghub_instance_type is not None:
            # Empty string means disable (treat as None for storage)
            updates["runninghub_instance_type"] = runninghub_instance_type if runninghub_instance_type else None
        
        if updates:
            self.update({"comfyui": updates})
