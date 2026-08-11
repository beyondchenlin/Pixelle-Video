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
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Literal, Optional

from loguru import logger
from pydantic import BaseModel, Field, field_validator, model_validator

from pixelle_video.config.prompt_prefix_library import (
    build_builtin_prompt_prefix_library_dict,
    normalize_prompt_prefix_workflow_preview_assets,
    normalize_prompt_prefix_workflow_preview_entry,
)
from pixelle_video.config.storyboard_preset_library import (
    build_builtin_shot_preset_library_dict,
    build_builtin_world_preset_library_dict,
)
from pixelle_video.config.tts_defaults import DEFAULT_TTS_INFERENCE_MODE
from pixelle_video.config.workflow_defaults import (
    DEFAULT_TTS_WORKFLOW,
    upgrade_legacy_default_tts_workflow,
)
from pixelle_video.models.storyboard_limits import (
    DEFAULT_STORYBOARD_GENERATION_LIMITS,
    DETERMINISTIC_STORYBOARD_MAX_SCENE_COUNT_MAX,
)
from pixelle_video.models.storyboard_planning import ContentMode, ShotOverridePolicy
from pixelle_video.render_backend import DEFAULT_RENDER_BACKEND, RenderBackend
from pixelle_video.tts_audio_strategy import DEFAULT_TTS_AUDIO_STRATEGY, TTSAudioStrategy
from pixelle_video.tts_split_strategy import DEFAULT_TTS_SPLIT_MODE, TtsSplitMode
from pixelle_video.utils.template_util import DEFAULT_IMAGE_TEMPLATE


class ProviderTransportConfig(BaseModel):
    """Shared transport limits for OpenAI-compatible providers."""

    connect_timeout_seconds: float = Field(default=10.0, gt=0, description="Provider HTTP connect timeout")
    read_timeout_seconds: float = Field(default=180.0, gt=0, description="Provider HTTP read timeout")
    write_timeout_seconds: float = Field(default=30.0, gt=0, description="Provider HTTP write timeout")
    pool_timeout_seconds: float = Field(default=10.0, gt=0, description="Provider HTTP connection-pool timeout")
    max_retries: int = Field(default=1, ge=0, le=5, description="Provider HTTP retry count")


class LLMConfig(ProviderTransportConfig):
    """LLM configuration"""

    api_key: str = Field(default="", description="LLM API Key")
    base_url: str = Field(default="", description="LLM API Base URL")
    model: str = Field(default="", description="LLM Model Name")
    max_input_tokens: Optional[int] = Field(default=None, description="Override model max input tokens (e.g. 30720 for qwen-max)")
    max_output_tokens: Optional[int] = Field(default=None, description="Override model max output tokens (e.g. 8192 for qwen-max)")


class TTSLocalConfig(BaseModel):
    """Local TTS configuration (Edge TTS)"""
    voice: str = Field(default="zh-CN-YunjianNeural", description="Edge TTS voice ID")
    speed: float = Field(default=1.2, ge=0.5, le=2.0, description="Speech speed multiplier (0.5-2.0)")


class TTSComfyUIConfig(BaseModel):
    """ComfyUI TTS configuration"""
    default_workflow: Optional[str] = Field(
        default=DEFAULT_TTS_WORKFLOW,
        description="Default TTS workflow (optional)",
    )


class TTSSubConfig(BaseModel):
    """TTS-specific configuration (under comfyui.tts)"""
    inference_mode: str = Field(
        default=DEFAULT_TTS_INFERENCE_MODE,
        description="TTS inference mode: 'local' or 'comfyui'",
    )
    local: TTSLocalConfig = Field(default_factory=TTSLocalConfig, description="Local TTS (Edge TTS) configuration")
    comfyui: TTSComfyUIConfig = Field(default_factory=TTSComfyUIConfig, description="ComfyUI TTS configuration")

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_default_workflow(cls, data: Any):
        if not isinstance(data, dict):
            return data

        legacy_default_workflow = data.get("default_workflow")
        if not isinstance(legacy_default_workflow, str) or not legacy_default_workflow.strip():
            return data

        comfyui_data = data.get("comfyui")
        comfyui_default_workflow = None
        if isinstance(comfyui_data, dict):
            comfyui_default_workflow = comfyui_data.get("default_workflow")
        elif hasattr(comfyui_data, "default_workflow"):
            comfyui_default_workflow = getattr(comfyui_data, "default_workflow")
        if comfyui_default_workflow:
            return data

        migrated = dict(data)
        if isinstance(comfyui_data, dict):
            migrated_comfyui = dict(comfyui_data)
        elif hasattr(comfyui_data, "model_dump"):
            migrated_comfyui = comfyui_data.model_dump()
        else:
            migrated_comfyui = {}
        migrated_comfyui["default_workflow"] = legacy_default_workflow
        migrated["comfyui"] = migrated_comfyui
        return migrated

    # Backward compatibility: keep default_workflow at top level
    @property
    def default_workflow(self) -> Optional[str]:
        """Get default workflow (for backward compatibility)"""
        return self.comfyui.default_workflow


class PromptPrefixWorkflowPreviewAssetConfig(BaseModel):
    """Workflow-scoped prompt-prefix preview metadata."""

    asset_path: str
    reference_prompt: Optional[str] = Field(default=None)
    generated_at: Optional[str] = Field(default=None)
    status: str = Field(default="ready")

    @model_validator(mode="before")
    @classmethod
    def normalize_preview_record(cls, data: Any):
        normalized = normalize_prompt_prefix_workflow_preview_entry(data)
        if normalized is None:
            raise ValueError("workflow preview entry is required")
        return normalized


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
    workflow_preview_assets: dict[str, PromptPrefixWorkflowPreviewAssetConfig] = Field(default_factory=dict)
    style_contract_kind: Literal["legacy_text", "visual_style_contract"] = Field(default="legacy_text")
    visual_style_contract: Optional[dict[str, Any]] = Field(default=None)
    visual_style_layers: list[dict[str, Any]] = Field(default_factory=list)
    integration_rules: list[str] = Field(default_factory=list)
    negative_rules: list[str] = Field(default_factory=list)
    created_at: Optional[str] = Field(default=None)

    @model_validator(mode="before")
    @classmethod
    def normalize_workflow_preview_assets(cls, data: Any):
        if not isinstance(data, dict):
            return data

        normalized = dict(data)
        normalized["workflow_preview_assets"] = normalize_prompt_prefix_workflow_preview_assets(
            normalized.get("workflow_preview_assets")
        )
        return normalized


class PromptPrefixLibraryConfig(BaseModel):
    """Image prompt prefix library configuration."""

    active_prefix_id: Optional[str] = Field(default=None)
    items: list[PromptPrefixItemConfig] = Field(default_factory=list)


class ImageSubConfig(BaseModel):
    """Image-specific configuration (under comfyui.image)"""
    default_workflow: Optional[str] = Field(
        default="selfhost/image_z_image_turbo_gguf.json",
        description="Default image workflow (optional)",
    )
    prompt_prefix: str = Field(
        default="Minimalist black-and-white matchstick figure style illustration, clean lines, simple sketch style",
        description="Legacy image prompt prefix retained for config compatibility; not used as an implicit style source"
    )
    prompt_prefix_library: PromptPrefixLibraryConfig = Field(
        default_factory=lambda: PromptPrefixLibraryConfig.model_validate(
            build_builtin_prompt_prefix_library_dict()
        ),
        description="Reusable image prompt prefix presets",
    )

    @model_validator(mode="before")
    @classmethod
    def attach_empty_library_for_legacy_prompt_prefix_configs(cls, data: Any):
        """Attach a library shell for old configs without activating retired prefix text."""
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


def _deep_merge_dicts(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in overlay.items():
        base_value = merged.get(key)
        if isinstance(base_value, dict) and isinstance(value, dict):
            merged[key] = _deep_merge_dicts(base_value, value)
        else:
            merged[key] = value
    return merged


def _normalize_storyboard_library_item(incoming_item: Any) -> dict[str, Any]:
    if isinstance(incoming_item, dict):
        incoming_payload = incoming_item
    elif hasattr(incoming_item, "model_dump"):
        incoming_payload = incoming_item.model_dump(exclude_unset=True)
    else:
        raise ValueError("malformed storyboard preset item: expected mapping-like input")

    preset_id = incoming_payload.get("preset_id")
    if not isinstance(preset_id, str) or not preset_id.strip():
        raise ValueError("malformed storyboard preset item: missing preset_id")

    return incoming_payload


def _merge_storyboard_library_items(default_items: list[dict[str, Any]], incoming_items: list[Any]) -> list[dict[str, Any]]:
    merged_by_id = {
        item["preset_id"]: dict(item)
        for item in default_items
        if isinstance(item, dict) and item.get("preset_id")
    }
    incoming_new_ids: list[str] = []

    for incoming_item in incoming_items:
        incoming_payload = _normalize_storyboard_library_item(incoming_item)
        preset_id = incoming_payload["preset_id"]

        merged_by_id[preset_id] = _deep_merge_dicts(merged_by_id.get(preset_id, {}), incoming_payload)
        if preset_id not in {item["preset_id"] for item in default_items if item.get("preset_id")}:
            incoming_new_ids.append(preset_id)

    ordered_items: list[dict[str, Any]] = []
    seen: set[str] = set()

    for item in default_items:
        preset_id = item.get("preset_id")
        if not preset_id or preset_id in seen:
            continue
        ordered_items.append(merged_by_id[preset_id])
        seen.add(preset_id)

    for preset_id in incoming_new_ids:
        if preset_id in seen:
            continue
        ordered_items.append(merged_by_id[preset_id])
        seen.add(preset_id)

    return ordered_items


class StoryboardWorldPresetItemConfig(BaseModel):
    """Single storyboard world preset definition."""

    preset_id: str
    display_name: str
    display_name_key: Optional[str] = Field(default=None)
    description_key: Optional[str] = Field(default=None)
    supported_modes: list[ContentMode] = Field(default_factory=list)
    style_core: str = Field(default="")
    world_elements: list[str] = Field(default_factory=list)
    knowledge_scene_rules: list[str] = Field(default_factory=list)
    negative_rules: list[str] = Field(default_factory=list)
    default_shot_preset_ids: list[str] = Field(default_factory=list)
    cast_slots: list[dict[str, Any]] = Field(default_factory=list)
    cast_slots_by_mode: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    conservative_fallback_mode: ContentMode = Field(default="concept_explainer")
    safe_default: bool = Field(default=False)
    forced_mode: Optional[ContentMode] = Field(default=None)

    @model_validator(mode="after")
    def validate_world_preset_consistency(self):
        supported_modes = set(self.supported_modes)
        if self.conservative_fallback_mode not in supported_modes:
            raise ValueError(
                f"world preset {self.preset_id} conservative_fallback_mode must be one of supported_modes"
            )

        if self.forced_mode is not None and self.forced_mode not in supported_modes:
            raise ValueError(f"world preset {self.preset_id} forced_mode must be one of supported_modes")

        cast_modes = set(self.cast_slots_by_mode.keys())
        if not cast_modes.issubset(supported_modes):
            unsupported_modes = sorted(cast_modes - supported_modes)
            raise ValueError(
                f"world preset {self.preset_id} cast_slots_by_mode contains unsupported modes: "
                f"{', '.join(unsupported_modes)}"
            )

        if len(supported_modes) > 1 and cast_modes != supported_modes:
            missing_modes = sorted(supported_modes - cast_modes)
            raise ValueError(
                f"world preset {self.preset_id} cast_slots_by_mode must cover all supported modes: "
                f"{', '.join(missing_modes)}"
            )

        return self


class StoryboardWorldPresetLibraryConfig(BaseModel):
    """Storyboard world preset library configuration."""

    default_world_preset_id: str = Field(default="neutral_knowledge_storyboard")
    items: list[StoryboardWorldPresetItemConfig] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def merge_builtin_world_library_defaults(cls, data: Any):
        if not isinstance(data, dict):
            return data

        builtins = build_builtin_world_preset_library_dict()
        merged = dict(builtins)

        if "default_world_preset_id" in data and data["default_world_preset_id"] is not None:
            merged["default_world_preset_id"] = data["default_world_preset_id"]

        incoming_items = data.get("items")
        if incoming_items is not None:
            merged["items"] = _merge_storyboard_library_items(builtins["items"], incoming_items)

        return merged

    @model_validator(mode="after")
    def validate_default_world_preset_id_exists(self):
        preset_ids = {item.preset_id for item in self.items}
        if self.default_world_preset_id not in preset_ids:
            raise ValueError(f"unknown default_world_preset_id: {self.default_world_preset_id}")
        return self


class StoryboardShotPresetItemConfig(BaseModel):
    """Single storyboard shot preset definition."""

    preset_id: str
    display_name: str
    display_name_key: Optional[str] = Field(default=None)
    description_key: Optional[str] = Field(default=None)
    supported_scene_count: list[int] = Field(default_factory=list)
    max_consecutive_same: int = Field(default=2)
    shot_distribution_rules: list[str] = Field(default_factory=list)
    opening_rules: list[str] = Field(default_factory=list)
    closing_rules: list[str] = Field(default_factory=list)
    transition_rules: list[str] = Field(default_factory=list)
    purpose_bias: str = Field(default="")
    override_policy: ShotOverridePolicy = Field(default="adaptive")


class StoryboardShotPresetLibraryConfig(BaseModel):
    """Storyboard shot preset library configuration."""

    default_shot_preset_id: str = Field(default="balanced_explainer")
    items: list[StoryboardShotPresetItemConfig] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def merge_builtin_shot_library_defaults(cls, data: Any):
        if not isinstance(data, dict):
            return data

        builtins = build_builtin_shot_preset_library_dict()
        merged = dict(builtins)

        if "default_shot_preset_id" in data and data["default_shot_preset_id"] is not None:
            merged["default_shot_preset_id"] = data["default_shot_preset_id"]

        incoming_items = data.get("items")
        if incoming_items is not None:
            merged["items"] = _merge_storyboard_library_items(builtins["items"], incoming_items)

        return merged

    @model_validator(mode="after")
    def validate_default_shot_preset_id_exists(self):
        preset_ids = {item.preset_id for item in self.items}
        if self.default_shot_preset_id not in preset_ids:
            raise ValueError(f"unknown default_shot_preset_id: {self.default_shot_preset_id}")
        return self


class StoryboardSubConfig(BaseModel):
    """Storyboard planning configuration."""

    min_scene_count: int = Field(
        default=DEFAULT_STORYBOARD_GENERATION_LIMITS.min_scene_count,
        ge=1,
        description="Minimum scene count for smart storyboard generation",
    )
    max_scene_count: int = Field(
        default=DEFAULT_STORYBOARD_GENERATION_LIMITS.max_scene_count,
        ge=1,
        description="Maximum scene count for smart storyboard generation",
    )
    deterministic_max_scene_count_limit: int = Field(
        default=DEFAULT_STORYBOARD_GENERATION_LIMITS.deterministic_max_scene_count_limit,
        ge=1,
        le=DETERMINISTIC_STORYBOARD_MAX_SCENE_COUNT_MAX,
        description="Maximum scene count for punctuation and sentence storyboard modes",
    )
    world_preset_library: StoryboardWorldPresetLibraryConfig = Field(
        default_factory=lambda: StoryboardWorldPresetLibraryConfig.model_validate(
            build_builtin_world_preset_library_dict()
        ),
        description="Storyboard world preset library",
    )
    shot_preset_library: StoryboardShotPresetLibraryConfig = Field(
        default_factory=lambda: StoryboardShotPresetLibraryConfig.model_validate(
            build_builtin_shot_preset_library_dict()
        ),
        description="Storyboard shot preset library",
    )

    @model_validator(mode="after")
    def validate_scene_count_limits(self):
        if self.min_scene_count > self.max_scene_count:
            raise ValueError("min_scene_count must not exceed max_scene_count")
        return self


def _validate_storyboard_cross_references(world_library: StoryboardWorldPresetLibraryConfig, shot_library: StoryboardShotPresetLibraryConfig) -> None:
    shot_ids = {item.preset_id for item in shot_library.items}
    for world_preset in world_library.items:
        missing_shot_ids = [shot_id for shot_id in world_preset.default_shot_preset_ids if shot_id not in shot_ids]
        if missing_shot_ids:
            missing_list = ", ".join(missing_shot_ids)
            raise ValueError(
                f"world preset {world_preset.preset_id} references missing shot preset ids: {missing_list}"
            )


DEFAULT_COMFYUI_URL = "http://127.0.0.1:8188"
_BACKEND_PROFILE_NAME_PATTERN = re.compile(r"^[a-z0-9_-]+$")


class ComfyUIBackendProfile(BaseModel):
    """Single ComfyUI backend profile."""

    url: Optional[str] = Field(default=None, description="ComfyUI backend server URL")
    python_exe: Optional[str] = Field(default=None, description="Python executable for managed ComfyUI")
    comfyui_root: Optional[str] = Field(default=None, description="ComfyUI application root directory")
    frontend_root: Optional[str] = Field(default=None, description="ComfyUI frontend root directory")
    extra_models_config: Optional[str] = Field(default=None, description="Extra model paths configuration file")
    managed: bool = Field(
        default=True,
        description=(
            "Whether Pixelle may start a missing local backend. A healthy process "
            "that Pixelle did not start remains externally owned and is never stopped."
        ),
    )
    restart_after_batch: bool = Field(
        default=False,
        description=(
            "Restart this backend after every workflow completion and at pipeline "
            "stage boundaries when the running process is owned by Pixelle. External "
            "backends are preserved. Set to False to keep models loaded in GPU for fast "
            "follow-up requests — the default for single-backend-per-workflow-type "
            "setups where the GPU has enough VRAM for all model sets."
        ),
    )
    data_root: Optional[str] = Field(default=None, description="ComfyUI data root for this profile")
    shared_base_path: Optional[str] = Field(
        default=None,
        description="Shared ComfyUI base directory containing models and custom nodes",
    )
    runtime_dir: Optional[str] = Field(default=None, description="Runtime directory for this profile")
    logs_dir: Optional[str] = Field(default=None, description="Log directory for this profile")
    database_url: Optional[str] = Field(default=None, description="ComfyUI database URL for this profile")


class ComfyUIWorkflowRouting(BaseModel):
    """Workflow type to ComfyUI backend profile routing."""

    image: str = Field(default="default", description="Backend profile for image workflows")
    tts: str = Field(default="default", description="Backend profile for TTS workflows")
    default: str = Field(default="default", description="Fallback backend profile")


def _validate_backend_profile_name(profile_name: str) -> None:
    if not _BACKEND_PROFILE_NAME_PATTERN.fullmatch(profile_name):
        raise ValueError(
            "backend profile name must contain only lowercase letters, "
            "numbers, underscores, and hyphens"
        )


def _default_backend_profile_payload(profile_name: str, fallback_url: str) -> dict[str, Any]:
    data_root = f"E:/ComfyUIData/pixelle-{profile_name}"
    return {
        "url": fallback_url,
        "managed": True,
        "restart_after_batch": False,
        "data_root": data_root,
        "runtime_dir": f"_runtime/comfyui/{profile_name}",
        "logs_dir": f"logs/comfyui/{profile_name}",
        "database_url": f"sqlite:///{data_root}/user/comfyui.db",
    }


def _normalize_backend_profile(
    profile_name: str,
    profile: ComfyUIBackendProfile,
    fallback_url: str,
) -> ComfyUIBackendProfile:
    payload = profile.model_dump()
    defaults = _default_backend_profile_payload(profile_name, fallback_url)
    for field_name, default_value in defaults.items():
        if field_name == "database_url":
            continue
        current_value = payload.get(field_name)
        if current_value is None or (isinstance(current_value, str) and not current_value):
            payload[field_name] = default_value
    payload["data_root"] = payload["data_root"].replace("\\", "/").rstrip("/")
    if not payload.get("shared_base_path"):
        payload["shared_base_path"] = str(Path(payload["data_root"]).parent).replace("\\", "/")
    else:
        payload["shared_base_path"] = payload["shared_base_path"].replace("\\", "/").rstrip("/")
    if not payload.get("database_url"):
        payload["database_url"] = f"sqlite:///{payload['data_root']}/user/comfyui.db"

    return ComfyUIBackendProfile.model_validate(payload)


class ComfyUIConfig(BaseModel):
    """ComfyUI configuration (includes global settings and service-specific configs)"""
    comfyui_url: str = Field(default=DEFAULT_COMFYUI_URL, description="ComfyUI Server URL")
    executor_type: Optional[Literal["http", "websocket"]] = Field(
        default=None,
        description="Optional ComfyUI executor override for selfhost workflows",
    )
    backend_management_mode: Literal["auto", "required", "disabled"] = Field(
        default="auto",
        description=(
            "Controls ComfyUI lifecycle ownership. 'auto' reuses a healthy existing "
            "backend and starts one only when the endpoint is unavailable; 'required' "
            "accepts only a Pixelle-owned manageable process; 'disabled' only connects "
            "to an externally managed backend and never starts or stops ComfyUI."
        ),
    )
    comfyui_api_key: Optional[str] = Field(default=None, description="ComfyUI API Key (optional)")
    runninghub_api_key: Optional[str] = Field(default=None, description="RunningHub API Key (optional)")
    runninghub_concurrent_limit: int = Field(default=1, ge=1, le=10, description="RunningHub concurrent execution limit (1-10)")
    runninghub_instance_type: Optional[str] = Field(default=None, description="RunningHub instance type (optional, set to 'plus' for 48GB VRAM)")
    backends: dict[str, ComfyUIBackendProfile] = Field(
        default_factory=dict,
        description="Named ComfyUI backend profiles",
    )
    workflow_routing: ComfyUIWorkflowRouting = Field(
        default_factory=ComfyUIWorkflowRouting,
        description="Workflow type to backend profile routing",
    )
    tts: TTSSubConfig = Field(default_factory=TTSSubConfig, description="TTS-specific configuration")
    image: ImageSubConfig = Field(default_factory=ImageSubConfig, description="Image-specific configuration")
    video: VideoSubConfig = Field(default_factory=VideoSubConfig, description="Video-specific configuration")

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_comfyui_cleanup_fields(cls, data: Any):
        if not isinstance(data, dict):
            return data

        normalized = dict(data)
        if normalized.get("backends") is None:
            normalized["backends"] = {}
        elif isinstance(normalized.get("backends"), dict):
            normalized["backends"] = {
                profile_name: ({} if profile_data is None else profile_data)
                for profile_name, profile_data in normalized["backends"].items()
            }
        if normalized.get("workflow_routing") is None:
            normalized["workflow_routing"] = {}

        legacy_fields = []
        for field_name in (
            "post_generation_cleanup_mode",
            "post_generation_cleanup_intensity",
            "pre_generation_cleanup_mode",
            "pre_generation_cleanup_timeout_seconds",
        ):
            if field_name in normalized:
                legacy_fields.append(field_name)
                normalized.pop(field_name, None)

        if legacy_fields:
            logger.warning(
                "Ignoring legacy ComfyUI config field(s): {}. "
                "Memory release is now handled by managed backend restart "
                "controlled via backends.<role>.restart_after_batch.",
                ", ".join(legacy_fields),
            )

        if "gguf_cleanup_strategy" in normalized:
            normalized.pop("gguf_cleanup_strategy", None)
            logger.warning(
                "Ignoring retired ComfyUI config field: gguf_cleanup_strategy. "
                "GGUF memory release is handled by managed backend restart."
            )

        normalized.pop("model_cleanup_mode", None)

        return normalized

    @model_validator(mode="after")
    def normalize_backend_profiles_and_routing(self):
        fallback_url = self.comfyui_url or DEFAULT_COMFYUI_URL
        normalized_backends: dict[str, ComfyUIBackendProfile] = {}

        for profile_name, profile in self.backends.items():
            _validate_backend_profile_name(profile_name)
            normalized_backends[profile_name] = _normalize_backend_profile(
                profile_name,
                profile,
                fallback_url,
            )

        if "default" not in normalized_backends:
            normalized_backends["default"] = _normalize_backend_profile(
                "default",
                ComfyUIBackendProfile(),
                fallback_url,
            )

        self.backends = normalized_backends

        for field_name in ("image", "tts", "default"):
            routed_profile = getattr(self.workflow_routing, field_name)
            if routed_profile not in self.backends:
                raise ValueError(
                    f"workflow_routing.{field_name} must reference an existing backend profile"
                )

        return self


class TemplateConfig(BaseModel):
    """Template configuration"""
    default_template: str = Field(
        default=DEFAULT_IMAGE_TEMPLATE,
        description="Default frame template path"
    )


class RenderTimingConfig(BaseModel):
    """Render timing configuration."""

    tts_batching_mode: str = Field(default="paragraph", description="TTS batching mode")
    tts_audio_strategy: TTSAudioStrategy = Field(
        default=DEFAULT_TTS_AUDIO_STRATEGY,
        description="TTS audio organization strategy",
    )
    tts_split_mode: TtsSplitMode = Field(
        default=DEFAULT_TTS_SPLIT_MODE,
        description="TTS text segmentation strategy",
    )
    tts_batch_max_sentences: int = Field(default=8, ge=1, description="Maximum sentences per TTS batch")
    tts_batch_max_chars: int = Field(default=220, ge=1, description="Maximum characters per TTS batch")
    tts_sentence_joiner_mode: Literal["direct", "space"] = Field(
        default="direct",
        description="How TTS sentence units are joined inside an audio block",
    )
    caption_punctuation_mode: Literal["strip_all", "strip_terminal", "preserve"] = Field(
        default="strip_all",
        description="How punctuation is formatted for displayed captions",
    )
    preserve_natural_punctuation: bool = Field(
        default=True,
        description="Ask narration generation to preserve natural punctuation",
    )
    max_chars_per_tts_segment: int = Field(default=90, ge=1, description="Maximum characters per external TTS segment")
    tts_split_overflow_policy: str = Field(default="hard_limit", description="TTS split overflow policy")
    tts_boundary_search_radius: int = Field(default=20, ge=0, description="TTS external splitter boundary search radius")
    tts_soft_overflow_chars: int = Field(default=0, ge=0, description="Allowed soft overflow characters for TTS splitting")
    tts_audio_boundary_fade_ms: int = Field(default=8, ge=0, description="Audio fade duration at TTS boundaries")
    subtitle_alignment_engine: str = Field(
        default="qwen_forced_aligner",
        description="Subtitle alignment engine",
    )
    silence_trim_tool: Optional[str] = Field(default=None, description="Optional silence trim tool")
    silence_trim_margin_ms: int = Field(default=120, ge=0, description="Silence trim margin in milliseconds")


class ElementAnimationConfig(BaseModel):
    """Element animation configuration."""

    enabled: bool = Field(default=False, description="Enable element animation")
    backend: Literal["hyperframes_canvas", "python_ffmpeg"] = Field(
        default="hyperframes_canvas",
        description="Element animation backend",
    )
    subject_count: int = Field(default=3, ge=1, description="Number of subjects to animate")
    candidate_limit: int = Field(default=3, ge=1, description="Maximum segmentation candidates")
    prompt: Optional[str] = Field(default=None, description="Optional element animation prompt")
    intensity: Literal["low", "medium", "high"] = Field(
        default="medium",
        description="Element animation intensity",
    )
    workflow: str = Field(
        default="image_sam31_segment.json",
        description="Element animation segmentation workflow",
    )

    @model_validator(mode="after")
    def validate_candidate_limit(self):
        if self.candidate_limit < self.subject_count:
            raise ValueError("candidate_limit must be >= subject_count")
        return self


class RenderConfig(BaseModel):
    """Render configuration."""

    backend: RenderBackend = Field(default=DEFAULT_RENDER_BACKEND, description="Render backend")
    timing: RenderTimingConfig = Field(default_factory=RenderTimingConfig)
    element_animation: ElementAnimationConfig = Field(default_factory=ElementAnimationConfig)


class LoggingConfig(BaseModel):
    """Application-owned file logging configuration."""

    enabled: bool = Field(default=True)
    level: str = Field(default="INFO")
    log_dir: str = Field(default="_runtime/logs")
    rotation_mb: int = Field(default=50, ge=1)
    retention_days: int = Field(default=14, ge=1)
    task_logs_enabled: bool = Field(default=True)
    ai_creation_logs_enabled: bool = Field(default=True)
    preview_chars: int = Field(default=120, ge=20)


class RuntimeConfig(BaseModel):
    """Runtime lifecycle controls."""

    release_resources_after_video_generation: bool = Field(
        default=True,
        description=(
            "Release per-generation Pixelle resources when the generation worker "
            "becomes idle. This is applied in PixelleVideoCore so Web, API, batch, "
            "and direct calls share the same lifecycle behavior."
        ),
    )
    close_comfykit_after_generation: bool = Field(
        default=True,
        description=(
            "Close idle ComfyKit executors after generation. The next workflow call "
            "creates a fresh executor lazily."
        ),
    )
    close_html_browser_after_generation: bool = Field(
        default=True,
        description=(
            "Close the shared Playwright browser used for HTML frame rendering after "
            "generation when the core is idle."
        ),
    )
    close_alignment_service_after_generation: bool = Field(
        default=True,
        description=(
            "Release cached subtitle forced-alignment models after generation. "
            "This prevents the main Pixelle process from retaining large ASR "
            "models between back-to-back video jobs."
        ),
    )
    stop_managed_comfyui_backends_after_generation: bool = Field(
        default=True,
        description=(
            "Stop Pixelle-managed local ComfyUI backends once the generation core "
            "is idle. The next self-hosted workflow starts the required backend "
            "lazily, avoiding cumulative CPU/GPU memory pressure across jobs."
        ),
    )
    collect_garbage_after_generation: bool = Field(
        default=True,
        description=(
            "Run Python garbage collection after closing generation resources so "
            "large temporary object graphs are released promptly."
        ),
    )
    log_process_memory_after_generation: bool = Field(
        default=True,
        description=(
            "Log the current process memory before and after generation resource "
            "release when psutil is available."
        ),
    )


class ReferenceImageConfig(BaseModel):
    """Reference-image feature configuration."""

    enabled: bool = Field(default=False)
    web_ui_enabled: bool = Field(default=True)
    analysis_mode: Literal["off", "auto", "required"] = Field(default="off")
    workflow_injection_mode: Literal["off", "auto", "required"] = Field(default="off")
    profile_merge_mode: Literal["supplement", "override", "strict"] = Field(default="supplement")
    allowed_extensions: list[str] = Field(
        default_factory=lambda: [".jpg", ".jpeg", ".png", ".webp"]
    )
    max_upload_size_mb: int = Field(default=20, ge=1)
    max_vision_edge_px: int = Field(default=1024, ge=1)
    max_workflow_edge_px: int = Field(default=2048, ge=1)
    strip_exif: bool = Field(default=True)
    convert_to_png_for_workflow: bool = Field(default=False)
    allow_ambiguous_image_param: bool = Field(default=False)
    workflow_param_overrides: dict[str, Any] = Field(default_factory=dict)

    @field_validator("allowed_extensions", mode="before")
    @classmethod
    def normalize_allowed_extensions(cls, value: Any):
        if value in (None, "", []):
            return [".jpg", ".jpeg", ".png", ".webp"]
        if not isinstance(value, (list, tuple, set)):
            raise ValueError("reference_image.allowed_extensions must be a list")
        normalized: list[str] = []
        for item in value:
            extension = str(item or "").strip().lower()
            if not extension:
                continue
            if not extension.startswith("."):
                extension = f".{extension}"
            if extension not in normalized:
                normalized.append(extension)
        if not normalized:
            raise ValueError("reference_image.allowed_extensions must not be empty")
        return normalized

    @field_validator("workflow_param_overrides", mode="before")
    @classmethod
    def validate_workflow_param_overrides(cls, value: Any):
        if value in (None, ""):
            return {}
        if not isinstance(value, dict):
            raise ValueError("reference_image.workflow_param_overrides must be an object")
        normalized: dict[str, Any] = {}
        for key, override in value.items():
            workflow_key = str(key or "").strip()
            if not workflow_key:
                raise ValueError("reference_image.workflow_param_overrides keys must not be empty")
            normalized[workflow_key] = cls._normalize_workflow_param_override(override)
        return normalized

    @classmethod
    def _normalize_workflow_param_override(cls, value: Any) -> str | list[str] | dict[str, Any]:
        if isinstance(value, str):
            param_name = value.strip()
            if not param_name:
                raise ValueError("reference_image.workflow_param_overrides values must not be empty")
            return param_name
        if isinstance(value, Mapping):
            override = dict(value)
            for key in ("reference_image", "params", "param_names"):
                if key in override:
                    override[key] = cls._normalize_workflow_param_override_names(override[key])
                    return override
            raise ValueError(
                "reference_image.workflow_param_overrides object values must include reference_image, params, or param_names"
            )
        if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
            return cls._normalize_workflow_param_override_names(value)
        raise ValueError(
            "reference_image.workflow_param_overrides values must be a string, list, or object"
        )

    @classmethod
    def _normalize_workflow_param_override_names(cls, value: Any) -> list[str]:
        values = [value] if isinstance(value, str) else value
        if not isinstance(values, Sequence) or isinstance(values, (bytes, bytearray)):
            raise ValueError("reference_image.workflow_param_overrides param names must be a string or list")
        normalized: list[str] = []
        for item in values:
            param_name = str(item or "").strip()
            if param_name and param_name not in normalized:
                normalized.append(param_name)
        if not normalized:
            raise ValueError("reference_image.workflow_param_overrides param names must not be empty")
        return normalized


class VisionLLMConfig(ProviderTransportConfig):
    """Dedicated multimodal LLM configuration for reference-image analysis."""

    enabled: bool = Field(default=False)
    api_key: str = Field(default="")
    base_url: str = Field(default="")
    model: str = Field(default="")
    temperature: float = Field(default=0.2, ge=0)
    max_tokens: int = Field(default=1200, ge=1)
    max_image_size_mb: int = Field(default=5, ge=1)
    max_vision_edge_px: int = Field(default=1024, ge=1)
    unavailable_policy: Literal["skip", "fail"] = Field(default="skip")
    force_supports_vision: Optional[bool] = Field(default=None)


class OpenAIImageProviderConfig(ProviderTransportConfig):
    """Configuration for the governed OpenAI-compatible image adapter."""

    enabled: bool = Field(default=False)
    api_key: str = Field(default="")
    base_url: str = Field(default="https://api.openai.com/v1")
    max_output_size_mb: int = Field(default=25, ge=1, le=100)
    max_output_pixels: int = Field(
        default=20_000_000,
        ge=1_048_576,
        le=100_000_000,
    )
    max_output_edge_px: int = Field(default=8192, ge=64, le=16384)


class DirectMediaConfig(BaseModel):
    """Direct media providers that run behind the MediaService governance boundary."""

    enabled: bool = Field(default=False)
    openai_image: OpenAIImageProviderConfig = Field(
        default_factory=OpenAIImageProviderConfig
    )


class PixelleVideoConfig(BaseModel):
    """Pixelle-Video main configuration"""
    config_version: int = Field(default=2, ge=1, description="Runtime configuration schema version")
    project_name: str = Field(default="Pixelle-Video", description="Project name")
    llm: LLMConfig = Field(default_factory=LLMConfig)
    comfyui: ComfyUIConfig = Field(default_factory=ComfyUIConfig)
    template: TemplateConfig = Field(default_factory=TemplateConfig)
    render: RenderConfig = Field(default_factory=RenderConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    storyboard: StoryboardSubConfig = Field(default_factory=StoryboardSubConfig, description="Storyboard planning configuration")
    reference_image: ReferenceImageConfig = Field(default_factory=ReferenceImageConfig)
    vision_llm: VisionLLMConfig = Field(default_factory=VisionLLMConfig)
    direct_media: DirectMediaConfig = Field(default_factory=DirectMediaConfig)

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_omnivoice_defaults(cls, data: Any):
        if not isinstance(data, dict):
            return data

        config_version = int(data.get("config_version") or 1)
        migrated = dict(data)

        if config_version >= 2:
            migrated["config_version"] = config_version
            return migrated

        comfyui_config = migrated.get("comfyui")
        if isinstance(comfyui_config, dict):
            migrated_comfyui = dict(comfyui_config)
            tts_config = migrated_comfyui.get("tts")
            if isinstance(tts_config, dict):
                migrated_tts = dict(tts_config)
                comfyui_tts = migrated_tts.get("comfyui")
                if isinstance(comfyui_tts, dict):
                    migrated_nested_tts = dict(comfyui_tts)
                    default_workflow = migrated_nested_tts.get("default_workflow")
                    upgraded_workflow = upgrade_legacy_default_tts_workflow(default_workflow)
                    if upgraded_workflow != default_workflow:
                        migrated_nested_tts["default_workflow"] = upgraded_workflow
                    migrated_tts["comfyui"] = migrated_nested_tts
                migrated_comfyui["tts"] = migrated_tts
            migrated["comfyui"] = migrated_comfyui

        render_config = migrated.get("render")
        if isinstance(render_config, dict):
            migrated_render = dict(render_config)
            timing_config = migrated_render.get("timing")
            if isinstance(timing_config, dict):
                migrated_timing = dict(timing_config)
                if (
                    migrated_timing.get("tts_split_mode") == "external_only"
                    and migrated_timing.get("tts_audio_strategy") in (None, "master_track")
                    and migrated_timing.get("max_chars_per_tts_segment", 90) == 90
                    and migrated_timing.get("tts_boundary_search_radius", 20) == 20
                    and migrated_timing.get("tts_soft_overflow_chars", 0) == 0
                ):
                    migrated_timing["tts_split_mode"] = DEFAULT_TTS_SPLIT_MODE
                migrated_render["timing"] = migrated_timing
            migrated["render"] = migrated_render

        migrated["config_version"] = 2
        return migrated

    @model_validator(mode="after")
    def validate_storyboard_referential_integrity(self):
        _validate_storyboard_cross_references(
            self.storyboard.world_preset_library,
            self.storyboard.shot_preset_library,
        )
        return self
    
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
