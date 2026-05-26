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
Media Generation Service - ComfyUI Workflow-based implementation

Supports both image and video generation workflows.
Automatically detects output type based on ExecuteResult.
"""

import os
from collections.abc import Mapping
from typing import Any, Optional

from loguru import logger

from pixelle_video.models.media import MediaResult
from pixelle_video.runninghub_workflow_contracts import (
    RUNNINGHUB_SOURCE,
    runninghub_registry_root,
)
from pixelle_video.services.comfy_base_service import ComfyBaseService
from pixelle_video.services.comfyui_errors import looks_like_memory_exhaustion
from pixelle_video.services.prompt_trace_artifacts import (
    build_workflow_params_trace,
    require_media_prompt_trace_context,
    summarize_media_workflow_result,
    validate_media_prompt_trace_artifact,
    write_media_result_artifact,
)

_MEDIA_PROMPT_ALIAS_PARAM_KEYS = frozenset(
    {
        "prompt",
        "positive_prompt",
        "image_prompt",
        "video_prompt",
        "text_prompt",
    }
)
_MEDIA_NEGATIVE_PROMPT_ALIAS_PARAM_KEYS = frozenset(
    {
        "negative",
        "negative_prompt",
        "negative_image_prompt",
        "negative_video_prompt",
    }
)


def _looks_like_memory_exhaustion(error_message: str) -> bool:
    return looks_like_memory_exhaustion(error_message)


def _looks_like_selfhost_connection_failure(error_message: str) -> bool:
    lowered = (error_message or "").lower()
    return any(
        marker in lowered
        for marker in (
            "cannot connect to host",
            "connection refused",
            "failed to establish a new connection",
            "actively refused",
        )
    )


def _reject_media_prompt_alias_params(params: Mapping[str, Any]) -> None:
    for key, value in params.items():
        name = str(key or "").strip()
        normalized_name = name.lower()
        if not name or value in (None, "", [], {}):
            continue
        if (
            normalized_name in _MEDIA_PROMPT_ALIAS_PARAM_KEYS
            or normalized_name in _MEDIA_NEGATIVE_PROMPT_ALIAS_PARAM_KEYS
        ):
            raise ValueError(
                "media workflow prompt alias params must use explicit prompt or negative_prompt arguments"
            )


def _resolve_comfyui_url_for_error_message(configured_url: str | None) -> str:
    resolved = (
        configured_url
        or os.getenv("COMFYUI_BASE_URL")
        or "http://127.0.0.1:8188"
    )
    return str(resolved).strip() or "http://127.0.0.1:8188"


def _build_media_generation_error_message(
    *,
    error_message: str,
    workflow_key: str,
    media_type: str,
    comfyui_url: str | None = None,
) -> str:
    cleaned = (error_message or "Unknown error").strip()
    if workflow_key.startswith("selfhost/") and _looks_like_selfhost_connection_failure(cleaned):
        resolved_comfyui_url = _resolve_comfyui_url_for_error_message(comfyui_url)
        guidance = [
            f"Media generation failed: {cleaned}",
            f"Self-hosted workflow '{workflow_key}' requires a reachable ComfyUI server.",
            f"Current ComfyUI URL: {resolved_comfyui_url}.",
            "Start ComfyUI or update Settings -> ComfyUI Server URL (or config.yaml) to a running ComfyUI instance.",
        ]
        if resolved_comfyui_url != "http://127.0.0.1:8188":
            guidance.append("If you're using the default local setup, try http://127.0.0.1:8188.")
        return " ".join(guidance)

    if not _looks_like_memory_exhaustion(cleaned):
        return f"Media generation failed: {cleaned}"

    guidance = [
        f"{media_type.title()} generation ran out of memory in workflow '{workflow_key}'.",
        "Try restarting the self-hosted ComfyUI backend, reducing the image size, or using a lighter workflow.",
    ]
    if media_type == "image" and workflow_key != "selfhost/image_z_image_turbo_gguf.json":
        guidance.append(
            "Recommended lighter default: 'selfhost/image_z_image_turbo_gguf.json'."
        )
    return f"{' '.join(guidance)} Backend error: {cleaned}"


def _is_already_formatted_media_error(message: str) -> bool:
    stripped = (message or "").strip()
    return stripped.startswith("Media generation failed:") or "generation ran out of memory in workflow" in stripped


def _media_workflow_execution_input(workflow_info: Mapping[str, Any]) -> str:
    if workflow_info.get("source") == "runninghub" and workflow_info.get("workflow_id"):
        return str(workflow_info["workflow_id"])
    return str(workflow_info["path"])


class MediaService(ComfyBaseService):
    """
    Media generation service - Workflow-based
    
    Uses ComfyKit to execute image/video generation workflows.
    Supports both image_ and video_ workflow prefixes.
    
    Usage:
        # Media calls require a saved final prompt trace context. Prefer the
        # standard pipeline, image API, workbench regeneration, or preview
        # helpers so the exact prompt artifact is written before ComfyUI runs.
        #
        # List available workflows
        workflows = pixelle_video.media.list_workflows()
    """
    
    WORKFLOW_PREFIX = ""  # Will be overridden by _scan_workflows
    DEFAULT_WORKFLOW = None  # No hardcoded default, must be configured
    WORKFLOWS_DIR = "workflows"
    
    def __init__(self, config: dict, core=None):
        """
        Initialize media service
        
        Args:
            config: Full application config dict
            core: PixelleVideoCore instance (for accessing shared ComfyKit)
        """
        super().__init__(config, service_name="image", core=core)  # Keep "image" for config compatibility
    
    def _scan_workflows(self):
        """
        Scan workflows for both image_ and video_ prefixes
        
        Override parent method to support multiple prefixes
        """
        if self._workflows_cache is not None:
            return self._workflows_cache

        from pathlib import Path

        from pixelle_video.utils.os_util import (
            get_resource_path,
            list_resource_dirs,
            list_resource_files,
        )
        
        workflows = []
        
        # Get all workflow source directories
        source_dirs = list_resource_dirs("workflows")
        
        if not source_dirs:
            logger.warning("No workflow source directories found")
            return workflows
        
        # Scan each source directory for workflow files
        for source_name in source_dirs:
            if source_name == RUNNINGHUB_SOURCE:
                registry_root = runninghub_registry_root()
                workflow_paths = (
                    sorted(
                        path
                        for path in registry_root.iterdir()
                        if path.is_file() and path.suffix.lower() == ".json"
                    )
                    if registry_root.is_dir()
                    else []
                )
            else:
                workflow_paths = [
                    Path(get_resource_path("workflows", source_name, filename))
                    for filename in list_resource_files("workflows", source_name)
                ]

            for file_path in workflow_paths:
                filename = file_path.name
                if not filename.endswith('.json'):
                    continue
                try:
                    workflow_info = self._parse_workflow_file(file_path, source_name)
                    if source_name == RUNNINGHUB_SOURCE:
                        if workflow_info.get("media_type") not in {"image", "video"}:
                            continue
                    else:
                        content_contract = workflow_info.get("workflow_content_contract")
                        if isinstance(content_contract, dict) and (
                            content_contract.get("contains_tts_nodes")
                            or content_contract.get("contains_analysis_nodes")
                        ):
                            logger.warning(
                                "Skipping non-media selfhost workflow with media-looking "
                                f"name: {workflow_info['key']}"
                            )
                            continue
                        if not (
                            filename.startswith("image_") or filename.startswith("video_")
                        ):
                            continue
                    workflows.append(workflow_info)
                    logger.debug(f"Found workflow: {workflow_info['key']}")
                except Exception as e:
                    logger.error(f"Failed to parse workflow {source_name}/{filename}: {e}")
        
        # Sort by key (source/name)
        self._workflows_cache = sorted(workflows, key=lambda w: w["key"])
        return self._workflows_cache

    def resolve_workflow_key(
        self,
        *,
        workflow: Optional[str] = None,
        media_type: str = "image",
    ) -> str:
        workflow_info = self._resolve_workflow(
            workflow=workflow,
            workflow_domain=media_type,
        )
        return str(workflow_info["key"])

    def resolve_workflow_trace_context(
        self,
        *,
        workflow: Optional[str] = None,
        media_type: str = "image",
    ) -> dict[str, Any]:
        requested_workflow = workflow.strip() if isinstance(workflow, str) else workflow
        workflow_info = self._resolve_workflow(
            workflow=requested_workflow,
            workflow_domain=media_type,
        )
        workflow_key = str(workflow_info["key"])
        workflow_input = _media_workflow_execution_input(workflow_info)
        workflow_file_trace = self._build_resolved_workflow_file_trace(
            workflow_info,
            workflow_input,
        )
        return {
            "requested_workflow": requested_workflow,
            "workflow": workflow_key,
            "workflow_key": workflow_key,
            "workflow_source": str(workflow_info["source"]),
            "workflow_input": workflow_input,
            **workflow_file_trace,
        }
    
    async def __call__(
        self,
        prompt: str,
        workflow: Optional[str] = None,
        # Media type specification (required for proper handling)
        media_type: str = "image",  # "image" or "video"
        # ComfyUI connection (optional overrides)
        comfyui_url: Optional[str] = None,
        runninghub_api_key: Optional[str] = None,
        # Common workflow parameters
        width: Optional[int] = None,
        height: Optional[int] = None,
        duration: Optional[float] = None,  # Video duration in seconds (for video workflows)
        negative_prompt: Optional[str] = None,
        steps: Optional[int] = None,
        seed: Optional[int] = None,
        cfg: Optional[float] = None,
        sampler: Optional[str] = None,
        media_prompt_trace_context: Mapping[str, Any] | None = None,
        **params
    ) -> MediaResult:
        """
        Generate media (image or video) using workflow
        
        Media type must be specified explicitly via media_type parameter.
        Returns a MediaResult object containing media type and URL.
        
        Args:
            prompt: Media generation prompt
            workflow: Workflow filename (default: from config or "selfhost/image_z_image_turbo_gguf.json")
            media_type: Type of media to generate - "image" or "video" (default: "image")
            comfyui_url: ComfyUI URL (optional, overrides config)
            runninghub_api_key: RunningHub API key (optional, overrides config)
            width: Media width
            height: Media height
            duration: Target video duration in seconds (only for video workflows, typically from TTS audio duration)
            negative_prompt: Negative prompt
            steps: Sampling steps
            seed: Random seed
            cfg: CFG scale
            sampler: Sampler name
            **params: Additional workflow parameters
        
        Returns:
            MediaResult object with media_type ("image" or "video") and url
        
        Examples:
            MediaService is the low-level boundary to ComfyUI. Callers must
            write the final prompt artifact first and pass
            media_prompt_trace_context so prompt provenance cannot be bypassed.
        """
        trace_context = require_media_prompt_trace_context(
            media_prompt_trace_context,
            prompt=prompt,
            media_type=media_type,
            width=width,
            height=height,
            negative_prompt=negative_prompt,
        )
        # 1. Resolve workflow (returns structured info)
        workflow_info = self._resolve_workflow(
            workflow=workflow,
            workflow_domain=media_type,
        )
        workflow_input = _media_workflow_execution_input(workflow_info)
        workflow_file_trace = self._build_resolved_workflow_file_trace(
            workflow_info,
            workflow_input,
        )
        _reject_media_prompt_alias_params(params)
        workflow_params = {"prompt": prompt}
        if negative_prompt is not None:
            workflow_params["negative_prompt"] = negative_prompt
        if steps is not None:
            workflow_params["steps"] = steps
        if seed is not None:
            workflow_params["seed"] = seed
        if cfg is not None:
            workflow_params["cfg"] = cfg
        if sampler is not None:
            workflow_params["sampler"] = sampler
        workflow_params.update(params)
        if width is not None:
            workflow_params["width"] = width
        if height is not None:
            workflow_params["height"] = height
        if duration is not None:
            workflow_params["duration"] = duration
            if media_type == "video":
                logger.info(f"Target video duration: {duration:.2f}s (from TTS audio)")
        validate_media_prompt_trace_artifact(
            trace_context,
            prompt=prompt,
            resolved_workflow=str(workflow_info["key"]),
            resolved_workflow_input=workflow_input,
            media_type=media_type,
            width=width,
            height=height,
            negative_prompt=negative_prompt,
            workflow_param_trace=build_workflow_params_trace(
                workflow_params,
                prompt=prompt,
            ),
            workflow_file_trace=workflow_file_trace,
        )
        backend_role = "default"
        registry = self._get_backend_registry()
        if workflow_info["source"] == "selfhost" and registry is not None:
            backend_role = registry.resolve_role_for_media(
                workflow_info["key"],
                media_type,
            )
        logger.debug(f"Workflow parameters: {workflow_params}")
        result_artifact_written = False
        
        # 4. Execute workflow using shared ComfyKit instance from core
        try:
            # Determine what to pass to ComfyKit based on source
            if workflow_info["source"] == "runninghub" and "workflow_id" in workflow_info:
                # RunningHub: pass workflow_id (ComfyKit will use runninghub backend)
                logger.info(f"Executing RunningHub workflow: {workflow_input}")
            else:
                # Selfhost: pass file path (ComfyKit will use local ComfyUI)
                logger.info(f"Executing selfhost workflow: {workflow_input}")
            
            result = await self._execute_workflow(
                workflow_input,
                workflow_params,
                workflow_info,
                backend_role=backend_role,
                media_prompt_trace_context=trace_context,
                media_type=media_type,
            )
            result_summary = summarize_media_workflow_result(result)
            
            # 5. Handle result based on specified media_type
            if result.status != "completed":
                error_msg = result.msg or "Unknown error"
                write_media_result_artifact(
                    trace_context,
                    status="failed",
                    result=result_summary,
                )
                result_artifact_written = True
                raise RuntimeError(error_msg)
            
            # Extract media based on specified type
            if media_type == "video":
                # Video workflow - get video from result
                if not result.videos:
                    write_media_result_artifact(
                        trace_context,
                        status="error",
                        result={**result_summary, "error": "No video generated"},
                    )
                    result_artifact_written = True
                    raise RuntimeError("No video generated")
                
                video_url = result.videos[0]
                logger.info(f"✅ Generated video: {video_url}")
                
                # Try to extract duration from result (if available)
                duration = None
                if hasattr(result, 'duration') and result.duration:
                    duration = result.duration
                
                media_result = MediaResult(
                    media_type="video",
                    url=video_url,
                    duration=duration
                )
                write_media_result_artifact(
                    trace_context,
                    status="completed",
                    result={
                        **result_summary,
                        "media_result": {
                            "media_type": media_result.media_type,
                            "url": media_result.url,
                            "duration": media_result.duration,
                        },
                    },
                )
                result_artifact_written = True
                return media_result
            else:  # image
                # Image workflow - get image from result
                if not result.images:
                    write_media_result_artifact(
                        trace_context,
                        status="error",
                        result={**result_summary, "error": "No image generated"},
                    )
                    result_artifact_written = True
                    raise RuntimeError("No image generated")
                
                image_url = result.images[0]
                logger.info(f"✅ Generated image: {image_url}")
                
                media_result = MediaResult(
                    media_type="image",
                    url=image_url
                )
                write_media_result_artifact(
                    trace_context,
                    status="completed",
                    result={
                        **result_summary,
                        "media_result": {
                            "media_type": media_result.media_type,
                            "url": media_result.url,
                        },
                    },
                )
                result_artifact_written = True
                return media_result
        
        except Exception as e:
            message = str(e)
            formatted_error = (
                message
                if _is_already_formatted_media_error(message)
                else _build_media_generation_error_message(
                    error_message=message,
                    workflow_key=workflow_info["key"],
                    media_type=media_type,
                    comfyui_url=comfyui_url or self.global_config.get("comfyui_url"),
                )
            )
            logger.error(f"Media generation error: {formatted_error}")
            if not result_artifact_written:
                write_media_result_artifact(
                    trace_context,
                    status="error",
                    result={
                        "error_type": type(e).__name__,
                        "error": formatted_error,
                    },
                )
            raise RuntimeError(formatted_error) from e
