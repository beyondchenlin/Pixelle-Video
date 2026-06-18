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

import json
import os
from collections.abc import Mapping
from pathlib import Path
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
    write_single_media_prompt_trace_context,
)
from pixelle_video.services.reference_image_workflow_binding import (
    REFERENCE_IMAGE_WORKFLOW_BINDING_PARAM,
    apply_reference_image_workflow_binding_trace,
    build_reference_image_workflow_binding,
    resolve_reference_image_workflow_injection_mode,
    workflow_param_overrides_from_config,
)
from pixelle_video.utils.os_util import (
    get_resource_path,
    list_resource_dirs,
    list_resource_files,
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
_REFERENCE_IMAGE_MODE_PARAM_KEYS = (
    "reference_image_workflow_injection_mode",
    "workflow_injection_mode",
    "ref_image_workflow_injection_mode",
)
SELFHOST_MEDIA_WORKFLOW_PREFIXES = ("image_", "video_")


def _is_selfhost_media_workflow_filename(filename: str) -> bool:
    return filename.endswith(".json") and filename.startswith(SELFHOST_MEDIA_WORKFLOW_PREFIXES)


def _workflow_content_contract_is_non_media(workflow_info: dict) -> bool:
    content_contract = workflow_info.get("workflow_content_contract")
    return isinstance(content_contract, dict) and (
        bool(content_contract.get("contains_tts_nodes"))
        or bool(content_contract.get("contains_analysis_nodes"))
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
        if name.startswith("_"):
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


def _extract_reference_image_mode_params(params: dict[str, Any]) -> dict[str, Any]:
    extracted: dict[str, Any] = {}
    for key in _REFERENCE_IMAGE_MODE_PARAM_KEYS:
        if key in params:
            extracted[key] = params.pop(key)
    structured = params.get("reference_image")
    if isinstance(structured, Mapping):
        extracted["reference_image"] = params.pop("reference_image")
    return extracted


def _task_root_from_media_prompt_trace_context(context: Mapping[str, Any]) -> Path | None:
    artifact_path = Path(str(context.get("artifact_path") or ""))
    if not artifact_path.name:
        return None
    explicit_task_root = str(context.get("task_root") or "").strip()
    if explicit_task_root:
        task_root = Path(explicit_task_root).resolve()
        try:
            artifact_path.resolve().relative_to(task_root)
        except ValueError as exc:
            raise ValueError(
                "media_prompt_trace_context task_root must contain artifact_path"
            ) from exc
        return task_root
    prompt_trace_root = None
    for parent in artifact_path.parents:
        if parent.name == "prompt_traces":
            prompt_trace_root = parent
    if prompt_trace_root is None:
        return artifact_path.parent.resolve()
    return prompt_trace_root.parent.resolve()


def _safe_task_relative_path(task_root: Path, relative_path: str) -> Path | None:
    try:
        root = task_root.resolve()
        candidate = (root / relative_path).resolve()
        candidate.relative_to(root)
        return candidate
    except (OSError, ValueError):
        return None


def _reference_image_asset_from_task_root(task_root: Path | None) -> tuple[str | None, dict[str, Any]]:
    if task_root is None:
        return None, {}
    asset_path = task_root / "reference_image" / "asset.json"
    if not asset_path.is_file():
        return None, {}
    try:
        payload = json.loads(asset_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, {}
    asset_trace = payload.get("asset") if isinstance(payload, Mapping) else None
    if not isinstance(asset_trace, Mapping):
        return None, {}
    relative_path = asset_trace.get("workflow_asset_relative_path") or asset_trace.get("task_asset_relative_path")
    if not isinstance(relative_path, str) or not relative_path.strip():
        return None, dict(asset_trace)
    safe_path = _safe_task_relative_path(task_root, relative_path.strip())
    if safe_path is None:
        return None, dict(asset_trace)
    return str(safe_path), dict(asset_trace)


def _reference_image_config_from_service(service: "MediaService") -> Mapping[str, Any]:
    def _section_to_mapping(section: Any) -> dict[str, Any] | None:
        if isinstance(section, Mapping):
            return dict(section)
        if hasattr(section, "model_dump"):
            dumped = section.model_dump()
            return dict(dumped) if isinstance(dumped, Mapping) else {}
        return None

    core_config = getattr(getattr(service, "core", None), "config", None)
    if isinstance(core_config, Mapping):
        core_reference_config = _section_to_mapping(core_config.get("reference_image"))
        if core_reference_config is not None:
            return core_reference_config
    else:
        core_reference_config = _section_to_mapping(getattr(core_config, "reference_image", None))
        if core_reference_config is not None:
            return core_reference_config

    if isinstance(service.app_config, Mapping):
        app_reference_config = _section_to_mapping(service.app_config.get("reference_image"))
        if app_reference_config is not None:
            return app_reference_config
    else:
        app_reference_config = _section_to_mapping(getattr(service.app_config, "reference_image", None))
        if app_reference_config is not None:
            return app_reference_config
    return {}


def _reference_binding_trace_output_dir(context: Mapping[str, Any]) -> Path:
    artifact_path = Path(str(context.get("artifact_path") or ""))
    if artifact_path.name:
        return artifact_path.parent / "reference_image_binding"
    return Path(".") / "reference_image_binding"


def _result_with_reference_binding(
    result_summary: Mapping[str, Any],
    binding_trace: Mapping[str, Any] | None,
) -> dict[str, Any]:
    payload = dict(result_summary or {})
    if isinstance(binding_trace, Mapping) and binding_trace:
        payload["reference_image_workflow_binding"] = dict(binding_trace)
    return payload


def _reference_image_analysis_status_from_task_root(task_root: Path | None) -> str:
    if task_root is None:
        return "unknown"
    analysis_path = task_root / "reference_image" / "analysis.json"
    if not analysis_path.is_file():
        return "unknown"
    try:
        payload = json.loads(analysis_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "unknown"
    status = payload.get("status") if isinstance(payload, Mapping) else None
    return str(status or "unknown")


def _reference_image_injection_status(binding_trace: Mapping[str, Any]) -> str:
    status = str(binding_trace.get("status") or "").strip().lower()
    reason = str(binding_trace.get("reason") or "").strip()
    if status == "injected":
        return "workflow_injected"
    if status == "failed":
        return "required_failed"
    if reason == "workflow_injection_mode_off":
        return "off"
    if status == "skipped":
        return "prompt_only"
    return status or "unknown"


def _first_reference_image_param_name(binding_trace: Mapping[str, Any]) -> str | None:
    trace_values = binding_trace.get("workflow_param_trace_values")
    if not isinstance(trace_values, Mapping):
        return None
    for key in trace_values:
        name = str(key or "").strip()
        if name:
            return name
    return None


def _safe_task_relative_text(task_root: Path | None, path: Path) -> str | None:
    if task_root is None:
        return None
    try:
        return path.resolve().relative_to(task_root.resolve()).as_posix()
    except (OSError, ValueError):
        return None


def _write_reference_image_injection_summary(
    context: Mapping[str, Any],
    *,
    workflow_info: Mapping[str, Any],
    binding_trace: Mapping[str, Any],
) -> dict[str, Any]:
    task_root = _task_root_from_media_prompt_trace_context(context)
    output_dir = _reference_binding_trace_output_dir(context)
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "injection_summary.json"
    summary = {
        "version": "reference_image_injection_summary/v1",
        "analysis_status": _reference_image_analysis_status_from_task_root(task_root),
        "workflow_injection_status": _reference_image_injection_status(binding_trace),
        "workflow_key": str(workflow_info.get("key") or binding_trace.get("workflow_key") or ""),
        "workflow_source": str(workflow_info.get("source") or ""),
        "injection_mode": str(binding_trace.get("injection_mode") or ""),
        "param_name": _first_reference_image_param_name(binding_trace),
        "reason": str(binding_trace.get("reason") or ""),
    }
    relative_path = _safe_task_relative_text(task_root, summary_path)
    if relative_path:
        summary["artifact_relative_path"] = relative_path
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return summary


class MediaService(ComfyBaseService):
    """
    Media generation service - Workflow-based
    """

    WORKFLOW_PREFIX = ""  # Will be overridden by _scan_workflows
    DEFAULT_WORKFLOW = None  # No hardcoded default, must be configured
    WORKFLOWS_DIR = "workflows"

    def __init__(self, config: dict, core=None):
        super().__init__(config, service_name="image", core=core)  # Keep "image" for config compatibility
        self.app_config = config

    def _scan_workflows(self):
        if self._workflows_cache is not None:
            return self._workflows_cache

        workflows = []
        source_dirs = list_resource_dirs("workflows")

        if not source_dirs:
            logger.warning("No workflow source directories found")
            return workflows

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
                if source_name != RUNNINGHUB_SOURCE and not _is_selfhost_media_workflow_filename(filename):
                    logger.debug(f"Skipping non-media selfhost workflow: {source_name}/{filename}")
                    continue
                try:
                    workflow_info = self._parse_workflow_file(file_path, source_name)
                    if source_name == RUNNINGHUB_SOURCE:
                        if workflow_info.get("media_type") not in {"image", "video"}:
                            continue
                    else:
                        if _workflow_content_contract_is_non_media(workflow_info):
                            logger.warning(
                                "Skipping selfhost media-prefixed workflow with non-media "
                                f"name: {workflow_info['key']}"
                            )
                            continue
                    workflows.append(workflow_info)
                    logger.debug(f"Found workflow: {workflow_info['key']}")
                except Exception as e:
                    logger.error(f"Failed to parse workflow {source_name}/{filename}: {e}")

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
        media_type: str = "image",
        comfyui_url: Optional[str] = None,
        runninghub_api_key: Optional[str] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        duration: Optional[float] = None,
        negative_prompt: Optional[str] = None,
        steps: Optional[int] = None,
        seed: Optional[int] = None,
        cfg: Optional[float] = None,
        sampler: Optional[str] = None,
        media_prompt_trace_context: Mapping[str, Any] | None = None,
        **params
    ) -> MediaResult:
        reference_binding_trace = params.pop(REFERENCE_IMAGE_WORKFLOW_BINDING_PARAM, None)
        reference_mode_params = _extract_reference_image_mode_params(params)
        trace_context = require_media_prompt_trace_context(
            media_prompt_trace_context,
            prompt=prompt,
            media_type=media_type,
            width=width,
            height=height,
            negative_prompt=negative_prompt,
        )
        workflow_info = self._resolve_workflow(
            workflow=workflow,
            workflow_domain=media_type,
        )
        workflow_input = _media_workflow_execution_input(workflow_info)
        workflow_file_trace = self._build_resolved_workflow_file_trace(
            workflow_info,
            workflow_input,
        )

        if not isinstance(reference_binding_trace, Mapping):
            reference_config = _reference_image_config_from_service(self)
            injection_mode = resolve_reference_image_workflow_injection_mode(
                reference_mode_params,
                reference_config,
            )
            asset_path, asset_trace = _reference_image_asset_from_task_root(
                _task_root_from_media_prompt_trace_context(trace_context)
            )
            binding = build_reference_image_workflow_binding(
                media_service=self,
                workflow=workflow,
                media_type=media_type,
                injection_mode=injection_mode,
                reference_image_asset_path=asset_path,
                reference_image_asset_trace=asset_trace,
                workflow_param_overrides=workflow_param_overrides_from_config(reference_config),
            )
            binding_trace = binding.to_trace_dict()
            _write_reference_image_injection_summary(
                trace_context,
                workflow_info=workflow_info,
                binding_trace=binding_trace,
            )
            if binding.status == "failed":
                raise ValueError(f"reference image workflow injection failed: {binding.reason}")
            if binding.injected:
                params.update(binding.injected_params)
                reference_binding_trace = binding_trace
            else:
                reference_binding_trace = binding_trace if binding.reason else None

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

        trace_safe_workflow_params = apply_reference_image_workflow_binding_trace(
            workflow_params,
            reference_binding_trace if isinstance(reference_binding_trace, Mapping) else None,
        )
        if isinstance(reference_binding_trace, Mapping) and reference_binding_trace.get("status") == "injected":
            trace_context = write_single_media_prompt_trace_context(
                _reference_binding_trace_output_dir(trace_context),
                task_id=trace_context.get("task_id") or "",
                prompt=prompt,
                negative_prompt=negative_prompt or "",
                workflow=str(workflow_info["key"]),
                workflow_input=workflow_input,
                media_type=media_type,
                source="reference_image_workflow_binding",
                frame_id=str(trace_context.get("frame_id") or ""),
                media_width=width,
                media_height=height,
                generation_context={
                    "source_artifact_path": trace_context.get("artifact_path"),
                    "reference_image_workflow_binding": dict(reference_binding_trace),
                },
                workflow_params=trace_safe_workflow_params,
                task_root=trace_context.get("task_root"),
            )
        workflow_param_trace = build_workflow_params_trace(
            trace_safe_workflow_params,
            prompt=prompt,
        )
        validate_media_prompt_trace_artifact(
            trace_context,
            prompt=prompt,
            resolved_workflow=str(workflow_info["key"]),
            resolved_workflow_input=workflow_input,
            media_type=media_type,
            width=width,
            height=height,
            negative_prompt=negative_prompt,
            workflow_param_trace=workflow_param_trace,
            workflow_file_trace=workflow_file_trace,
        )
        backend_role = "default"
        registry = self._get_backend_registry()
        if workflow_info["source"] == "selfhost" and registry is not None:
            backend_role = registry.resolve_role_for_media(
                workflow_info["key"],
                media_type,
            )
        logger.debug(f"Workflow parameters: {trace_safe_workflow_params}")
        result_artifact_written = False

        try:
            if workflow_info["source"] == "runninghub" and "workflow_id" in workflow_info:
                logger.info(f"Executing RunningHub workflow: {workflow_input}")
            else:
                logger.info(f"Executing selfhost workflow: {workflow_input}")

            result = await self._execute_workflow(
                workflow_input,
                workflow_params,
                workflow_info,
                backend_role=backend_role,
                media_prompt_trace_context=trace_context,
                media_type=media_type,
            )
            result_summary = _result_with_reference_binding(
                summarize_media_workflow_result(result),
                reference_binding_trace if isinstance(reference_binding_trace, Mapping) else None,
            )

            if result.status != "completed":
                error_msg = result.msg or "Unknown error"
                write_media_result_artifact(
                    trace_context,
                    status="failed",
                    result=result_summary,
                )
                result_artifact_written = True
                raise RuntimeError(error_msg)

            if media_type == "video":
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
            else:
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
                error_result = {
                    "error_type": type(e).__name__,
                    "error": formatted_error,
                }
                if isinstance(reference_binding_trace, Mapping):
                    error_result["reference_image_workflow_binding"] = dict(reference_binding_trace)
                write_media_result_artifact(
                    trace_context,
                    status="error",
                    result=error_result,
                )
            raise RuntimeError(formatted_error) from e
