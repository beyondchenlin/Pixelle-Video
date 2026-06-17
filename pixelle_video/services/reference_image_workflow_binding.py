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

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from pixelle_video.models.reference_image_workflow_binding import (
    ReferenceImageWorkflowBinding,
    ReferenceImageWorkflowInjectionMode,
)
from pixelle_video.utils.workflow_capabilities import get_workflow_capabilities

REFERENCE_IMAGE_WORKFLOW_BINDING_PARAM = "_reference_image_workflow_binding_trace"
_ALLOWED_INJECTION_MODES = {"off", "auto", "required"}


def normalize_reference_image_workflow_injection_mode(
    value: Any,
    *,
    default: str = "off",
) -> ReferenceImageWorkflowInjectionMode:
    normalized = str(value or default or "off").strip().lower()
    if normalized not in _ALLOWED_INJECTION_MODES:
        raise ValueError("reference image workflow_injection_mode must be one of: off, auto, required")
    return normalized  # type: ignore[return-value]


def resolve_reference_image_workflow_injection_mode(
    params: Mapping[str, Any] | None,
    reference_image_config: Mapping[str, Any] | Any | None,
) -> ReferenceImageWorkflowInjectionMode:
    params = params or {}
    for key in ("reference_image_workflow_injection_mode", "workflow_injection_mode", "ref_image_workflow_injection_mode"):
        if params.get(key) is not None:
            return normalize_reference_image_workflow_injection_mode(params[key])
    structured_input = params.get("reference_image")
    if isinstance(structured_input, Mapping) and structured_input.get("workflow_injection_mode") is not None:
        return normalize_reference_image_workflow_injection_mode(structured_input.get("workflow_injection_mode"))
    if isinstance(reference_image_config, Mapping):
        return normalize_reference_image_workflow_injection_mode(reference_image_config.get("workflow_injection_mode"), default="off")
    return normalize_reference_image_workflow_injection_mode(
        getattr(reference_image_config, "workflow_injection_mode", "off"),
        default="off",
    )


def workflow_param_overrides_from_config(
    reference_image_config: Mapping[str, Any] | Any | None,
) -> Mapping[str, Any]:
    if isinstance(reference_image_config, Mapping):
        value = reference_image_config.get("workflow_param_overrides")
        return value if isinstance(value, Mapping) else {}
    value = getattr(reference_image_config, "workflow_param_overrides", {})
    return value if isinstance(value, Mapping) else {}


def build_reference_image_workflow_binding(
    *,
    media_service: Any,
    workflow: str | None,
    media_type: str,
    injection_mode: ReferenceImageWorkflowInjectionMode,
    reference_image_asset_path: str | None,
    reference_image_asset_trace: Mapping[str, Any] | None,
    workflow_param_overrides: Mapping[str, Any] | None = None,
) -> ReferenceImageWorkflowBinding:
    workflow_info = _resolve_workflow_info(media_service, workflow=workflow, media_type=media_type)
    workflow_key = str(workflow_info.get("key") or workflow or "")
    source = str(workflow_info.get("source") or "")
    asset_trace = dict(reference_image_asset_trace or {})

    if injection_mode == "off":
        return _binding(
            status="skipped",
            injection_mode=injection_mode,
            workflow_key=workflow_key,
            media_type=media_type,
            reason="workflow_injection_mode_off",
            asset_trace=asset_trace,
        )
    if not reference_image_asset_path:
        return _handle_unavailable(
            injection_mode=injection_mode,
            workflow_key=workflow_key,
            media_type=media_type,
            reason="reference_image_asset_missing",
            asset_trace=asset_trace,
        )
    asset_path = Path(reference_image_asset_path)
    if not asset_path.is_file():
        return _handle_unavailable(
            injection_mode=injection_mode,
            workflow_key=workflow_key,
            media_type=media_type,
            reason="reference_image_workflow_asset_not_found",
            asset_trace=asset_trace,
        )
    if source != "selfhost":
        return _handle_unavailable(
            injection_mode=injection_mode,
            workflow_key=workflow_key,
            media_type=media_type,
            reason="reference_image_workflow_injection_requires_selfhost",
            asset_trace=asset_trace,
        )

    capabilities = get_workflow_capabilities(workflow_info)
    explicit_names = _override_param_names(
        workflow_param_overrides or {},
        workflow_key=workflow_key,
    )
    candidate_param_names = explicit_names or capabilities.reference_image_param_names
    if not candidate_param_names:
        return _handle_unavailable(
            injection_mode=injection_mode,
            workflow_key=workflow_key,
            media_type=media_type,
            reason="workflow_does_not_declare_reference_image_param",
            asset_trace=asset_trace,
            declared_reference_params=list(capabilities.reference_image_param_names),
        )

    trace_value = {
        "asset_sha256": asset_trace.get("sha256"),
        "workflow_asset_relative_path": asset_trace.get("workflow_asset_relative_path"),
        "mime_type": asset_trace.get("mime_type"),
        "width": asset_trace.get("width"),
        "height": asset_trace.get("height"),
        "source": "reference_image_asset",
    }
    injected_params = {name: str(asset_path) for name in candidate_param_names}
    workflow_param_trace_values = {name: trace_value for name in candidate_param_names}
    return ReferenceImageWorkflowBinding(
        status="injected",
        injection_mode=injection_mode,
        workflow_key=workflow_key,
        media_type=media_type,
        injected_params=injected_params,
        workflow_param_trace_values=workflow_param_trace_values,
        summary={
            "param_names": list(candidate_param_names),
            "asset": asset_trace,
            "workflow_source": source,
        },
    )


def apply_reference_image_workflow_binding_trace(
    workflow_params: Mapping[str, Any],
    binding_trace: Mapping[str, Any] | None,
) -> dict[str, Any]:
    params = dict(workflow_params or {})
    if not isinstance(binding_trace, Mapping):
        return params
    trace_values = binding_trace.get("workflow_param_trace_values")
    if not isinstance(trace_values, Mapping):
        return params
    for key, value in trace_values.items():
        name = str(key or "").strip()
        if name and name in params:
            params[name] = value
    return params


def _resolve_workflow_info(media_service: Any, *, workflow: str | None, media_type: str) -> Mapping[str, Any]:
    resolver = getattr(media_service, "_resolve_workflow", None)
    if not callable(resolver):
        raise ValueError("media_service._resolve_workflow is required for reference image workflow binding")
    return resolver(workflow=workflow, workflow_domain=media_type)


def _override_param_names(overrides: Mapping[str, Any], *, workflow_key: str) -> tuple[str, ...]:
    candidates = [workflow_key, Path(workflow_key).name, "*"]
    for key in candidates:
        if key not in overrides:
            continue
        return _normalize_param_names(overrides.get(key))
    return ()


def _normalize_param_names(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, Mapping):
        values = value.get("reference_image") or value.get("params") or value.get("param_names") or []
        if isinstance(values, str):
            values = [values]
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        values = list(value)
    else:
        values = []
    result: list[str] = []
    for item in values:
        text = str(item or "").strip()
        if text and text not in result:
            result.append(text)
    return tuple(result)


def _handle_unavailable(
    *,
    injection_mode: ReferenceImageWorkflowInjectionMode,
    workflow_key: str,
    media_type: str,
    reason: str,
    asset_trace: Mapping[str, Any],
    declared_reference_params: list[str] | None = None,
) -> ReferenceImageWorkflowBinding:
    if injection_mode == "required":
        return _binding(
            status="failed",
            injection_mode=injection_mode,
            workflow_key=workflow_key,
            media_type=media_type,
            reason=reason,
            error=reason,
            asset_trace=asset_trace,
            declared_reference_params=declared_reference_params,
        )
    return _binding(
        status="skipped",
        injection_mode=injection_mode,
        workflow_key=workflow_key,
        media_type=media_type,
        reason=reason,
        asset_trace=asset_trace,
        declared_reference_params=declared_reference_params,
    )


def _binding(
    *,
    status: str,
    injection_mode: ReferenceImageWorkflowInjectionMode,
    workflow_key: str,
    media_type: str,
    reason: str = "",
    error: str = "",
    asset_trace: Mapping[str, Any] | None = None,
    declared_reference_params: list[str] | None = None,
) -> ReferenceImageWorkflowBinding:
    summary: dict[str, Any] = {}
    if asset_trace:
        summary["asset"] = dict(asset_trace)
    if declared_reference_params is not None:
        summary["declared_reference_params"] = list(declared_reference_params)
    return ReferenceImageWorkflowBinding(
        status=status,  # type: ignore[arg-type]
        injection_mode=injection_mode,
        workflow_key=workflow_key,
        media_type=media_type,
        reason=reason,
        error=error,
        summary=summary,
    )
