from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlencode, urljoin, urlparse
from uuid import uuid4

import aiohttp

from pixelle_video.models.visual_anchor_two_stage import (
    VisualAnchorImageGenerationRequest,
)
from pixelle_video.services.visual_anchor_reference_condition import (
    IDENTITY_REFERENCE_CONDITION_CROP,
    IDENTITY_REFERENCE_CONDITION_HEIGHT,
    IDENTITY_REFERENCE_CONDITION_UPSCALE_METHOD,
    IDENTITY_REFERENCE_CONDITION_WIDTH,
)

VISUAL_ANCHOR_GENERATION_REQUEST_PARAM = "_visual_anchor_generation_request"
_SAFE_FRAME_ID_RE = re.compile(r"[^A-Za-z0-9_-]+")


def validate_visual_anchor_first_generation_binding(
    *,
    request_payload: Mapping[str, Any],
    prompt: str,
    negative_prompt: str | None,
    seed: int | None,
    media_type: str,
    trace_context: Mapping[str, Any],
    workflow_info: Mapping[str, Any],
    workflow_file_trace: Mapping[str, Any],
    reference_binding_trace: Mapping[str, Any] | None,
    workflow_params: Mapping[str, Any],
) -> dict[str, Any]:
    request = VisualAnchorImageGenerationRequest.model_validate(request_payload)
    task_root = _task_root(trace_context)
    binding_audit_path = _binding_audit_path(task_root, request.frame_id)
    if binding_audit_path.exists():
        raise ValueError(
            "visual-anchor first generation was already submitted or recorded for this task and frame"
        )
    failures: list[str] = []

    def require(condition: bool, message: str) -> None:
        if not condition:
            failures.append(message)

    require(media_type == "image", "request must use the image media domain")
    require(
        str(workflow_info.get("source") or "") == "selfhost",
        "request must use the local self-hosted image workflow",
    )
    require(prompt == request.final_positive_prompt, "positive prompt differs from request")
    require(
        (negative_prompt or "") == request.final_negative_prompt,
        "negative prompt differs from request",
    )
    require(seed == request.random_seed, "random seed differs from request")
    expected_execution = request.expected_execution
    require(
        workflow_params.get("width") == expected_execution.width,
        "image width differs from the registered execution contract",
    )
    require(
        workflow_params.get("height") == expected_execution.height,
        "image height differs from the registered execution contract",
    )
    require(
        str(trace_context.get("task_id") or "") == request.task_id,
        "task id differs from request",
    )
    require(
        str(trace_context.get("frame_id") or "") == request.frame_id,
        "frame id differs from request",
    )
    require(
        str(workflow_info.get("key") or "") == request.workflow_key,
        "workflow key differs from request",
    )
    require(
        str(workflow_file_trace.get("workflow_file_sha256") or "")
        == request.workflow_version_sha256,
        "workflow version differs from request",
    )
    if request.identity_conditioning_mode == "text_profile":
        return _validate_text_profile_first_generation_binding(
            request=request,
            task_root=task_root,
            binding_audit_path=binding_audit_path,
            reference_binding_trace=reference_binding_trace,
            failures=failures,
        )
    require(
        isinstance(reference_binding_trace, Mapping),
        "reference binding trace is missing",
    )

    binding = dict(reference_binding_trace or {})
    require(binding.get("status") == "injected", "reference image was not injected")
    require(
        binding.get("injection_mode") == "required",
        "reference injection was not fail-closed",
    )
    condition = request.identity_reference_condition
    if condition is None:
        raise ValueError("reference-image generation request has no reference condition")
    summary = binding.get("summary")
    summary = dict(summary) if isinstance(summary, Mapping) else {}
    param_names = summary.get("param_names")
    require(
        isinstance(param_names, list)
        and param_names == [condition.workflow_parameter],
        "reference image was not injected into the inspected workflow parameter",
    )
    asset = summary.get("asset")
    asset = dict(asset) if isinstance(asset, Mapping) else {}
    bound_asset_sha256 = asset.get("workflow_sha256") or asset.get("sha256")
    require(
        bound_asset_sha256 == condition.asset_sha256,
        "injected reference digest differs from request",
    )
    require(
        str(asset.get("workflow_asset_relative_path") or "").replace("\\", "/")
        == condition.workflow_asset_relative_path,
        "injected reference path differs from request",
    )

    actual_reference_path = workflow_params.get(condition.workflow_parameter)
    if isinstance(actual_reference_path, str) and actual_reference_path.strip():
        actual_path = Path(actual_reference_path).resolve()
        try:
            actual_relative = actual_path.relative_to(task_root).as_posix()
        except ValueError:
            actual_relative = ""
        actual_path_is_safe = bool(actual_relative)
        require(
            actual_path_is_safe,
            "actual injected file is not inside the task directory",
        )
        require(
            actual_path_is_safe and actual_path.is_file(),
            "injected reference file does not exist",
        )
        actual_sha256 = (
            _file_sha256(actual_path)
            if actual_path_is_safe and actual_path.is_file()
            else ""
        )
        require(
            actual_sha256 == condition.asset_sha256,
            "actual injected file digest differs from request",
        )
        require(
            actual_relative == condition.workflow_asset_relative_path,
            "actual injected file is not the registered task-local reference",
        )
    else:
        require(False, "actual reference workflow parameter is missing")

    if failures:
        failed_audit = {
            "schema_version": "visual_anchor_first_generation_binding_audit.v6",
            "request_version": request.request_version,
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": "failed",
            "task_id": request.task_id,
            "frame_id": request.frame_id,
            "generation_attempt": 1,
            "random_seed": request.random_seed,
            "selected_fusion_method": request.selected_fusion_method,
            "final_manifestation": request.final_manifestation,
            "prompt_assembly_trace": _prompt_assembly_trace_payload(request),
            "failure_reason": "; ".join(failures),
            "failure_codes": list(failures),
            "positive_prompt_sha256": _text_sha256(request.final_positive_prompt),
            "negative_prompt_sha256": _text_sha256(request.final_negative_prompt),
            "prompt_versions": {
                "content_stage": request.content_stage_prompt_version,
                "fusion_stage": request.fusion_stage_prompt_version,
            },
            "identity_profile_id": request.identity_profile_id,
            "identity_display_name": request.identity_display_name,
            "identity_core_traits": list(request.identity_core_traits),
            "identity_resource_version": request.identity_resource_version,
            "identity_content_sha256": request.identity_content_sha256,
            "identity_conditioning_mode": request.identity_conditioning_mode,
            "reference_condition": condition.model_dump(mode="json"),
            "workflow_key": request.workflow_key,
            "workflow_version_sha256": request.workflow_version_sha256,
            "expected_execution": expected_execution.model_dump(mode="json"),
            "actual_binding": {
                "injection_mode": binding.get("injection_mode"),
                "status": binding.get("status"),
                "param_names": param_names,
                "asset_sha256": bound_asset_sha256,
                "workflow_asset_relative_path": asset.get(
                    "workflow_asset_relative_path"
                ),
            },
        }
        _write_binding_audit(
            task_root,
            request.frame_id,
            failed_audit,
            require_new=True,
        )
        raise ValueError(
            "visual-anchor first generation binding rejected: " + "; ".join(failures)
        )

    audit = {
        "schema_version": "visual_anchor_first_generation_binding_audit.v6",
        "request_version": request.request_version,
        "recorded_at_utc": datetime.now(UTC).isoformat(),
        "status": "ready_to_submit",
        "task_id": request.task_id,
        "frame_id": request.frame_id,
        "generation_attempt": 1,
        "random_seed": request.random_seed,
        "selected_fusion_method": request.selected_fusion_method,
        "final_manifestation": request.final_manifestation,
        "prompt_assembly_trace": _prompt_assembly_trace_payload(request),
        "positive_prompt_sha256": _text_sha256(request.final_positive_prompt),
        "negative_prompt_sha256": _text_sha256(request.final_negative_prompt),
        "prompt_versions": {
            "content_stage": request.content_stage_prompt_version,
            "fusion_stage": request.fusion_stage_prompt_version,
        },
        "identity_profile_id": request.identity_profile_id,
        "identity_display_name": request.identity_display_name,
        "identity_core_traits": list(request.identity_core_traits),
        "identity_resource_version": request.identity_resource_version,
        "identity_content_sha256": request.identity_content_sha256,
        "identity_conditioning_mode": request.identity_conditioning_mode,
        "reference_condition": condition.model_dump(mode="json"),
        "workflow_key": request.workflow_key,
        "workflow_version_sha256": request.workflow_version_sha256,
        "expected_execution": expected_execution.model_dump(mode="json"),
        "actual_binding": {
            "injection_mode": binding.get("injection_mode"),
            "status": binding.get("status"),
            "param_names": param_names,
            "asset_sha256": bound_asset_sha256,
            "workflow_asset_relative_path": asset.get(
                "workflow_asset_relative_path"
            ),
        },
    }
    _write_binding_audit(
        task_root,
        request.frame_id,
        audit,
        require_new=True,
    )
    return audit


def _validate_text_profile_first_generation_binding(
    *,
    request: VisualAnchorImageGenerationRequest,
    task_root: Path,
    binding_audit_path: Path,
    reference_binding_trace: Mapping[str, Any] | None,
    failures: list[str],
) -> dict[str, Any]:
    binding = dict(reference_binding_trace or {})
    if binding.get("status") == "injected":
        failures.append("text-profile workflow unexpectedly injected a reference image")
    if binding.get("injection_mode") == "required":
        failures.append("text-profile workflow unexpectedly required reference injection")

    audit = _first_generation_binding_audit_payload(
        request=request,
        status="failed" if failures else "ready_to_submit",
        failure_codes=failures,
        actual_binding={
            "injection_mode": binding.get("injection_mode"),
            "status": binding.get("status") or "not_injected",
            "param_names": [],
            "asset_sha256": None,
            "workflow_asset_relative_path": None,
        },
    )
    _write_binding_audit(
        task_root,
        request.frame_id,
        audit,
        require_new=True,
    )
    if failures:
        raise ValueError(
            "visual-anchor first generation binding rejected: "
            + "; ".join(failures)
        )
    if not binding_audit_path.is_file():
        raise ValueError("visual-anchor binding audit was not persisted")
    return audit


def _first_generation_binding_audit_payload(
    *,
    request: VisualAnchorImageGenerationRequest,
    status: str,
    failure_codes: list[str],
    actual_binding: Mapping[str, Any],
) -> dict[str, Any]:
    payload = {
        "schema_version": "visual_anchor_first_generation_binding_audit.v6",
        "request_version": request.request_version,
        "recorded_at_utc": datetime.now(UTC).isoformat(),
        "status": status,
        "task_id": request.task_id,
        "frame_id": request.frame_id,
        "generation_attempt": 1,
        "random_seed": request.random_seed,
        "selected_fusion_method": request.selected_fusion_method,
        "final_manifestation": request.final_manifestation,
        "prompt_assembly_trace": _prompt_assembly_trace_payload(request),
        "positive_prompt_sha256": _text_sha256(request.final_positive_prompt),
        "negative_prompt_sha256": _text_sha256(request.final_negative_prompt),
        "prompt_versions": {
            "content_stage": request.content_stage_prompt_version,
            "fusion_stage": request.fusion_stage_prompt_version,
        },
        "identity_profile_id": request.identity_profile_id,
        "identity_display_name": request.identity_display_name,
        "identity_core_traits": list(request.identity_core_traits),
        "identity_resource_version": request.identity_resource_version,
        "identity_content_sha256": request.identity_content_sha256,
        "identity_conditioning_mode": request.identity_conditioning_mode,
        "reference_condition": None,
        "target_visual_style": request.target_visual_style.model_dump(mode="json"),
        "visible_text_policy": request.visible_text_policy.model_dump(mode="json"),
        "workflow_key": request.workflow_key,
        "workflow_version_sha256": request.workflow_version_sha256,
        "expected_execution": request.expected_execution.model_dump(mode="json"),
        "actual_binding": dict(actual_binding),
    }
    if failure_codes:
        payload["failure_reason"] = "; ".join(failure_codes)
        payload["failure_codes"] = list(failure_codes)
    return payload


def _prompt_assembly_trace_payload(
    request: VisualAnchorImageGenerationRequest,
) -> dict[str, Any] | None:
    trace = request.prompt_assembly_trace
    return trace.model_dump(mode="json") if trace is not None else None


async def verify_visual_anchor_executed_workflow_binding(
    *,
    request_payload: Mapping[str, Any],
    pre_submit_audit: Mapping[str, Any],
    workflow_result: Any,
    comfyui_url: str,
    task_root: str | Path,
) -> dict[str, Any]:
    """Verify the executed ComfyUI history and uploaded reference bytes."""

    request = VisualAnchorImageGenerationRequest.model_validate(request_payload)
    root = Path(task_root).resolve()
    try:
        return await _verify_visual_anchor_executed_workflow_binding(
            request=request,
            pre_submit_audit=pre_submit_audit,
            workflow_result=workflow_result,
            comfyui_url=comfyui_url,
            task_root=root,
        )
    except Exception as exc:
        failure_audit = dict(pre_submit_audit)
        failure_audit.update(
            {
                "status": "failed",
                "recorded_at_utc": datetime.now(UTC).isoformat(),
                "failure_reason": str(exc),
                "actual_execution": {
                    "comfyui_prompt_id": str(
                        getattr(workflow_result, "prompt_id", "") or ""
                    ).strip(),
                    "captured_first_output_artifacts": (
                        _captured_first_output_artifacts(
                            root,
                            request.frame_id,
                        )
                    ),
                },
            }
        )
        _write_binding_audit(root, request.frame_id, failure_audit)
        raise


async def _verify_visual_anchor_executed_workflow_binding(
    *,
    request: VisualAnchorImageGenerationRequest,
    pre_submit_audit: Mapping[str, Any],
    workflow_result: Any,
    comfyui_url: str,
    task_root: Path,
) -> dict[str, Any]:
    if pre_submit_audit.get("status") != "ready_to_submit":
        raise ValueError("visual-anchor pre-submit binding audit is invalid")
    if str(getattr(workflow_result, "status", "") or "") != "completed":
        raise ValueError("visual-anchor workflow did not complete")
    prompt_id = str(getattr(workflow_result, "prompt_id", "") or "").strip()
    if not prompt_id:
        raise ValueError("visual-anchor workflow result has no ComfyUI prompt id")
    base_url = str(comfyui_url or "").strip().rstrip("/")
    if not base_url.startswith(("http://", "https://")):
        raise ValueError("visual-anchor workflow has no valid local ComfyUI URL")
    if request.identity_conditioning_mode == "text_profile":
        return await _verify_text_profile_executed_workflow_binding(
            request=request,
            pre_submit_audit=pre_submit_audit,
            workflow_result=workflow_result,
            base_url=base_url,
            prompt_id=prompt_id,
            task_root=task_root,
        )

    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        (
            generated_output_sha256,
            generated_output_reference,
            generated_output_payload,
        ) = await _download_first_generated_image(
            session=session,
            base_url=base_url,
            workflow_result=workflow_result,
        )
        generated_output_artifact = _persist_first_generated_output(
            task_root=task_root,
            frame_id=request.frame_id,
            filename=generated_output_reference["filename"],
            payload=generated_output_payload,
            expected_sha256=generated_output_sha256,
        )
        history_url = f"{base_url}/history/{quote(prompt_id, safe='')}"
        async with session.get(history_url) as response:
            if response.status != 200:
                raise ValueError(
                    "visual-anchor could not read the executed ComfyUI history"
                )
            history_payload = await response.json()
        workflow, execution_status = _executed_workflow(
            history_payload,
            prompt_id=prompt_id,
        )
        condition = request.identity_reference_condition
        if condition is None:
            raise ValueError("reference-image execution has no reference condition")
        source_node = _workflow_node(workflow, condition.workflow_node_id)
        conditioner_node = _workflow_node(workflow, condition.conditioning_node_id)
        sampler_node = _workflow_node(workflow, condition.sampler_node_id)
        scale_node_id = condition.binding_path_node_ids[1]
        scale_node = _workflow_node(workflow, scale_node_id)

        source_input = str(
            _node_inputs(source_node).get(condition.workflow_node_input_field) or ""
        ).strip()
        if not source_input:
            raise ValueError(
                "executed ComfyUI reference-image node has no uploaded input"
            )
        _require_node_class(
            source_node,
            condition.workflow_node_class_type,
            "reference input",
        )
        _require_node_class(
            conditioner_node,
            condition.conditioning_node_class_type,
            "reference conditioning",
        )
        _require_node_class(scale_node, "ImageScale", "reference scale")
        _require_node_class(
            sampler_node,
            condition.sampler_node_class_type,
            "sampler",
        )
        scale_inputs = _node_inputs(scale_node)
        conditioner_inputs = _node_inputs(conditioner_node)
        sampler_inputs = _node_inputs(sampler_node)
        if _linked_node_id(scale_inputs.get("image")) != condition.workflow_node_id:
            raise ValueError("executed ComfyUI reference input did not enter ImageScale")
        if (
            scale_inputs.get("width") != IDENTITY_REFERENCE_CONDITION_WIDTH
            or scale_inputs.get("height") != IDENTITY_REFERENCE_CONDITION_HEIGHT
            or scale_inputs.get("crop") != IDENTITY_REFERENCE_CONDITION_CROP
            or scale_inputs.get("upscale_method")
            != IDENTITY_REFERENCE_CONDITION_UPSCALE_METHOD
        ):
            raise ValueError(
                "executed ComfyUI reference conditioning did not preserve the registered 32x32 scale"
            )
        if _linked_node_id(conditioner_inputs.get("image1")) != scale_node_id:
            raise ValueError("executed ComfyUI scaled reference did not enter conditioning")
        if (
            conditioner_inputs.get("image2") is not None
            or conditioner_inputs.get("image3") is not None
            or conditioner_inputs.get("image_encoder") is not None
        ):
            raise ValueError(
                "executed ComfyUI workflow conditioned on more than one reference image"
            )
        if conditioner_inputs.get("auto_resize_images") is not False:
            raise ValueError(
                "executed ComfyUI reference conditioner enabled automatic resizing"
            )
        clip_node_id = _linked_node_id(conditioner_inputs.get("clip"))
        prompt_node_id = _linked_node_id(conditioner_inputs.get("prompt"))
        vae_node_id = _linked_node_id(conditioner_inputs.get("vae"))
        if clip_node_id is None or prompt_node_id is None or vae_node_id is None:
            raise ValueError(
                "executed ComfyUI reference conditioner is missing the text encoder, final prompt, or VAE"
            )
        _require_node_class(
            _workflow_node(workflow, clip_node_id),
            "CLIPLoaderGGUF",
            "reference text encoder",
        )
        _require_node_class(
            _workflow_node(workflow, prompt_node_id),
            "PrimitiveStringMultiline",
            "reference final prompt",
        )
        _require_node_class(
            _workflow_node(workflow, vae_node_id),
            "VAELoader",
            "reference VAE",
        )
        if prompt_node_id != _actual_parameter_node_id(workflow, "prompt"):
            raise ValueError(
                "executed ComfyUI reference conditioner did not receive the declared final prompt"
            )
        if (
            _linked_node_id(sampler_inputs.get("positive"))
            != condition.conditioning_node_id
        ):
            raise ValueError("executed ComfyUI reference conditioning did not enter sampling")
        if sampler_inputs.get("seed") != request.random_seed:
            raise ValueError("executed ComfyUI random seed differs from the request")
        if _actual_parameter(workflow, "prompt") != request.final_positive_prompt:
            raise ValueError("executed ComfyUI positive prompt differs from the request")
        if (
            _actual_parameter(workflow, "negative_prompt")
            != request.final_negative_prompt
        ):
            raise ValueError("executed ComfyUI negative prompt differs from the request")
        if _reference_conditioner_count(workflow) != 1:
            raise ValueError(
                "executed ComfyUI workflow must contain exactly one reference conditioner"
            )
        actual_width = _positive_actual_parameter(workflow, "width")
        actual_height = _positive_actual_parameter(workflow, "height")
        sampler_config = {
            key: value
            for key, value in sampler_inputs.items()
            if key
            in {
                "seed",
                "steps",
                "cfg",
                "sampler_name",
                "scheduler",
                "denoise",
            }
        }
        model_files = _actual_model_files(workflow)
        expected_execution = request.expected_execution
        expected_sampler_config = {
            "seed": request.random_seed,
            "steps": expected_execution.steps,
            "cfg": expected_execution.cfg,
            "sampler_name": expected_execution.sampler_name,
            "scheduler": expected_execution.scheduler,
            "denoise": expected_execution.denoise,
        }
        if actual_width != expected_execution.width:
            raise ValueError(
                "executed ComfyUI width differs from the registered execution contract"
            )
        if actual_height != expected_execution.height:
            raise ValueError(
                "executed ComfyUI height differs from the registered execution contract"
            )
        if model_files != expected_execution.model_files:
            raise ValueError(
                "executed ComfyUI model files differ from the registered execution contract"
            )
        if sampler_config != expected_sampler_config:
            raise ValueError(
                "executed ComfyUI sampler configuration differs from the registered execution contract"
            )
        execution_config = {
            "workflow_key": request.workflow_key,
            "workflow_version_sha256": request.workflow_version_sha256,
            "width": actual_width,
            "height": actual_height,
            "model_files": model_files,
            "sampler": sampler_config,
            "reference_conditioning": {
                "mode": "TextEncodeZImageOmni",
                "input_count": 1,
                "width": scale_inputs.get("width"),
                "height": scale_inputs.get("height"),
                "crop": scale_inputs.get("crop"),
                "upscale_method": scale_inputs.get("upscale_method"),
                "auto_resize_images": conditioner_inputs.get(
                    "auto_resize_images"
                ),
            },
        }

        reference_query = urlencode(
            {"filename": source_input, "type": "input"}
        )
        async with session.get(f"{base_url}/view?{reference_query}") as response:
            if response.status != 200:
                raise ValueError(
                    "visual-anchor could not read the reference uploaded to ComfyUI"
                )
            uploaded_reference = await response.read()
    uploaded_sha256 = hashlib.sha256(uploaded_reference).hexdigest()
    if uploaded_sha256 != condition.asset_sha256:
        raise ValueError(
            "executed ComfyUI reference bytes differ from the registered task asset"
        )

    audit = dict(pre_submit_audit)
    audit.update(
        {
            "status": "passed",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "actual_execution": {
                "comfyui_prompt_id": prompt_id,
                "execution_status": execution_status,
                "reference_input_node_id": condition.workflow_node_id,
                "reference_input_node_class_type": condition.workflow_node_class_type,
                "reference_input_node_field": condition.workflow_node_input_field,
                "reference_input_filename": source_input,
                "uploaded_reference_sha256": uploaded_sha256,
                "conditioning_node_id": condition.conditioning_node_id,
                "conditioning_node_class_type": condition.conditioning_node_class_type,
                "reference_conditioning_mode": condition.conditioning_node_class_type,
                "reference_conditioning_input_count": 1,
                "reference_scale_node_id": scale_node_id,
                "reference_scale_node_class_type": "ImageScale",
                "reference_conditioning_width": scale_inputs.get("width"),
                "reference_conditioning_height": scale_inputs.get("height"),
                "reference_conditioning_crop": scale_inputs.get("crop"),
                "reference_conditioning_upscale_method": scale_inputs.get(
                    "upscale_method"
                ),
                "reference_conditioning_auto_resize": conditioner_inputs.get(
                    "auto_resize_images"
                ),
                "sampler_node_id": condition.sampler_node_id,
                "sampler_node_class_type": condition.sampler_node_class_type,
                "binding_path_node_ids": list(condition.binding_path_node_ids),
                "random_seed": request.random_seed,
                "width": actual_width,
                "height": actual_height,
                "model_files": model_files,
                "sampler_config": sampler_config,
                "execution_config_sha256": _canonical_json_sha256(
                    execution_config
                ),
                "generated_output_sha256": generated_output_sha256,
                "generated_output_reference": generated_output_reference,
                "generated_output_artifact": generated_output_artifact,
                "positive_prompt_sha256": _text_sha256(
                    request.final_positive_prompt
                ),
                "negative_prompt_sha256": _text_sha256(
                    request.final_negative_prompt
                ),
            },
        }
    )
    _write_binding_audit(task_root, request.frame_id, audit)
    return audit


async def _verify_text_profile_executed_workflow_binding(
    *,
    request: VisualAnchorImageGenerationRequest,
    pre_submit_audit: Mapping[str, Any],
    workflow_result: Any,
    base_url: str,
    prompt_id: str,
    task_root: Path,
) -> dict[str, Any]:
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        (
            generated_output_sha256,
            generated_output_reference,
            generated_output_payload,
        ) = await _download_first_generated_image(
            session=session,
            base_url=base_url,
            workflow_result=workflow_result,
        )
        generated_output_artifact = _persist_first_generated_output(
            task_root=task_root,
            frame_id=request.frame_id,
            filename=generated_output_reference["filename"],
            payload=generated_output_payload,
            expected_sha256=generated_output_sha256,
        )
        history_url = f"{base_url}/history/{quote(prompt_id, safe='')}"
        async with session.get(history_url) as response:
            if response.status != 200:
                raise ValueError(
                    "visual-anchor could not read the executed ComfyUI history"
                )
            history_payload = await response.json()

    workflow, execution_status = _executed_workflow(
        history_payload,
        prompt_id=prompt_id,
    )
    if _actual_parameter(workflow, "prompt") != request.final_positive_prompt:
        raise ValueError("executed ComfyUI positive prompt differs from the request")
    if request.negative_prompt_supported and (
        _actual_parameter(workflow, "negative_prompt")
        != request.final_negative_prompt
    ):
        raise ValueError("executed ComfyUI negative prompt differs from the request")

    sampler_node_id, sampler_node = _single_image_sampler(workflow)
    sampler_inputs = _node_inputs(sampler_node)
    if sampler_inputs.get("seed") != request.random_seed:
        raise ValueError("executed ComfyUI random seed differs from the request")
    actual_width = _positive_actual_parameter(workflow, "width")
    actual_height = _positive_actual_parameter(workflow, "height")
    sampler_config = {
        key: value
        for key, value in sampler_inputs.items()
        if key
        in {
            "seed",
            "steps",
            "cfg",
            "sampler_name",
            "scheduler",
            "denoise",
        }
    }
    model_files = _actual_model_files(workflow)
    expected_execution = request.expected_execution
    expected_sampler_config = {
        "seed": request.random_seed,
        "steps": expected_execution.steps,
        "cfg": expected_execution.cfg,
        "sampler_name": expected_execution.sampler_name,
        "scheduler": expected_execution.scheduler,
        "denoise": expected_execution.denoise,
    }
    if actual_width != expected_execution.width:
        raise ValueError(
            "executed ComfyUI width differs from the registered execution contract"
        )
    if actual_height != expected_execution.height:
        raise ValueError(
            "executed ComfyUI height differs from the registered execution contract"
        )
    if model_files != expected_execution.model_files:
        raise ValueError(
            "executed ComfyUI model files differ from the registered execution contract"
        )
    if sampler_config != expected_sampler_config:
        raise ValueError(
            "executed ComfyUI sampler configuration differs from the registered execution contract"
        )
    if _reference_conditioner_count(workflow) != 0:
        raise ValueError(
            "text-profile visual-anchor workflow unexpectedly used reference conditioning"
        )

    execution_config = {
        "workflow_key": request.workflow_key,
        "workflow_version_sha256": request.workflow_version_sha256,
        "width": actual_width,
        "height": actual_height,
        "model_files": model_files,
        "sampler": sampler_config,
        "identity_conditioning": {
            "mode": "text_profile",
            "reference_input_count": 0,
        },
    }
    audit = dict(pre_submit_audit)
    audit.update(
        {
            "status": "passed",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "actual_execution": {
                "comfyui_prompt_id": prompt_id,
                "execution_status": execution_status,
                "identity_conditioning_mode": "text_profile",
                "reference_conditioning_input_count": 0,
                "sampler_node_id": sampler_node_id,
                "sampler_node_class_type": str(
                    sampler_node.get("class_type") or ""
                ),
                "random_seed": request.random_seed,
                "width": actual_width,
                "height": actual_height,
                "model_files": model_files,
                "sampler_config": sampler_config,
                "execution_config_sha256": _canonical_json_sha256(
                    execution_config
                ),
                "generated_output_sha256": generated_output_sha256,
                "generated_output_reference": generated_output_reference,
                "generated_output_artifact": generated_output_artifact,
                "positive_prompt_sha256": _text_sha256(
                    request.final_positive_prompt
                ),
                "negative_prompt_sha256": _text_sha256(
                    request.final_negative_prompt
                ),
            },
        }
    )
    _write_binding_audit(task_root, request.frame_id, audit)
    return audit


def record_visual_anchor_first_generation_failure(
    *,
    request_payload: Mapping[str, Any],
    pre_submit_audit: Mapping[str, Any],
    task_root: str | Path,
    reason: object,
    workflow_result: Any = None,
) -> dict[str, Any]:
    request = VisualAnchorImageGenerationRequest.model_validate(request_payload)
    root = Path(task_root).resolve()
    failure_reason = " ".join(str(reason or "workflow execution failed").split())
    audit = dict(pre_submit_audit)
    audit.update(
        {
            "status": "failed",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "failure_reason": failure_reason,
            "actual_execution": {
                "comfyui_prompt_id": str(
                    getattr(workflow_result, "prompt_id", "") or ""
                ).strip(),
                "execution_status": str(
                    getattr(workflow_result, "status", "") or "failed"
                ).strip(),
                "captured_first_output_artifacts": (
                    _captured_first_output_artifacts(root, request.frame_id)
                ),
            },
        }
    )
    _write_binding_audit(root, request.frame_id, audit)
    return audit


def _task_root(trace_context: Mapping[str, Any]) -> Path:
    value = trace_context.get("task_root")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("visual-anchor generation requires a task root")
    root = Path(value).resolve()
    if not root.is_dir():
        raise ValueError("visual-anchor task root does not exist")
    return root


def _executed_workflow(
    history_payload: Any,
    *,
    prompt_id: str,
) -> tuple[Mapping[str, Any], str]:
    if not isinstance(history_payload, Mapping):
        raise ValueError("ComfyUI history response is invalid")
    record = history_payload.get(prompt_id)
    if not isinstance(record, Mapping):
        raise ValueError("ComfyUI history does not contain the executed prompt")
    status = record.get("status")
    if not isinstance(status, Mapping):
        raise ValueError("ComfyUI history has no execution status")
    status_text = str(status.get("status_str") or "").strip()
    if status_text != "success" or status.get("completed") is not True:
        raise ValueError("ComfyUI history does not record a successful completion")
    prompt_record = record.get("prompt")
    if (
        not isinstance(prompt_record, list)
        or len(prompt_record) < 3
        or not isinstance(prompt_record[2], Mapping)
    ):
        raise ValueError("ComfyUI history has no executed workflow mapping")
    return prompt_record[2], status_text


def _workflow_node(
    workflow: Mapping[str, Any],
    node_id: str,
) -> Mapping[str, Any]:
    node = workflow.get(node_id)
    if not isinstance(node, Mapping):
        raise ValueError(f"executed ComfyUI workflow is missing node {node_id}")
    return node


def _node_inputs(node: Mapping[str, Any]) -> Mapping[str, Any]:
    inputs = node.get("inputs")
    if not isinstance(inputs, Mapping):
        raise ValueError("executed ComfyUI node has no input mapping")
    return inputs


def _single_image_sampler(
    workflow: Mapping[str, Any],
) -> tuple[str, Mapping[str, Any]]:
    sampler_classes = {
        "KSampler",
        "KSamplerAdvanced",
        "SamplerCustom",
        "SamplerCustomAdvanced",
    }
    samplers = [
        (str(node_id), raw_node)
        for node_id, raw_node in workflow.items()
        if isinstance(raw_node, Mapping)
        and str(raw_node.get("class_type") or "") in sampler_classes
    ]
    if len(samplers) != 1:
        raise ValueError(
            "executed ComfyUI workflow must contain exactly one image sampler"
        )
    return samplers[0]


def _require_node_class(
    node: Mapping[str, Any],
    expected: str,
    label: str,
) -> None:
    if str(node.get("class_type") or "") != expected:
        raise ValueError(f"executed ComfyUI {label} node class changed")


def _linked_node_id(value: Any) -> str | None:
    if (
        isinstance(value, list)
        and len(value) == 2
        and isinstance(value[0], (str, int))
        and isinstance(value[1], int)
    ):
        return str(value[0])
    return None


def _actual_parameter(workflow: Mapping[str, Any], name: str) -> str:
    value = _actual_parameter_value(workflow, name)
    if not isinstance(value, str):
        raise ValueError(f"executed ComfyUI {name} parameter must be text")
    return value


def _actual_parameter_value(workflow: Mapping[str, Any], name: str) -> Any:
    marker = f"${name}."
    values: list[Any] = []
    for raw_node in workflow.values():
        if not isinstance(raw_node, Mapping):
            continue
        meta = raw_node.get("_meta")
        title = str(meta.get("title") or "") if isinstance(meta, Mapping) else ""
        if marker not in title:
            continue
        inputs = _node_inputs(raw_node)
        field = title.split(marker, 1)[1].split("!", 1)[0].strip()
        if field in inputs:
            values.append(inputs[field])
    if len(values) != 1:
        raise ValueError(
            f"executed ComfyUI workflow must expose exactly one {name} parameter"
        )
    return values[0]


def _actual_parameter_node_id(
    workflow: Mapping[str, Any],
    name: str,
) -> str:
    marker = f"${name}."
    node_ids: list[str] = []
    for node_id, raw_node in workflow.items():
        if not isinstance(raw_node, Mapping):
            continue
        meta = raw_node.get("_meta")
        title = str(meta.get("title") or "") if isinstance(meta, Mapping) else ""
        if marker not in title:
            continue
        inputs = _node_inputs(raw_node)
        field = title.split(marker, 1)[1].split("!", 1)[0].strip()
        if field in inputs:
            node_ids.append(str(node_id))
    if len(node_ids) != 1:
        raise ValueError(
            f"executed ComfyUI workflow must expose exactly one {name} parameter node"
        )
    return node_ids[0]


def _positive_actual_parameter(workflow: Mapping[str, Any], name: str) -> int:
    value = _actual_parameter_value(workflow, name)
    if isinstance(value, bool):
        raise ValueError(f"executed ComfyUI {name} parameter must be positive")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"executed ComfyUI {name} parameter must be positive"
        ) from exc
    if result <= 0:
        raise ValueError(f"executed ComfyUI {name} parameter must be positive")
    return result


def _actual_model_files(workflow: Mapping[str, Any]) -> list[str]:
    loader_classes = {
        "CheckpointLoaderSimple",
        "CLIPLoader",
        "CLIPLoaderGGUF",
        "DualCLIPLoader",
        "DualCLIPLoaderGGUF",
        "UNETLoader",
        "UnetLoaderGGUF",
        "VAELoader",
    }
    files: set[str] = set()
    for raw_node in workflow.values():
        if (
            not isinstance(raw_node, Mapping)
            or str(raw_node.get("class_type") or "") not in loader_classes
        ):
            continue
        for key, value in _node_inputs(raw_node).items():
            if str(key).endswith("_name") and isinstance(value, str) and value.strip():
                files.add(value.strip())
    if not files:
        raise ValueError("executed ComfyUI workflow has no model files")
    return sorted(files)


def _reference_conditioner_count(workflow: Mapping[str, Any]) -> int:
    return sum(
        1
        for node in workflow.values()
        if isinstance(node, Mapping)
        and str(node.get("class_type") or "") == "TextEncodeZImageOmni"
    )


async def _download_first_generated_image(
    *,
    session: aiohttp.ClientSession,
    base_url: str,
    workflow_result: Any,
) -> tuple[str, dict[str, str], bytes]:
    images = getattr(workflow_result, "images", None)
    if not isinstance(images, list) or len(images) != 1:
        raise ValueError(
            "visual-anchor first generation must return exactly one image output"
        )
    raw_url = str(images[0] or "").strip()
    if not raw_url:
        raise ValueError("visual-anchor first generation returned an empty image URL")
    resolved_url = urljoin(f"{base_url}/", raw_url)
    expected_origin = urlparse(base_url)
    actual_origin = urlparse(resolved_url)
    expected_view_path = f"{expected_origin.path.rstrip('/')}/view" or "/view"
    if (
        actual_origin.scheme != expected_origin.scheme
        or actual_origin.netloc != expected_origin.netloc
        or actual_origin.path != expected_view_path
    ):
        raise ValueError(
            "visual-anchor generated image URL escaped the local ComfyUI view endpoint"
        )
    query = parse_qs(actual_origin.query)
    filename = str((query.get("filename") or [""])[0]).strip()
    output_type = str((query.get("type") or [""])[0]).strip()
    if not filename or output_type != "output":
        raise ValueError(
            "visual-anchor first generation did not return a persisted output image"
        )
    async with session.get(resolved_url) as response:
        if response.status != 200:
            raise ValueError(
                "visual-anchor could not read the first generated image from ComfyUI"
            )
        payload = await response.read()
    if not payload:
        raise ValueError("visual-anchor first generated image is empty")
    return (
        hashlib.sha256(payload).hexdigest(),
        {
            "filename": filename,
            "subfolder": str((query.get("subfolder") or [""])[0]),
            "type": output_type,
        },
        payload,
    )


def _persist_first_generated_output(
    *,
    task_root: Path,
    frame_id: str,
    filename: str,
    payload: bytes,
    expected_sha256: str,
) -> str:
    if not task_root.is_dir():
        raise ValueError("visual-anchor task root does not exist")
    suffix = Path(filename).suffix.casefold()
    if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
        suffix = ".bin"
    output_dir = (
        task_root
        / "visual_anchor_generation"
        / _simple_safe_frame_id(frame_id)
    ).resolve()
    output_dir.relative_to(task_root)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = (output_dir / f"first_comfyui_output{suffix}").resolve()
    output_path.relative_to(output_dir)
    if output_path.is_file():
        if _file_sha256(output_path) != expected_sha256:
            raise ValueError(
                "visual-anchor captured first output conflicts with existing evidence"
            )
        return output_path.relative_to(task_root).as_posix()
    temporary_path = output_dir / f".tmp-output-{uuid4().hex[:12]}"
    try:
        with temporary_path.open("wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        if _file_sha256(temporary_path) != expected_sha256:
            raise ValueError("visual-anchor captured first output digest changed")
        os.replace(temporary_path, output_path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return output_path.relative_to(task_root).as_posix()


def _captured_first_output_artifacts(
    task_root: Path,
    frame_id: str,
) -> list[str]:
    output_dir = (
        task_root
        / "visual_anchor_generation"
        / _simple_safe_frame_id(frame_id)
    ).resolve()
    try:
        output_dir.relative_to(task_root)
    except ValueError:
        return []
    if not output_dir.is_dir():
        return []
    return sorted(
        path.relative_to(task_root).as_posix()
        for path in output_dir.glob("first_comfyui_output.*")
        if path.is_file() and not path.is_symlink()
    )


def _write_binding_audit(
    task_root: Path,
    frame_id: str,
    audit: Mapping[str, Any],
    *,
    require_new: bool = False,
) -> None:
    output_path = _binding_audit_path(task_root, frame_id)
    output_dir = output_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(dict(audit), ensure_ascii=False, indent=2) + "\n"
    if require_new:
        try:
            with output_path.open("x", encoding="utf-8", newline="\n") as handle:
                handle.write(serialized)
                handle.flush()
                os.fsync(handle.fileno())
        except FileExistsError as exc:
            raise ValueError(
                "visual-anchor first generation evidence already exists"
            ) from exc
        return
    temporary_path = output_dir / f".tmp-binding-{uuid4().hex[:12]}"
    try:
        with temporary_path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, output_path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _simple_safe_frame_id(frame_id: str) -> str:
    if not isinstance(frame_id, str) or not frame_id.strip():
        raise ValueError("visual-anchor frame id cannot be persisted safely")
    normalized = _SAFE_FRAME_ID_RE.sub("_", frame_id).strip("_") or "frame"
    digest = hashlib.sha256(frame_id.encode("utf-8")).hexdigest()[:12]
    return f"{normalized[:32].rstrip('_-') or 'frame'}-{digest}"


def _binding_audit_path(task_root: Path, frame_id: str) -> Path:
    output_path = (
        task_root
        / "visual_anchor_generation"
        / _simple_safe_frame_id(frame_id)
        / "first_request_binding.json"
    ).resolve()
    output_path.relative_to(task_root)
    return output_path


def visual_anchor_first_request_binding_artifact_relative_path(
    frame_id: str,
) -> str:
    return (
        "visual_anchor_generation/"
        f"{_simple_safe_frame_id(frame_id)}/first_request_binding.json"
    )


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_json_sha256(value: Mapping[str, Any]) -> str:
    payload = json.dumps(
        dict(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


__all__ = [
    "VISUAL_ANCHOR_GENERATION_REQUEST_PARAM",
    "record_visual_anchor_first_generation_failure",
    "validate_visual_anchor_first_generation_binding",
    "verify_visual_anchor_executed_workflow_binding",
    "visual_anchor_first_request_binding_artifact_relative_path",
]
