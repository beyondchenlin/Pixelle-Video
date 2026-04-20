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
Configuration schema with Pydantic models

Single source of truth for all configuration defaults and validation.
"""
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field, model_validator

from pixelle_video.config.prompt_prefix_library import (
    build_builtin_prompt_prefix_library_dict,
)


class LLMConfig(BaseModel):
    """LLM configuration"""
    api_key: str = Field(default="", description="LLM API Key")
    base_url: str = Field(default="", description="LLM API Base URL")
    model: str = Field(default="", description="LLM Model Name")


class TTSLocalConfig(BaseModel):
    """Local TTS configuration (Edge TTS)"""
    voice: str = Field(default="zh-CN-YunjianNeural", description="Edge TTS voice ID")
    speed: float = Field(default=1.2, ge=0.5, le=2.0, description="Speech speed multiplier (0.5-2.0)")


class TTSComfyUIConfig(BaseModel):
    """ComfyUI TTS configuration"""
    default_workflow: Optional[str] = Field(default=None, description="Default TTS workflow (optional)")


class TTSSubConfig(BaseModel):
    """TTS-specific configuration (under comfyui.tts)"""
    inference_mode: str = Field(default="local", description="TTS inference mode: 'local' or 'comfyui'")
    local: TTSLocalConfig = Field(default_factory=TTSLocalConfig, description="Local TTS (Edge TTS) configuration")
    comfyui: TTSComfyUIConfig = Field(default_factory=TTSComfyUIConfig, description="ComfyUI TTS configuration")
    
    # Backward compatibility: keep default_workflow at top level
    @property
    def default_workflow(self) -> Optional[str]:
        """Get default workflow (for backward compatibility)"""
        return self.comfyui.default_workflow


class PromptPrefixItemConfig(BaseModel):
    """Single prompt prefix library item."""

    id: str
    name: str
    content: str
    style_category_id: str
    scene_category_id: str
    source: Literal["builtin", "manual", "llm"] = Field(default="manual")
    is_builtin: bool = Field(default=False)
    note: str = Field(default="")
    preview_asset_path: Optional[str] = Field(default=None)
    created_at: Optional[str] = Field(default=None)


class PromptPrefixLibraryConfig(BaseModel):
    """Image prompt prefix library configuration."""

    active_prefix_id: Optional[str] = Field(default=None)
    items: list[PromptPrefixItemConfig] = Field(default_factory=list)


class ImageSubConfig(BaseModel):
    """Image-specific configuration (under comfyui.image)"""
    default_workflow: Optional[str] = Field(
        default="selfhost/image_z_image_turbo.json",
        description="Default image workflow (optional)",
    )
    prompt_prefix: str = Field(
        default="Minimalist black-and-white matchstick figure style illustration, clean lines, simple sketch style",
        description="Prompt prefix for all image generation"
    )
    prompt_prefix_library: PromptPrefixLibraryConfig = Field(
        default_factory=lambda: PromptPrefixLibraryConfig.model_validate(
            build_builtin_prompt_prefix_library_dict()
        ),
        description="Reusable image prompt prefix presets",
    )

    @model_validator(mode="before")
    @classmethod
    def preserve_legacy_prompt_prefix_when_library_is_missing(cls, data: Any):
        """Keep upgraded configs on their existing legacy prefix until users pick a library item."""
        if not isinstance(data, dict):
            return data
        if "prompt_prefix_library" in data or "prompt_prefix" not in data:
            return data

        legacy_prefix = data.get("prompt_prefix")
        if not isinstance(legacy_prefix, str) or not legacy_prefix.strip():
            return data

        upgraded = dict(data)
        upgraded_library = build_builtin_prompt_prefix_library_dict()
        upgraded_library["active_prefix_id"] = None
        upgraded["prompt_prefix_library"] = upgraded_library
        return upgraded


class VideoSubConfig(BaseModel):
    """Video-specific configuration (under comfyui.video)"""
    default_workflow: Optional[str] = Field(
        default="runninghub/video_wan2.1_fusionx.json",
        description="Default video workflow (optional)",
    )
    prompt_prefix: str = Field(
        default="Minimalist black-and-white matchstick figure style illustration, clean lines, simple sketch style",
        description="Prompt prefix for all video generation"
    )


class ComfyUIConfig(BaseModel):
    """ComfyUI configuration (includes global settings and service-specific configs)"""
    comfyui_url: str = Field(default="http://127.0.0.1:8188", description="ComfyUI Server URL")
    executor_type: Optional[Literal["http", "websocket"]] = Field(
        default=None,
        description="Optional ComfyUI executor override for selfhost workflows",
    )
    comfyui_api_key: Optional[str] = Field(default=None, description="ComfyUI API Key (optional)")
    runninghub_api_key: Optional[str] = Field(default=None, description="RunningHub API Key (optional)")
    runninghub_concurrent_limit: int = Field(default=1, ge=1, le=10, description="RunningHub concurrent execution limit (1-10)")
    runninghub_instance_type: Optional[str] = Field(default=None, description="RunningHub instance type (optional, set to 'plus' for 48GB VRAM)")
    tts: TTSSubConfig = Field(default_factory=TTSSubConfig, description="TTS-specific configuration")
    image: ImageSubConfig = Field(default_factory=ImageSubConfig, description="Image-specific configuration")
    video: VideoSubConfig = Field(default_factory=VideoSubConfig, description="Video-specific configuration")


class TemplateConfig(BaseModel):
    """Template configuration"""
    default_template: str = Field(
        default="1080x1920/default.html",
        description="Default frame template path"
    )


class PixelleVideoConfig(BaseModel):
    """Pixelle-Video main configuration"""
    project_name: str = Field(default="Pixelle-Video", description="Project name")
    llm: LLMConfig = Field(default_factory=LLMConfig)
    comfyui: ComfyUIConfig = Field(default_factory=ComfyUIConfig)
    template: TemplateConfig = Field(default_factory=TemplateConfig)
    
    def is_llm_configured(self) -> bool:
        """Check if LLM is properly configured"""
        return bool(
            self.llm.api_key and self.llm.api_key.strip() and
            self.llm.base_url and self.llm.base_url.strip() and
            self.llm.model and self.llm.model.strip()
        )
    
    def validate_required(self) -> bool:
        """Validate required configuration"""
        return self.is_llm_configured()
    
    def to_dict(self) -> dict:
        """Convert to dictionary (for backward compatibility)"""
        return self.model_dump()
