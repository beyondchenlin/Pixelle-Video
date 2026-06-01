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
import inspect
import json
from collections.abc import Mapping
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
from pixelle_video.runninghub_workflow_contracts import (
    ANALYSIS_WORKFLOW_DOMAINS,
    MEDIA_WORKFLOW_DOMAINS,
    runninghub_descriptor_domains,
    validate_runninghub_descriptor_contract,
)
from pixelle_video.services.alignment_service import AlignmentService
from pixelle_video.services.analysis_trace_artifacts import (
    validate_analysis_workflow_trace_artifact,
    write_analysis_workflow_result_artifact,
)
from pixelle_video.services.audio_edit_service import AudioEditService
from pixelle_video.services.comfyui_backend_manager import ManagedComfyUIBackend
from pixelle_video.services.comfyui_backend_registry import ComfyUIBackendRegistry
from pixelle_video.services.comfyui_errors import (
    looks_like_backend_connection_loss,
    looks_like_memory_exhaustion,
    looks_like_transient_backend_execution_error,
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
from pixelle_video.services.prompt_trace_artifacts import (
    build_workflow_params_trace,
    require_media_prompt_trace_context,
    summarize_media_workflow_result,
    validate_media_prompt_trace_artifact,
    write_media_workflow_result_artifact,
)
from pixelle_video.services.tts_service import TTSService
from pixelle_video.services.tts_trace_artifacts import (
    validate_tts_workflow_trace_artifact,
    write_tts_workflow_result_artifact,
)
from pixelle_video.services.video import VideoService
from pixelle_video.services.video_analysis import VideoAnalysisService
from pixelle_video.tts_workflow_contract import is_index_tts2_workflow_key
from pixelle_video.tts_workflow_family import (
    is_known_tts_workflow_resource,
    is_omnivoice_workflow_key,
)
from pixelle_video.tts_workflow_param_contract import (
    is_tts_workflow_param_name,
    workflow_params_have_case_variant_tts_key,
    workflow_params_look_like_tts_generation,
)
from pixelle_video.utils.os_util import get_output_path
from pixelle_video.workflow_content_contracts import (
    WORKFLOW_FILE_TRACE_KEYS,
    build_workflow_file_trace,
    extract_workflow_file_trace,
    load_workflow_json,
    workflow_content_contract,
    workflow_file_sha256,
)

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
_WORKFLOW_PROMPT_PARAM_KEYS = (
    "prompt",
    "positive_prompt",
    "image_prompt",
    "video_prompt",
    "text_prompt",
)
_WORKFLOW_WIDTH_PARAM_KEYS = ("width", "media_width", "image_width", "video_width")
_WORKFLOW_HEIGHT_PARAM_KEYS = ("height", "media_height", "image_height", "video_height")
_WORKFLOW_NEGATIVE_PROMPT_PARAM_KEYS = (
    "negative",
    "negative_prompt",
    "negative_image_prompt",
    "negative_video_prompt",
)
_MEDIA_PROMPT_TRACE_MEDIA_TYPES = MEDIA_WORKFLOW_DOMAINS
_MEDIA_PROMPT_TRACE_CONTROL_PARAM_KEYS = frozenset(
    {
        "batch_size",
        "cfg",
        "clip_skip",
        "denoise",
        "duration",
        "fps",
        "frame_count",
        "frame_rate",
        "frames",
        "guidance",
        "guidance_scale",
        "motion_bucket_id",
        "noise_aug_strength",
        "num_frames",
        "sampler",
        "sampler_name",
        "scheduler",
        "second",
        "seconds",
        "seed",
        "steps",
        "strength",
        "height",
        "media_height",
        "media_width",
        "width",
    }
)
_MEDIA_PROMPT_TRACE_INPUT_PARAM_KEYS = frozenset(
    {
        "audio",
        "image",
        "media",
        "ref_audio",
        "reference_audio",
        "reference_image",
        "source_image",
        "target_image",
        "video",
    }
)
_MEDIA_PROMPT_TRACE_VISUAL_INPUT_PARAM_KEYS = frozenset(
    {
        "image",
        "media",
        "reference_image",
        "source_image",
        "target_image",
        "video",
    }
)
_MEDIA_PROMPT_TRACE_VISUAL_INPUT_PARAM_SUFFIXES = (
    "image",
    "media",
    "video",
)
_ANALYSIS_WORKFLOW_DOMAINS = ANALYSIS_WORKFLOW_DOMAINS
_ANALYSIS_PROMPT_PARAM_KEYS = frozenset(
    {
        "caption",
        "instruction",
        "instructions",
        "prompt",
        "question",
        "query",
        "text",
        *_WORKFLOW_PROMPT_PARAM_KEYS,
        *_WORKFLOW_NEGATIVE_PROMPT_PARAM_KEYS,
    }
)
_ANALYSIS_PROMPT_PARAM_SUFFIXES = (
    "_caption",
    "_instruction",
    "_instructions",
    "_prompt",
    "_prompt_text",
    "_query",
    "_question",
    "_question_text",
)
_ANALYSIS_PROMPT_PARAM_PREFIXES = (
    "caption_",
    "instruction_",
    "instructions_",
    "prompt_",
    "query_",
    "question_",
)
_ANALYSIS_ALLOWED_INPUT_PARAM_KEYS = frozenset(
    {
        "file",
        "image",
        "image_path",
        "input",
        "input_file",
        "input_image",
        "input_media",
        "input_path",
        "input_url",
        "input_video",
        "media",
        "media_path",
        "path",
        "source_image",
        "source_media",
        "source_video",
        "url",
        "video",
        "video_path",
    }
)
_ANALYSIS_ALLOWED_INPUT_PARAM_SUFFIXES = (
    "_file",
    "_image",
    "_media",
    "_path",
    "_url",
    "_video",
)
_MEDIA_PROMPT_TRACE_INPUT_PARAM_SUFFIXES = (
    "audio",
    "file",
    "image",
    "media",
    "path",
    "url",
    "video",
)


def _workflow_param_value(
    workflow_params: Mapping[str, Any],
    keys: tuple[str, ...],
) -> Any:
    normalized_keys = {key.lower() for key in keys}
    for key, value in workflow_params.items():
        if str(key or "").strip().lower() in normalized_keys:
            return value
    return None


def _extract_prompt_from_workflow_params(workflow_params: Mapping[str, Any]) -> str:
    for key in _WORKFLOW_PROMPT_PARAM_KEYS:
        value = _workflow_param_value(workflow_params, (key,))
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _extract_negative_prompt_from_workflow_params(
    workflow_params: Mapping[str, Any],
) -> str:
    values: list[str] = []
    for key in _WORKFLOW_NEGATIVE_PROMPT_PARAM_KEYS:
        value = _workflow_param_value(workflow_params, (key,))
        if isinstance(value, str) and value.strip():
            values.append(value.strip())
    if len(set(values)) > 1:
        raise ValueError(
            "media_prompt_trace_context workflow negative prompt alias does not match negative prompt"
        )
    if values:
        return values[0]
    return ""


def _extract_int_from_workflow_params(
    workflow_params: Mapping[str, Any],
    keys: tuple[str, ...],
) -> int | None:
    for key in keys:
        value = _workflow_param_value(workflow_params, (key,))
        if value is None or str(value).strip() == "":
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


def _workflow_input_looks_like_media_generation(workflow_input: Any) -> bool:
    if isinstance(workflow_input, Mapping):
        return False
    normalized = str(workflow_input or "").replace("\\", "/").strip().lower()
    if not normalized:
        return False
    filename = normalized.rsplit("/", 1)[-1]
    return (
        filename.startswith(("image_", "video_"))
        or "/image_" in normalized
        or "/video_" in normalized
    )


def _workflow_identifier_looks_like_analysis(workflow_identifier: Any) -> bool:
    if isinstance(workflow_identifier, Mapping):
        return False
    normalized = str(workflow_identifier or "").replace("\\", "/").strip().lower()
    if not normalized:
        return False
    filename = normalized.rsplit("/", 1)[-1]
    return (
        filename.startswith(("analyse_", "analyze_", "analysis_"))
        or filename.startswith(("image_analysis", "video_analysis"))
        or filename.startswith(("image_understanding", "video_understanding"))
        or "/analyse_" in normalized
        or "/analyze_" in normalized
        or "/analysis_" in normalized
        or "/image_understanding" in normalized
        or "/video_understanding" in normalized
    )


def _workflow_identifier_looks_like_non_media_generation(
    workflow_identifier: Any,
) -> bool:
    return is_known_tts_workflow_resource(workflow_identifier)


def _workflow_identifier_looks_like_workflow_resource(
    workflow_identifier: Any,
) -> bool:
    if isinstance(workflow_identifier, Mapping):
        return False
    normalized = str(workflow_identifier or "").replace("\\", "/").strip().lower()
    if not normalized:
        return False
    return (
        normalized.startswith(("workflows/", "selfhost/", "runninghub/", "custom/"))
        or "/workflows/" in normalized
    )


def _workflow_identifier_looks_like_raw_workflow_compatibility_name(
    workflow_identifier: Any,
) -> bool:
    if isinstance(workflow_identifier, Mapping):
        return False
    return str(workflow_identifier or "").replace("\\", "/").strip().lower() == "workflow.json"


def _raw_workflow_compatibility_boundary_applies(
    workflow_input: Any,
    *,
    workflow_source: str,
    resolved_workflow: str | None,
    workflow_file_boundary: bool,
) -> bool:
    if workflow_file_boundary:
        return False
    if str(workflow_source or "selfhost").strip().lower() != "selfhost":
        return False
    if not _workflow_identifier_looks_like_raw_workflow_compatibility_name(workflow_input):
        return False
    return True


def _enforce_raw_workflow_compatibility_boundary(
    workflow_input: Any,
    workflow_params: Mapping[str, Any],
    *,
    workflow_source: str,
    resolved_workflow: str | None,
    workflow_file_boundary: bool,
) -> None:
    if not _raw_workflow_compatibility_boundary_applies(
        workflow_input,
        workflow_source=workflow_source,
        resolved_workflow=resolved_workflow,
        workflow_file_boundary=workflow_file_boundary,
    ):
        return
    raise ValueError(
        "raw workflow.json is not allowed through public ComfyKit execution; "
        "use a resolved workflow path or execute_comfykit_workflow_file"
    )


def _workflow_params_have_media_inputs_or_controls(
    workflow_params: Mapping[str, Any],
) -> bool:
    for key, value in workflow_params.items():
        name = str(key or "").strip().lower()
        if not name or value in (None, "", [], {}):
            continue
        if name in _MEDIA_PROMPT_TRACE_CONTROL_PARAM_KEYS:
            return True
        if name in _MEDIA_PROMPT_TRACE_INPUT_PARAM_KEYS:
            return True
        if name.endswith(_MEDIA_PROMPT_TRACE_INPUT_PARAM_SUFFIXES):
            return True
    return False


def _workflow_params_have_traceable_payload(
    workflow_params: Mapping[str, Any],
) -> bool:
    prompt = _extract_prompt_from_workflow_params(workflow_params)
    return bool(build_workflow_params_trace(workflow_params, prompt=prompt or None))


def _workflow_params_have_visual_media_payload(
    workflow_params: Mapping[str, Any],
    *,
    prompt_is_text_input: bool = False,
) -> bool:
    prompt_keys = {key.lower() for key in _WORKFLOW_PROMPT_PARAM_KEYS}
    negative_prompt_keys = {
        key.lower() for key in _WORKFLOW_NEGATIVE_PROMPT_PARAM_KEYS
    }
    dimension_keys = {
        *[key.lower() for key in _WORKFLOW_WIDTH_PARAM_KEYS],
        *[key.lower() for key in _WORKFLOW_HEIGHT_PARAM_KEYS],
    }
    for key, value in workflow_params.items():
        raw_name = str(key or "").strip()
        name = raw_name.lower()
        if not raw_name or value in (None, "", [], {}):
            continue
        if name in prompt_keys:
            if prompt_is_text_input and raw_name == "prompt":
                continue
            return True
        if name in negative_prompt_keys:
            return True
        if name in dimension_keys:
            return True
        if name in _MEDIA_PROMPT_TRACE_VISUAL_INPUT_PARAM_KEYS:
            return True
        if name.endswith(_MEDIA_PROMPT_TRACE_VISUAL_INPUT_PARAM_SUFFIXES):
            return True
    return False


def _workflow_params_have_negative_prompt_payload(
    workflow_params: Mapping[str, Any],
) -> bool:
    negative_prompt_keys = {
        key.lower() for key in _WORKFLOW_NEGATIVE_PROMPT_PARAM_KEYS
    }
    return any(
        str(key or "").strip().lower() in negative_prompt_keys
        and isinstance(value, str)
        and bool(value.strip())
        for key, value in workflow_params.items()
    )


def _workflow_params_look_like_non_media_generation(
    workflow_params: Mapping[str, Any],
) -> bool:
    return workflow_params_look_like_tts_generation(workflow_params)


def _workflow_params_have_tts_signal(
    workflow_params: Mapping[str, Any],
) -> bool:
    has_text_input = False
    has_only_tts_params = True
    for key, value in workflow_params.items():
        name = str(key or "").strip()
        if not name or value in (None, "", [], {}):
            continue
        normalized = name.lower()
        if not is_tts_workflow_param_name(name):
            has_only_tts_params = False
            continue
        if normalized in {"prompt", "prompt_text", "text"}:
            has_text_input = True
    return has_only_tts_params and has_text_input


def _workflow_params_have_case_variant_non_media_key(
    workflow_params: Mapping[str, Any],
) -> bool:
    return workflow_params_have_case_variant_tts_key(workflow_params)


def _enforce_known_non_media_workflow_param_case_boundary(
    workflow_input: Any,
    workflow_params: Mapping[str, Any],
    *,
    resolved_workflow: str | None,
) -> None:
    if not (
        _workflow_identifier_looks_like_non_media_generation(workflow_input)
        or _workflow_identifier_looks_like_non_media_generation(resolved_workflow)
    ):
        return
    if _workflow_params_have_case_variant_non_media_key(workflow_params):
        raise ValueError(
            "non-media workflow params must use exact lowercase keys"
        )


def _workflow_params_have_case_variant_prompt_key(
    workflow_params: Mapping[str, Any],
) -> bool:
    prompt_keys = {key.lower() for key in _WORKFLOW_PROMPT_PARAM_KEYS}
    for key, value in workflow_params.items():
        name = str(key or "").strip()
        if (
            name
            and name.lower() in prompt_keys
            and name != name.lower()
            and isinstance(value, str)
            and value.strip()
        ):
            return True
    return False


def _comfykit_workflow_requires_media_prompt_trace(
    workflow_input: Any,
    workflow_params: Mapping[str, Any],
    *,
    workflow_source: str,
    media_type: str | None = None,
    resolved_workflow: str | None = None,
    workflow_file_boundary: bool = False,
) -> bool:
    resolved_media_type = str(media_type or "").strip().lower()
    if resolved_media_type in _MEDIA_PROMPT_TRACE_MEDIA_TYPES:
        return True

    normalized_source = str(workflow_source or "selfhost").strip().lower()
    known_non_media_workflow = (
        _workflow_identifier_looks_like_non_media_generation(workflow_input)
        or _workflow_identifier_looks_like_non_media_generation(resolved_workflow)
    )
    has_visual_media_payload = _workflow_params_have_visual_media_payload(
        workflow_params,
        prompt_is_text_input=known_non_media_workflow,
    )
    prompt = _extract_prompt_from_workflow_params(workflow_params)
    traceable_payload = _workflow_params_have_traceable_payload(workflow_params)
    has_case_variant_prompt = _workflow_params_have_case_variant_prompt_key(
        workflow_params
    )
    has_negative_prompt_payload = _workflow_params_have_negative_prompt_payload(
        workflow_params
    )
    has_media_inputs_or_controls = _workflow_params_have_media_inputs_or_controls(
        workflow_params
    )
    non_media_workflow = (
        known_non_media_workflow
        and not has_visual_media_payload
    )
    if non_media_workflow:
        return False

    if prompt:
        return True

    if normalized_source == "runninghub" and (
        prompt or traceable_payload or has_media_inputs_or_controls
    ):
        return True
    if _workflow_input_looks_like_media_generation(
        workflow_input
    ) or _workflow_input_looks_like_media_generation(resolved_workflow):
        return bool(prompt or traceable_payload or has_media_inputs_or_controls)
    if has_case_variant_prompt:
        return True
    if has_negative_prompt_payload:
        return True
    if has_media_inputs_or_controls:
        return True
    if traceable_payload:
        return True
    return False


def _infer_media_type_from_workflow_input(workflow_input: Any) -> str:
    normalized = str(workflow_input or "").replace("\\", "/").strip().lower()
    filename = normalized.rsplit("/", 1)[-1]
    if filename.startswith("video_") or "/video_" in normalized:
        return "video"
    if filename.startswith("image_") or "/image_" in normalized:
        return "image"
    return ""


def _workflow_domain_requests_analysis(workflow_domain: str | None) -> bool:
    return str(workflow_domain or "").strip().lower() in _ANALYSIS_WORKFLOW_DOMAINS


def _workflow_boundary_is_analysis(
    *,
    workflow_input: Any,
    resolved_workflow: str | None,
    workflow_domain: str | None,
    analysis_service_domain: str | None,
) -> bool:
    recognized_analysis_workflow = (
        _workflow_identifier_looks_like_analysis(workflow_input)
        or _workflow_identifier_looks_like_analysis(resolved_workflow)
    )
    if not _workflow_domain_requests_analysis(workflow_domain):
        return False
    if str(analysis_service_domain or "").strip().lower() not in {
        "image_analysis",
        "video_analysis",
    }:
        raise ValueError(
            "workflow_domain analysis requires a resolved analysis service workflow"
        )
    if not recognized_analysis_workflow:
        raise ValueError(
            "workflow_domain analysis requires a resolved analysis workflow"
        )
    return True


def _workflow_identifier_requires_analysis_boundary(
    workflow_input: Any,
    resolved_workflow: str | None,
) -> bool:
    return (
        _workflow_identifier_looks_like_analysis(workflow_input)
        or _workflow_identifier_looks_like_analysis(resolved_workflow)
    )


def _analysis_media_type_for_service_domain(service_domain: str | None) -> str:
    normalized = str(service_domain or "").strip().lower()
    if normalized == "image_analysis":
        return "image"
    if normalized == "video_analysis":
        return "video"
    return ""


def _extract_analysis_media_path(
    workflow_params: Mapping[str, Any],
    *,
    service_domain: str | None,
) -> str:
    media_type = _analysis_media_type_for_service_domain(service_domain)
    if media_type == "image":
        value = _workflow_param_value(workflow_params, ("image", "media", "path", "url"))
    elif media_type == "video":
        value = _workflow_param_value(workflow_params, ("video", "media", "path", "url"))
    else:
        value = None
    return str(value or "").strip()


def _analysis_param_name_is_prompt_like(name: str) -> bool:
    normalized = str(name or "").strip().lower()
    if not normalized:
        return False
    return (
        normalized in _ANALYSIS_PROMPT_PARAM_KEYS
        or normalized.endswith(_ANALYSIS_PROMPT_PARAM_SUFFIXES)
        or normalized.startswith(_ANALYSIS_PROMPT_PARAM_PREFIXES)
    )


def _analysis_param_name_is_allowed_input(name: str) -> bool:
    normalized = str(name or "").strip().lower()
    if not normalized:
        return False
    return normalized in _ANALYSIS_ALLOWED_INPUT_PARAM_KEYS or normalized.endswith(
        _ANALYSIS_ALLOWED_INPUT_PARAM_SUFFIXES
    )


def _existing_selfhost_workflow_content_contract(workflow_input: Any) -> dict[str, Any]:
    if isinstance(workflow_input, Mapping):
        return {}
    try:
        workflow_path = Path(str(workflow_input))
    except (TypeError, ValueError):
        return {}
    if not workflow_path.is_file():
        return {}
    try:
        workflow = load_workflow_json(workflow_path)
    except Exception:
        return {}
    if str(workflow.get("source") or "selfhost").strip().lower() == "runninghub":
        return {}
    return workflow_content_contract(workflow)


def _enforce_selfhost_workflow_content_boundary(
    *,
    workflow_input: Any,
    workflow_domain: str | None,
    media_workflow_contract: str | None,
    media_prompt_trace_context: Mapping[str, Any] | None,
    tts_workflow_trace_context: Mapping[str, Any] | None,
    analysis_workflow_trace_context: Mapping[str, Any] | None,
) -> None:
    content_contract = _existing_selfhost_workflow_content_contract(workflow_input)
    if not content_contract:
        return
    if content_contract.get("contains_tts_nodes") and str(
        media_workflow_contract or ""
    ).strip().lower() in _MEDIA_PROMPT_TRACE_MEDIA_TYPES:
        raise ValueError(
            "selfhost workflow content resolves to TTS nodes and cannot execute "
            "through a media workflow contract"
        )
    if (
        content_contract.get("contains_analysis_nodes")
        and not _workflow_domain_requests_analysis(workflow_domain)
    ):
        raise ValueError(
            "analysis workflow execution requires a resolved analysis service workflow"
        )
    _require_workflow_prompt_literal_trace(
        workflow_contract=content_contract,
        trace_contexts=(
            media_prompt_trace_context,
            tts_workflow_trace_context,
            analysis_workflow_trace_context,
        ),
    )


def _require_workflow_prompt_literal_trace(
    *,
    workflow_contract: Mapping[str, Any],
    trace_contexts: tuple[Mapping[str, Any] | None, ...],
) -> None:
    prompt_literals = workflow_contract.get("prompt_literals")
    if not prompt_literals:
        return
    expected_sha256 = str(workflow_contract.get("prompt_literals_sha256") or "").strip()
    if not expected_sha256:
        raise ValueError("workflow prompt literals require a workflow literal hash")
    active_contexts = [
        context for context in trace_contexts if isinstance(context, Mapping)
    ]
    if not active_contexts:
        raise ValueError(
            "workflow prompt literals require a prompt trace context "
            "(media_prompt_trace_context, tts_workflow_trace_context, or "
            "analysis_workflow_trace_context) before workflow execution"
        )
    traced_hashes = [
        str(context.get("workflow_prompt_literals_sha256") or "").strip()
        for context in active_contexts
    ]
    if not any(traced_hashes):
        raise ValueError(
            "workflow prompt literals require workflow_prompt_literals_sha256 in the "
            "prompt trace context"
        )
    if expected_sha256 not in traced_hashes:
        raise ValueError(
            "prompt trace context workflow prompt literal hash does not match"
        )


def _workflow_file_trace_from_identity(
    workflow_identity: Mapping[str, Any],
) -> dict[str, Any]:
    workflow_file_sha = str(
        workflow_identity.get("workflow_file_sha256") or ""
    ).strip()
    workflow_contract = workflow_identity.get("workflow_content_contract")
    if not workflow_file_sha or not isinstance(workflow_contract, Mapping):
        return {}
    return {
        "workflow_file_sha256": workflow_file_sha,
        "workflow_prompt_literals": list(workflow_contract.get("prompt_literals") or []),
        "workflow_prompt_literals_sha256": str(
            workflow_contract.get("prompt_literals_sha256") or ""
        ),
    }


def _workflow_file_trace_from_execution_request(
    *,
    workflow_input: Any,
    resolved_workflow: str | None,
    workflow_file_trace: Mapping[str, Any] | None,
    trusted_workflow_file_trace: bool = False,
) -> dict[str, Any]:
    canonical_trace = build_workflow_file_trace(
        str(resolved_workflow or ""),
        str(workflow_input or ""),
    )
    explicit_trace = _complete_workflow_file_trace(workflow_file_trace)
    if canonical_trace and explicit_trace and explicit_trace != canonical_trace:
        raise ValueError("workflow file trace does not match resolved workflow file")
    if canonical_trace:
        return canonical_trace
    if explicit_trace and trusted_workflow_file_trace:
        return explicit_trace
    if explicit_trace:
        raise ValueError("workflow file trace cannot be verified against resolved workflow file")
    return {}


def _complete_workflow_file_trace(
    workflow_file_trace: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(workflow_file_trace, Mapping) or not workflow_file_trace:
        return {}
    extracted = extract_workflow_file_trace(workflow_file_trace)
    missing = [key for key in WORKFLOW_FILE_TRACE_KEYS if key not in extracted]
    if missing:
        raise ValueError("workflow file trace is incomplete")
    if not str(extracted.get("workflow_file_sha256") or "").strip():
        raise ValueError("workflow file trace is incomplete")
    if not isinstance(extracted.get("workflow_prompt_literals"), list):
        raise ValueError("workflow file trace is incomplete")
    if not str(extracted.get("workflow_prompt_literals_sha256") or "").strip():
        raise ValueError("workflow file trace is incomplete")
    return extracted


def _execution_requires_workflow_file_trace(
    *,
    media_prompt_trace_context: Mapping[str, Any] | None,
    tts_workflow_trace_context: Mapping[str, Any] | None,
    analysis_workflow_trace_context: Mapping[str, Any] | None,
    media_workflow_contract: str | None,
    tts_workflow_contract: str | None,
    tts_service_domain: str | None,
    analysis_service_domain: str | None,
) -> bool:
    has_trace_context = any(
        isinstance(context, Mapping)
        for context in (
            media_prompt_trace_context,
            tts_workflow_trace_context,
            analysis_workflow_trace_context,
        )
    )
    if not has_trace_context:
        return False
    media_contract = str(media_workflow_contract or "").strip().lower()
    if media_contract in _MEDIA_PROMPT_TRACE_MEDIA_TYPES:
        return True
    if str(tts_workflow_contract or "").strip():
        return True
    if str(tts_service_domain or "").strip().lower() == "tts":
        return True
    return str(analysis_service_domain or "").strip().lower() in {
        "image_analysis",
        "video_analysis",
    }


def _validate_analysis_workflow_boundary(
    workflow_params: Mapping[str, Any],
) -> None:
    for key, value in workflow_params.items():
        name = str(key or "").strip()
        if not name or value in (None, "", [], {}):
            continue
        if _analysis_param_name_is_prompt_like(name):
            raise ValueError(
                "analysis_prompt_trace_context is required before analysis workflow prompt execution"
            )
        if not _analysis_param_name_is_allowed_input(name):
            raise ValueError(
                "analysis workflow params are restricted to media inputs without analysis prompt trace"
            )


def _validate_comfykit_analysis_trace_boundary(
    *,
    workflow_input: Any,
    workflow_params: Mapping[str, Any],
    analysis_workflow_trace_context: Mapping[str, Any] | None,
    workflow_domain: str | None,
    analysis_service_domain: str | None,
    resolved_workflow: str | None,
    workflow_file_trace: Mapping[str, Any] | None = None,
) -> Mapping[str, Any] | None:
    if not isinstance(workflow_params, Mapping):
        return None
    if not _workflow_boundary_is_analysis(
        workflow_input=workflow_input,
        resolved_workflow=resolved_workflow,
        workflow_domain=workflow_domain,
        analysis_service_domain=analysis_service_domain,
    ):
        return None
    _validate_analysis_workflow_boundary(workflow_params)
    media_type = _analysis_media_type_for_service_domain(analysis_service_domain)
    media_path = _extract_analysis_media_path(
        workflow_params,
        service_domain=analysis_service_domain,
    )
    if not media_type or not media_path:
        raise ValueError(
            "analysis_workflow_trace_context media input is required before analysis workflow execution"
        )
    return validate_analysis_workflow_trace_artifact(
        analysis_workflow_trace_context,
        media_path=media_path,
        media_type=media_type,
        workflow=str(resolved_workflow or workflow_input),
        workflow_input=str(workflow_input),
        service_domain=str(analysis_service_domain or ""),
        workflow_params=workflow_params,
        workflow_file_trace=workflow_file_trace,
    )


def _extract_tts_text_from_workflow_params(
    workflow_params: Mapping[str, Any],
) -> str:
    for key in ("text", "prompt"):
        if key not in workflow_params:
            continue
        value = workflow_params.get(key)
        if value is None:
            continue
        text = str(value)
        if text.strip():
            return text
    return ""


def _summarize_tts_workflow_result(result: Any) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "status": str(getattr(result, "status", "")),
        "msg": str(getattr(result, "msg", "") or ""),
        "audios": [str(value) for value in getattr(result, "audios", []) or []],
        "files": [str(value) for value in getattr(result, "files", []) or []],
    }
    outputs = getattr(result, "outputs", {}) or {}
    if isinstance(outputs, Mapping):
        summary["outputs"] = {
            str(key): str(value)
            for key, value in outputs.items()
        }
    else:
        summary["outputs"] = {}
    return summary


def _summarize_analysis_workflow_result(result: Any) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "status": str(getattr(result, "status", "")),
        "msg": str(getattr(result, "msg", "") or ""),
        "texts": [str(value) for value in getattr(result, "texts", []) or []],
        "files": [str(value) for value in getattr(result, "files", []) or []],
    }
    outputs = getattr(result, "outputs", {}) or {}
    if isinstance(outputs, Mapping):
        summary["outputs"] = {
            str(key): value
            for key, value in outputs.items()
        }
    else:
        summary["outputs"] = {}
    return summary


def _local_comfykit_result_status(result: Any) -> str:
    if isinstance(result, Mapping):
        status = result.get("status")
    else:
        status = getattr(result, "status", "")
    return str(status or "").strip().lower()


def _local_comfykit_result_message(result: Any) -> str:
    if isinstance(result, Mapping):
        message = result.get("msg") or result.get("error")
        nested_result = result.get("result")
    else:
        message = getattr(result, "msg", "") or getattr(result, "error", "")
        nested_result = getattr(result, "result", None)
    if message:
        return str(message)
    if isinstance(nested_result, Mapping):
        return str(nested_result.get("msg") or nested_result.get("error") or "")
    return ""


def _local_comfykit_result_needs_transient_backend_retry(result: Any) -> bool:
    status = _local_comfykit_result_status(result)
    if not status or status == "completed":
        return False
    return looks_like_transient_backend_execution_error(
        _local_comfykit_result_message(result)
    )


def _comfykit_workflow_requires_tts_trace(
    workflow_input: Any,
    workflow_params: Mapping[str, Any],
    *,
    workflow_source: str,
    tts_workflow_contract: str | None = None,
    media_workflow_contract: str | None = None,
) -> bool:
    if str(media_workflow_contract or "").strip().lower() in _MEDIA_PROMPT_TRACE_MEDIA_TYPES:
        return False
    known_tts_workflow = (
        _workflow_identifier_looks_like_non_media_generation(workflow_input)
        or _workflow_identifier_looks_like_non_media_generation(tts_workflow_contract)
    )
    has_tts_signal = _workflow_params_have_tts_signal(workflow_params)
    if not known_tts_workflow and not has_tts_signal:
        return False
    if known_tts_workflow:
        return True
    if _workflow_params_have_visual_media_payload(
        workflow_params,
        prompt_is_text_input=True,
    ):
        return False
    return str(workflow_source or "").strip().lower() == "runninghub"


def _runninghub_boundary_is_known_non_media(
    *,
    workflow_input: Any,
    tts_workflow_contract: str | None,
    workflow_domain: str | None,
) -> bool:
    has_trusted_tts_contract = _workflow_identifier_looks_like_non_media_generation(
        tts_workflow_contract
    )
    if str(workflow_domain or "").strip().lower() == "tts":
        return has_trusted_tts_contract
    return (
        _workflow_identifier_looks_like_non_media_generation(workflow_input)
        or has_trusted_tts_contract
    )


def _validate_comfykit_tts_trace_boundary(
    *,
    workflow_input: Any,
    workflow_params: Mapping[str, Any],
    workflow_source: str,
    tts_workflow_trace_context: Mapping[str, Any] | None,
    tts_workflow_contract: str | None,
    media_workflow_contract: str | None = None,
    workflow_file_trace: Mapping[str, Any] | None = None,
) -> Mapping[str, Any] | None:
    if not isinstance(workflow_params, Mapping):
        return None
    _enforce_known_non_media_workflow_param_case_boundary(
        workflow_input,
        workflow_params,
        resolved_workflow=tts_workflow_contract,
    )
    if not _comfykit_workflow_requires_tts_trace(
        workflow_input,
        workflow_params,
        workflow_source=workflow_source,
        tts_workflow_contract=tts_workflow_contract,
        media_workflow_contract=media_workflow_contract,
    ):
        return None
    if not isinstance(tts_workflow_trace_context, Mapping):
        raise ValueError(
            "tts_workflow_trace_context is required before TTS workflow execution"
        )
    trace_text = _extract_tts_text_from_workflow_params(workflow_params)
    if not trace_text:
        trace_text = str(tts_workflow_trace_context.get("text") or "")
    return validate_tts_workflow_trace_artifact(
        tts_workflow_trace_context,
        text=trace_text,
        workflow=str(tts_workflow_contract or workflow_input),
        workflow_input=str(workflow_input),
        workflow_params=workflow_params,
        workflow_file_trace=workflow_file_trace,
    )


def _validate_comfykit_media_prompt_trace_boundary(
    *,
    workflow_input: Any,
    workflow_params: Mapping[str, Any],
    workflow_source: str,
    media_prompt_trace_context: Mapping[str, Any] | None,
    media_type: str | None,
    resolved_workflow: str | None,
    media_workflow_contract: str | None = None,
    tts_workflow_contract: str | None = None,
    workflow_domain: str | None = None,
    analysis_service_domain: str | None = None,
    workflow_file_boundary: bool = False,
    workflow_file_trace: Mapping[str, Any] | None = None,
) -> Mapping[str, Any] | None:
    if not isinstance(workflow_params, Mapping):
        return None

    _enforce_raw_workflow_compatibility_boundary(
        workflow_input,
        workflow_params,
        workflow_source=workflow_source,
        resolved_workflow=resolved_workflow,
        workflow_file_boundary=workflow_file_boundary,
    )
    _enforce_known_non_media_workflow_param_case_boundary(
        workflow_input,
        workflow_params,
        resolved_workflow=resolved_workflow,
    )
    if (
        _workflow_identifier_requires_analysis_boundary(workflow_input, resolved_workflow)
        and not _workflow_domain_requests_analysis(workflow_domain)
    ):
        raise ValueError(
            "analysis workflow execution requires a resolved analysis service workflow"
        )
    if _workflow_boundary_is_analysis(
        workflow_input=workflow_input,
        resolved_workflow=resolved_workflow,
        workflow_domain=workflow_domain,
        analysis_service_domain=analysis_service_domain,
    ):
        _validate_analysis_workflow_boundary(workflow_params)
        return None
    trusted_media_type = str(media_workflow_contract or "").strip().lower()
    if trusted_media_type and trusted_media_type not in _MEDIA_PROMPT_TRACE_MEDIA_TYPES:
        raise ValueError(
            "media workflow contract must be image or video before media workflow execution"
        )
    requested_media_type = str(media_type or "").strip().lower()
    if trusted_media_type and requested_media_type and requested_media_type != trusted_media_type:
        raise ValueError(
            "media_type does not match resolved media workflow contract"
        )
    effective_media_type = trusted_media_type or requested_media_type or None
    requires_trace = _comfykit_workflow_requires_media_prompt_trace(
        workflow_input,
        workflow_params,
        workflow_source=workflow_source,
        media_type=effective_media_type,
        resolved_workflow=resolved_workflow,
        workflow_file_boundary=workflow_file_boundary,
    )
    if (
        str(workflow_source or "").strip().lower() == "runninghub"
        and not trusted_media_type
        and not _runninghub_boundary_is_known_non_media(
            workflow_input=workflow_input,
            tts_workflow_contract=tts_workflow_contract,
            workflow_domain=workflow_domain,
        )
    ):
        if not requires_trace:
            raise ValueError(
                "RunningHub workflow execution requires an explicit service workflow contract"
            )
        raise ValueError(
            "RunningHub media workflow execution requires an explicit media workflow contract"
        )
    if not isinstance(media_prompt_trace_context, Mapping):
        if requires_trace:
            raise ValueError(
                "media_prompt_trace_context is required before media workflow execution"
            )
        return None

    trace_prompt = _extract_prompt_from_workflow_params(workflow_params)
    if not trace_prompt:
        trace_prompt = str(media_prompt_trace_context.get("prompt") or "").strip()
    if not trace_prompt:
        raise ValueError(
            "media_prompt_trace_context prompt is required before media workflow execution"
        )

    resolved_media_type = (
        str(effective_media_type or "").strip()
        or str(media_prompt_trace_context.get("media_type") or "").strip()
        or _infer_media_type_from_workflow_input(workflow_input)
    )
    if resolved_media_type not in _MEDIA_PROMPT_TRACE_MEDIA_TYPES:
        raise ValueError(
            "media_type is required before media workflow execution"
        )

    media_width = _extract_int_from_workflow_params(
        workflow_params,
        _WORKFLOW_WIDTH_PARAM_KEYS,
    )
    media_height = _extract_int_from_workflow_params(
        workflow_params,
        _WORKFLOW_HEIGHT_PARAM_KEYS,
    )
    negative_prompt = _extract_negative_prompt_from_workflow_params(workflow_params)
    workflow_param_trace = build_workflow_params_trace(
        workflow_params,
        prompt=trace_prompt,
    )
    trace_context = require_media_prompt_trace_context(
        media_prompt_trace_context,
        prompt=trace_prompt,
        media_type=resolved_media_type,
        width=media_width,
        height=media_height,
        negative_prompt=negative_prompt,
    )
    resolved_workflow_input = str(workflow_input)
    validate_media_prompt_trace_artifact(
        trace_context,
        prompt=trace_prompt,
        resolved_workflow=str(resolved_workflow or resolved_workflow_input),
        resolved_workflow_input=resolved_workflow_input,
        media_type=resolved_media_type,
        width=media_width,
        height=media_height,
        negative_prompt=negative_prompt,
        workflow_param_trace=workflow_param_trace,
        workflow_file_trace=workflow_file_trace,
    )
    return trace_context


class _LocalComfyUIWorkflowSession:
    def __init__(
        self,
        *,
        backend_role: str,
        release_after_session: bool = False,
        missing_endpoint: str = "required",
    ) -> None:
        self.backend_role = backend_role
        self.init_lock = asyncio.Lock()
        self.execute_lock = asyncio.Lock()
        self.lock_acquired = False
        self.prepared = False
        self.used_extensions: set[ComfyUIExtensionName] = set()
        self.preflighted_extensions: set[ComfyUIExtensionName] = set()
        self.release_after_session = release_after_session
        self.missing_endpoint = missing_endpoint


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
        # Media calls require a saved prompt trace context; use API/pipeline helpers
        # unless you have already written the final prompt artifact.
        
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
        self._comfykit_close_timeout_seconds = 5.0
        
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
        self._local_comfyui_accelerator_lock = asyncio.Lock()
        self._local_comfyui_accelerator_lock_depth: ContextVar[int] = ContextVar(
            "local_comfyui_accelerator_lock_depth",
            default=0,
        )
        self._comfyui_restart_tasks: dict[str, asyncio.Task[bool]] = {}
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

    async def _acquire_local_comfyui_accelerator_lock(
        self,
        *,
        backend_role: str,
        reason: str,
    ) -> tuple[bool, object]:
        depth = self._local_comfyui_accelerator_lock_depth.get()
        if depth > 0:
            token = self._local_comfyui_accelerator_lock_depth.set(depth + 1)
            return False, token

        role = self._normalize_comfyui_backend_role(backend_role)
        logger.debug(
            f"Waiting for local ComfyUI accelerator operation lock "
            f"(role={role}, reason={reason})"
        )
        await self._local_comfyui_accelerator_lock.acquire()
        token = self._local_comfyui_accelerator_lock_depth.set(1)
        logger.debug(
            f"Acquired local ComfyUI accelerator operation lock "
            f"(role={role}, reason={reason})"
        )
        return True, token

    def _release_local_comfyui_accelerator_lock(
        self,
        state: tuple[bool, object],
        *,
        backend_role: str,
        reason: str,
    ) -> None:
        acquired, token = state
        self._local_comfyui_accelerator_lock_depth.reset(token)
        if acquired:
            self._local_comfyui_accelerator_lock.release()
            role = self._normalize_comfyui_backend_role(backend_role)
            logger.debug(
                f"Released local ComfyUI accelerator operation lock "
                f"(role={role}, reason={reason})"
            )

    @asynccontextmanager
    async def _local_comfyui_accelerator_operation(
        self,
        *,
        backend_role: str,
        reason: str,
    ):
        state = await self._acquire_local_comfyui_accelerator_lock(
            backend_role=backend_role,
            reason=reason,
        )
        try:
            yield
        finally:
            self._release_local_comfyui_accelerator_lock(
                state,
                backend_role=backend_role,
                reason=reason,
            )

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

    def schedule_comfyui_backend_restart(
        self,
        backend_role: str,
        reason: str,
    ) -> asyncio.Task[bool] | None:
        role = self._normalize_comfyui_backend_role(backend_role)
        existing_task = self._comfyui_restart_tasks.get(role)
        if existing_task is not None:
            if not existing_task.done():
                logger.info(
                    "ComfyUI backend restart already scheduled; skipping duplicate request "
                    f"for role '{role}' ({reason})"
                )
                return existing_task
            if existing_task.cancelled():
                logger.warning(
                    "Previous ComfyUI backend restart task was cancelled; scheduling "
                    f"a new restart for role '{role}' ({reason})"
                )
            else:
                try:
                    existing_task.result()
                except Exception as exc:
                    logger.warning(
                        "Previous ComfyUI backend restart task failed; scheduling "
                        f"a new restart for role '{role}' ({reason}): {exc}"
                    )
            self._comfyui_restart_tasks.pop(role, None)

        self._mark_local_comfyui_released(backend_role=role)
        task = asyncio.create_task(
            self._scheduled_backend_restart(role, reason)
        )
        self._comfyui_restart_tasks[role] = task
        return task

    async def _scheduled_backend_restart(
        self,
        backend_role: str,
        reason: str,
    ) -> bool:
        role = self._normalize_comfyui_backend_role(backend_role)
        async with self._local_comfyui_accelerator_operation(
            backend_role=role,
            reason=f"scheduled-restart:{reason}",
        ):
            async with self._get_backend_lock(role):
                restarted = await self._restart_comfyui_backend_role(role, reason)
        if not restarted:
            scope = self._local_comfyui_task_scope.get()
            if scope is not None:
                role_state = scope.state_for(role)
                role_state.pending_memory_release = True
        return restarted

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
                await self._close_comfykit_instance(role)
            
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
            kit = self._comfykit_by_backend.pop(role, None)
            self._comfykit_config_hash_by_backend.pop(role, None)
            if kit is None:
                continue
            for attr_name in ("_runninghub_executor", "_http_executor", "_websocket_executor"):
                executor = getattr(kit, attr_name, None)
                await self._close_comfykit_executor(role, attr_name, executor)

    async def _close_comfykit_executor(self, role: str, attr_name: str, executor) -> None:
        if executor is None:
            return
        close = getattr(executor, "close", None)
        if not callable(close):
            return
        try:
            close_result = close()
            if inspect.isawaitable(close_result):
                await asyncio.wait_for(
                    close_result,
                    timeout=self._comfykit_close_timeout_seconds,
                )
        except asyncio.TimeoutError:
            logger.warning(
                "Timed out closing stale ComfyKit executor "
                f"{attr_name} for backend role '{role}' after "
                f"{self._comfykit_close_timeout_seconds} seconds"
            )
        except Exception as e:
            logger.warning(
                f"Failed to close stale ComfyKit executor {attr_name} "
                f"for backend role '{role}': {e}"
            )

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
        client = self._get_comfyui_maintenance_client(role)
        if client is None:
            return

        try:
            await client.cleanup_before_generation()
        except Exception as e:
            raise RuntimeError(f"ComfyUI pre-workflow cleanup failed: {e}") from e

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

    def _restart_after_batch_for_role(self, backend_role: str) -> bool:
        role = self._normalize_comfyui_backend_role(backend_role)
        try:
            registry = self._get_comfyui_backend_registry()
            return registry.profile(role).restart_after_batch
        except ValueError:
            return False

    async def _restart_comfyui_backend_role(self, backend_role: str, reason: str) -> bool:
        role = self._normalize_comfyui_backend_role(backend_role)
        backend = self._get_managed_comfyui_backend(role)
        if backend is None:
            return False
        restarted = await backend.restart(reason=reason)
        if restarted:
            logger.info(
                f"Pixelle-managed ComfyUI backend '{role}' restarted; "
                "closing stale ComfyKit executors"
            )
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
        results,
    ) -> None:
        logger.bind(
            channel="runtime",
            event="comfyui_extension_release_preflight",
            context=context,
            extension_results=[
                result.to_log_dict() if hasattr(result, "to_log_dict") else result
                for result in results
            ],
        ).info(f"ComfyUI {context} extension release preflight completed")

    async def force_release_comfyui_memory(
        self,
        *,
        context: str,
        backend_role: str = "default",
        include_extensions: bool = False,
        extensions: tuple[ComfyUIExtensionName, ...] = ("indextts2",),
    ) -> bool:
        self.config = config_manager.config.to_dict()
        client = self._get_comfyui_maintenance_client(backend_role)
        if client is None:
            return False

        try:
            if include_extensions:
                result = await client.free_memory_with_extensions(
                    "high",
                    extensions=extensions,
                    missing_endpoint="required",
                )
            else:
                result = await client.free_memory("high")
            self._log_comfyui_memory_release(
                context=context,
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
        missing_endpoint: str = "required",
    ) -> bool:
        client = self._get_comfyui_maintenance_client(backend_role)
        if client is None:
            return False

        try:
            results = await client.preflight_extension_release_endpoints(
                extensions=extensions,
                missing_endpoint=missing_endpoint,
            )
        except Exception as e:
            detail = str(e).strip() or repr(e) or type(e).__name__
            raise RuntimeError(
                "ComfyUI "
                f"{context} extension release endpoint preflight failed "
                f"({type(e).__name__}): {detail}"
            ) from e
        self._log_comfyui_extension_release_preflight(
            context=context,
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
        """Release GPU memory after a workflow batch.

        When restart_after_batch is enabled for this backend role, performs a full
        ComfyUI backend restart to reliably release both GPU VRAM and CPU memory.
        Otherwise keeps the backend alive so that GGUF (and other) models stay
        loaded in GPU memory for fast follow-up requests.
        """
        if not extensions:
            return await self.release_comfyui_after_local_workflow(
                backend_role=backend_role
            )

        if not self._restart_after_batch_for_role(backend_role):
            logger.info(
                f"[MEMORY_RELEASE] Skipping ComfyUI backend restart for '{backend_role}' "
                f"(extensions: {extensions}) — restart_after_batch=False, keeping backend alive"
            )
            self._mark_local_comfyui_released(backend_role=backend_role)
            return True

        logger.info(f"[MEMORY_RELEASE] Restarting ComfyUI backend '{backend_role}' (extensions: {extensions}) to release GPU memory...")
        try:
            async with self._local_comfyui_accelerator_operation(
                backend_role=backend_role,
                reason=f"{context} memory release",
            ):
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
        """Release GPU memory after a workflow batch.

        When restart_after_batch is enabled for this backend role, performs a full
        ComfyUI backend restart. Otherwise keeps the backend alive so models stay
        loaded in GPU memory for fast follow-up requests.
        """
        if not self._restart_after_batch_for_role(backend_role):
            logger.info(
                f"[MEMORY_RELEASE] Skipping ComfyUI backend restart for '{backend_role}' "
                "(post-workflow) — restart_after_batch=False, keeping backend alive"
            )
            self._mark_local_comfyui_released(backend_role=backend_role)
            return True

        logger.info(f"[MEMORY_RELEASE] Restarting ComfyUI backend '{backend_role}' (post-workflow) to release GPU memory...")
        try:
            async with self._local_comfyui_accelerator_operation(
                backend_role=backend_role,
                reason="post-workflow memory release",
            ):
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
        """Release GPU memory at task exit.

        When restart_after_batch is enabled for this backend role, performs a full
        ComfyUI backend restart. Otherwise keeps the backend alive.
        """
        if not self._restart_after_batch_for_role(backend_role):
            logger.info(
                f"[MEMORY_RELEASE] Skipping ComfyUI backend restart for '{backend_role}' "
                "(post-task) — restart_after_batch=False, keeping backend alive"
            )
            self._mark_local_comfyui_released(backend_role=backend_role)
            return True

        async with self._local_comfyui_accelerator_operation(
            backend_role=backend_role,
            reason="post-task memory release",
        ):
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
        if is_index_tts2_workflow_key(workflow_input):
            extensions.append("indextts2")
        if is_omnivoice_workflow_key(workflow_input):
            extensions.append("omnivoice")
        if self._is_gguf_workflow_key(workflow_input):
            extensions.append("gguf")
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
        missing_endpoint: str = "required",
    ) -> None:
        context_suffix = _EXTENSION_RELEASE_CONTEXTS[extension]
        role = session.backend_role if session is not None else self._normalize_comfyui_backend_role(
            backend_role
        )
        effective_missing_endpoint = session.missing_endpoint if session is not None else missing_endpoint
        if session is not None:
            if extension in session.preflighted_extensions:
                return
            await self.preflight_comfyui_extension_release_endpoints(
                context=f"pre-{context_suffix}-workflow",
                backend_role=role,
                extensions=(extension,),
                missing_endpoint=effective_missing_endpoint,
            )
            session.preflighted_extensions.add(extension)
            return

        await self.preflight_comfyui_extension_release_endpoints(
            context=f"pre-{context_suffix}-workflow",
            backend_role=role,
            extensions=(extension,),
            missing_endpoint=missing_endpoint,
        )

    async def _preflight_workflow_extensions_once(
        self,
        extensions: tuple[ComfyUIExtensionName, ...],
        session: _LocalComfyUIWorkflowSession | None,
        *,
        backend_role: str = "default",
        missing_endpoint: str = "required",
    ) -> None:
        for extension in extensions:
            await self._preflight_extension_release_endpoint_once(
                extension,
                session,
                backend_role=backend_role,
                missing_endpoint=missing_endpoint,
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
                        missing_endpoint=session.missing_endpoint,
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

    async def _restart_local_comfykit_workflow_and_retry_once(
        self,
        workflow_input,
        workflow_params: dict,
        *,
        backend_role: str,
        restart_reason: str,
        warning_message: str,
    ) -> tuple[bool, Any]:
        restarted = await self._restart_comfyui_backend_role(
            backend_role,
            restart_reason,
        )
        if not restarted:
            return False, None
        logger.warning(warning_message)
        await self.prepare_comfyui_for_local_workflow(backend_role=backend_role)
        await self._register_local_comfyui_task_use(backend_role=backend_role)
        return True, await self._execute_local_comfykit_workflow_once(
            workflow_input,
            workflow_params,
            backend_role=backend_role,
        )

    async def _execute_local_comfykit_workflow(
        self,
        workflow_input,
        workflow_params: dict,
        *,
        backend_role: str = "default",
    ):
        role = self._normalize_comfyui_backend_role(backend_role)
        try:
            result = await self._execute_local_comfykit_workflow_once(
                workflow_input,
                workflow_params,
                backend_role=role,
            )
            if _local_comfykit_result_needs_transient_backend_retry(result):
                retried, retry_result = await self._restart_local_comfykit_workflow_and_retry_once(
                    workflow_input,
                    workflow_params,
                    backend_role=role,
                    restart_reason="transient_engine_error_during_workflow",
                    warning_message=(
                        "Local ComfyUI workflow returned a transient backend engine "
                        "error; restarted managed backend and retrying once."
                    ),
                )
                if retried:
                    return retry_result
            return result
        except Exception as exc:
            if looks_like_backend_connection_loss(str(exc)):
                retried, retry_result = await self._restart_local_comfykit_workflow_and_retry_once(
                    workflow_input,
                    workflow_params,
                    backend_role=role,
                    restart_reason="connection_lost_during_workflow",
                    warning_message=(
                        "Local ComfyUI workflow lost its backend connection; "
                        "restarted managed backend and retrying once."
                    ),
                )
                if retried:
                    return retry_result
            if looks_like_transient_backend_execution_error(str(exc)):
                retried, retry_result = await self._restart_local_comfykit_workflow_and_retry_once(
                    workflow_input,
                    workflow_params,
                    backend_role=role,
                    restart_reason="transient_engine_error_during_workflow",
                    warning_message=(
                        "Local ComfyUI workflow raised a transient backend engine "
                        "error; restarted managed backend and retrying once."
                    ),
                )
                if retried:
                    return retry_result
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
                try:
                    await backend_lock.acquire()
                    session.lock_acquired = True
                    await self.prepare_comfyui_for_local_workflow(backend_role=role)
                    session.prepared = True
                    await self._register_local_comfyui_task_use(backend_role=role)
                except Exception:
                    if session.lock_acquired:
                        session.lock_acquired = False
                        backend_lock.release()
                    raise

        async with session.execute_lock:
            async with self._local_comfyui_accelerator_operation(
                backend_role=role,
                reason="workflow-session-execute",
            ):
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
        missing_endpoint: str = "required",
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
            release_after_session=release_after_session,
            missing_endpoint=missing_endpoint,
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
        media_prompt_trace_context: Mapping[str, Any] | None = None,
        tts_workflow_trace_context: Mapping[str, Any] | None = None,
        workflow_domain: str | None = None,
        media_type: str | None = None,
        resolved_workflow: str | None = None,
        workflow_file_trace: Mapping[str, Any] | None = None,
    ):
        if isinstance(workflow_input, Mapping):
            raise ValueError(
                "raw workflow mappings are not allowed through public ComfyKit execution; "
                "use execute_comfykit_workflow_file with a traceable workflow file"
            )
        return await self._execute_comfykit_workflow_checked(
            workflow_input,
            workflow_params,
            workflow_source=workflow_source,
            backend_role=backend_role,
            media_prompt_trace_context=media_prompt_trace_context,
            tts_workflow_trace_context=tts_workflow_trace_context,
            tts_workflow_contract=None,
            tts_service_domain=None,
            workflow_domain=workflow_domain,
            analysis_service_domain=None,
            media_type=media_type,
            resolved_workflow=resolved_workflow,
            workflow_file_trace=workflow_file_trace,
        )

    async def _execute_analysis_comfykit_workflow(
        self,
        workflow_input,
        workflow_params: dict,
        *,
        workflow_source: str,
        analysis_service_domain: str,
        backend_role: str = "default",
        media_prompt_trace_context: Mapping[str, Any] | None = None,
        tts_workflow_trace_context: Mapping[str, Any] | None = None,
        analysis_workflow_trace_context: Mapping[str, Any] | None = None,
        workflow_domain: str | None = "analysis",
        media_type: str | None = None,
        resolved_workflow: str | None = None,
        workflow_file_trace: Mapping[str, Any] | None = None,
    ):
        return await self._execute_comfykit_workflow_checked(
            workflow_input,
            workflow_params,
            workflow_source=workflow_source,
            backend_role=backend_role,
            media_prompt_trace_context=media_prompt_trace_context,
            tts_workflow_trace_context=tts_workflow_trace_context,
            analysis_workflow_trace_context=analysis_workflow_trace_context,
            tts_workflow_contract=None,
            tts_service_domain=None,
            workflow_domain=workflow_domain,
            analysis_service_domain=analysis_service_domain,
            media_type=media_type,
            resolved_workflow=resolved_workflow,
            workflow_file_trace=workflow_file_trace,
        )

    async def _execute_tts_comfykit_workflow(
        self,
        workflow_input,
        workflow_params: dict,
        *,
        workflow_source: str,
        tts_service_domain: str = "tts",
        backend_role: str = "default",
        media_prompt_trace_context: Mapping[str, Any] | None = None,
        tts_workflow_trace_context: Mapping[str, Any] | None = None,
        workflow_domain: str | None = None,
        media_type: str | None = None,
        resolved_workflow: str | None = None,
        workflow_file_trace: Mapping[str, Any] | None = None,
    ):
        if str(tts_service_domain or "").strip().lower() != "tts":
            raise ValueError("TTS workflow execution requires the tts service domain")
        return await self._execute_comfykit_workflow_checked(
            workflow_input,
            workflow_params,
            workflow_source=workflow_source,
            backend_role=backend_role,
            media_prompt_trace_context=media_prompt_trace_context,
            tts_workflow_trace_context=tts_workflow_trace_context,
            tts_workflow_contract=resolved_workflow,
            tts_service_domain=tts_service_domain,
            workflow_domain=workflow_domain,
            analysis_service_domain=None,
            media_type=media_type,
            resolved_workflow=resolved_workflow,
            workflow_file_trace=workflow_file_trace,
        )

    async def _execute_media_comfykit_workflow(
        self,
        workflow_input,
        workflow_params: dict,
        *,
        workflow_source: str,
        media_service_domain: str,
        backend_role: str = "default",
        media_prompt_trace_context: Mapping[str, Any] | None = None,
        tts_workflow_trace_context: Mapping[str, Any] | None = None,
        workflow_domain: str | None = None,
        media_type: str | None = None,
        resolved_workflow: str | None = None,
        workflow_file_trace: Mapping[str, Any] | None = None,
    ):
        media_contract = str(media_service_domain or "").strip().lower()
        if media_contract not in _MEDIA_PROMPT_TRACE_MEDIA_TYPES:
            raise ValueError("media workflow execution requires an image or video service domain")
        requested_media_type = str(media_type or "").strip().lower()
        if requested_media_type and requested_media_type != media_contract:
            raise ValueError("media workflow execution media_type does not match service domain")
        return await self._execute_comfykit_workflow_checked(
            workflow_input,
            workflow_params,
            workflow_source=workflow_source,
            backend_role=backend_role,
            media_prompt_trace_context=media_prompt_trace_context,
            tts_workflow_trace_context=tts_workflow_trace_context,
            tts_workflow_contract=None,
            tts_service_domain=None,
            workflow_domain=workflow_domain,
            analysis_service_domain=None,
            media_workflow_contract=media_contract,
            media_type=media_type,
            resolved_workflow=resolved_workflow,
            workflow_file_trace=workflow_file_trace,
        )

    async def _execute_comfykit_workflow_checked(
        self,
        workflow_input,
        workflow_params: dict,
        *,
        workflow_source: str,
        backend_role: str = "default",
        media_prompt_trace_context: Mapping[str, Any] | None = None,
        tts_workflow_trace_context: Mapping[str, Any] | None = None,
        analysis_workflow_trace_context: Mapping[str, Any] | None = None,
        tts_workflow_contract: str | None = None,
        tts_service_domain: str | None = None,
        workflow_domain: str | None = None,
        analysis_service_domain: str | None = None,
        media_workflow_contract: str | None = None,
        media_type: str | None = None,
        resolved_workflow: str | None = None,
        workflow_file_trace: Mapping[str, Any] | None = None,
        trusted_workflow_file_trace: bool = False,
    ):
        effective_workflow_file_trace = _workflow_file_trace_from_execution_request(
            workflow_input=workflow_input,
            resolved_workflow=resolved_workflow,
            workflow_file_trace=workflow_file_trace,
            trusted_workflow_file_trace=trusted_workflow_file_trace,
        )
        if (
            _execution_requires_workflow_file_trace(
                media_prompt_trace_context=media_prompt_trace_context,
                tts_workflow_trace_context=tts_workflow_trace_context,
                analysis_workflow_trace_context=analysis_workflow_trace_context,
                media_workflow_contract=media_workflow_contract,
                tts_workflow_contract=tts_workflow_contract,
                tts_service_domain=tts_service_domain,
                analysis_service_domain=analysis_service_domain,
            )
            and not effective_workflow_file_trace
        ):
            raise ValueError(
                "workflow file trace is required before ComfyKit workflow execution"
            )
        tts_trace_context = _validate_comfykit_tts_trace_boundary(
            workflow_input=workflow_input,
            workflow_params=workflow_params,
            workflow_source=workflow_source,
            tts_workflow_trace_context=tts_workflow_trace_context,
            tts_workflow_contract=tts_workflow_contract,
            media_workflow_contract=media_workflow_contract,
            workflow_file_trace=effective_workflow_file_trace,
        )
        analysis_trace_context = _validate_comfykit_analysis_trace_boundary(
            workflow_input=workflow_input,
            workflow_params=workflow_params,
            analysis_workflow_trace_context=analysis_workflow_trace_context,
            workflow_domain=workflow_domain,
            analysis_service_domain=analysis_service_domain,
            resolved_workflow=resolved_workflow,
            workflow_file_trace=effective_workflow_file_trace,
        )
        _enforce_selfhost_workflow_content_boundary(
            workflow_input=workflow_input,
            workflow_domain=workflow_domain,
            media_workflow_contract=media_workflow_contract,
            media_prompt_trace_context=media_prompt_trace_context,
            tts_workflow_trace_context=tts_workflow_trace_context,
            analysis_workflow_trace_context=analysis_workflow_trace_context,
        )
        trace_context = _validate_comfykit_media_prompt_trace_boundary(
            workflow_input=workflow_input,
            workflow_params=workflow_params,
            workflow_source=workflow_source,
            media_prompt_trace_context=media_prompt_trace_context,
            media_type=media_type,
            resolved_workflow=resolved_workflow,
            media_workflow_contract=media_workflow_contract,
            tts_workflow_contract=tts_workflow_contract,
            workflow_domain=workflow_domain,
            analysis_service_domain=analysis_service_domain,
            workflow_file_trace=effective_workflow_file_trace,
        )
        try:
            result = await self._execute_comfykit_workflow_unchecked(
                workflow_input,
                workflow_params,
                workflow_source=workflow_source,
                backend_role=backend_role,
            )
        except Exception as exc:
            if isinstance(trace_context, Mapping):
                write_media_workflow_result_artifact(
                    trace_context,
                    status="error",
                    result={
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    },
                )
            if isinstance(tts_trace_context, Mapping):
                write_tts_workflow_result_artifact(
                    tts_trace_context,
                    status="error",
                    result={
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    },
                )
            if isinstance(analysis_trace_context, Mapping):
                write_analysis_workflow_result_artifact(
                    analysis_trace_context,
                    status="error",
                    result={
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    },
                )
            raise

        if isinstance(trace_context, Mapping):
            write_media_workflow_result_artifact(
                trace_context,
                status=str(getattr(result, "status", "") or "completed"),
                result=summarize_media_workflow_result(result),
            )
        if isinstance(tts_trace_context, Mapping):
            write_tts_workflow_result_artifact(
                tts_trace_context,
                status=str(getattr(result, "status", "") or "completed"),
                result=_summarize_tts_workflow_result(result),
            )
        if isinstance(analysis_trace_context, Mapping):
            write_analysis_workflow_result_artifact(
                analysis_trace_context,
                status=str(getattr(result, "status", "") or "completed"),
                result=_summarize_analysis_workflow_result(result),
            )
        return result

    async def _execute_comfykit_workflow_unchecked(
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
        async with self._local_comfyui_accelerator_operation(
            backend_role=role,
            reason="workflow",
        ):
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

    def _validate_selfhost_workflow_content_contract(
        self,
        *,
        workflow_path: Path,
        workflow_contract: Mapping[str, Any],
        workflow_params: Mapping[str, Any],
        media_prompt_trace_context: Mapping[str, Any] | None,
        tts_workflow_trace_context: Mapping[str, Any] | None,
        analysis_workflow_trace_context: Mapping[str, Any] | None,
        workflow_domain: str | None,
        media_type: str | None,
    ) -> None:
        if workflow_contract.get("contains_tts_nodes") and media_prompt_trace_context is not None:
            raise ValueError(
                "selfhost workflow content resolves to TTS nodes and cannot execute "
                "through a media prompt trace"
            )
        if (
            workflow_contract.get("contains_analysis_nodes")
            and not _workflow_domain_requests_analysis(workflow_domain)
        ):
            raise ValueError(
                "analysis workflow execution requires a resolved analysis service workflow"
            )
        prompt_literals = workflow_contract.get("prompt_literals")
        _require_workflow_prompt_literal_trace(
            workflow_contract=workflow_contract,
            trace_contexts=(
                media_prompt_trace_context,
                tts_workflow_trace_context,
                analysis_workflow_trace_context,
            ),
        )
        if media_type and not workflow_params and prompt_literals:
            raise ValueError(
                "workflow prompt literals require traced workflow params before media execution"
            )

    def resolve_comfykit_workflow_file_identity(
        self,
        workflow_path: str | Path,
    ) -> dict[str, Any]:
        path = Path(workflow_path)
        if not path.exists():
            raise FileNotFoundError(f"Workflow file does not exist: {path}")

        with path.open("r", encoding="utf-8") as f:
            workflow_config = json.load(f)

        if not isinstance(workflow_config, dict):
            raise ValueError(f"Workflow file must contain a JSON object: {path}")

        workflow_source = str(workflow_config.get("source") or "selfhost").lower()
        content_contract = workflow_content_contract(workflow_config)
        file_sha256 = workflow_file_sha256(path)
        if workflow_source == "runninghub":
            workflow_config = validate_runninghub_descriptor_contract(
                path,
                workflow_config,
            )
            workflow_id = workflow_config["workflow_id"]
            workflow_domain, service_domain = runninghub_descriptor_domains(
                workflow_config,
            )
            return {
                "path": path,
                "workflow_key": str(path),
                "source": workflow_source,
                "workflow_input": str(workflow_id),
                "backend_role": "default",
                "workflow_domain": workflow_domain,
                "service_domain": service_domain,
                "workflow_file_sha256": file_sha256,
                "workflow_content_contract": content_contract,
                "media_type": workflow_config.get("media_type"),
            }

        return {
            "path": path,
            "workflow_key": str(path),
            "source": workflow_source,
            "workflow_input": str(path),
            "backend_role": self._get_comfyui_backend_registry().resolve_role_for_workflow(
                str(path)
            ),
            "workflow_file_sha256": file_sha256,
            "workflow_content_contract": content_contract,
        }

    async def execute_comfykit_workflow_file(
        self,
        workflow_path: str | Path,
        workflow_params: dict,
        *,
        media_prompt_trace_context: Mapping[str, Any] | None = None,
        tts_workflow_trace_context: Mapping[str, Any] | None = None,
        analysis_workflow_trace_context: Mapping[str, Any] | None = None,
        workflow_domain: str | None = None,
        media_type: str | None = None,
    ):
        workflow_identity = self.resolve_comfykit_workflow_file_identity(workflow_path)
        workflow_input = str(workflow_identity["workflow_input"])
        workflow_key = str(workflow_identity.get("workflow_key") or workflow_input)
        workflow_source = str(workflow_identity["source"])
        backend_role = str(workflow_identity["backend_role"])
        workflow_content = workflow_identity.get("workflow_content_contract")
        if not isinstance(workflow_content, Mapping):
            workflow_content = {}
        workflow_file_trace = _workflow_file_trace_from_identity(workflow_identity)
        runninghub_media_contract = (
            str(workflow_identity.get("media_type") or "").strip().lower()
            if workflow_source == "runninghub"
            else ""
        )
        descriptor_workflow_domain = str(
            workflow_identity.get("workflow_domain") or ""
        ).strip().lower()
        descriptor_service_domain = str(
            workflow_identity.get("service_domain") or ""
        ).strip().lower()
        boundary_resolved_workflow = (
            workflow_key
            if (
                tts_workflow_trace_context is not None
                or descriptor_workflow_domain in _ANALYSIS_WORKFLOW_DOMAINS
            )
            else workflow_input
        )
        descriptor_analysis_service_domain = (
            descriptor_service_domain
            if descriptor_service_domain in {"image_analysis", "video_analysis"}
            else None
        )
        if workflow_source != "runninghub":
            self._validate_selfhost_workflow_content_contract(
                workflow_path=Path(workflow_identity["path"]),
                workflow_contract=workflow_content,
                workflow_params=workflow_params,
                media_prompt_trace_context=media_prompt_trace_context,
                tts_workflow_trace_context=tts_workflow_trace_context,
                analysis_workflow_trace_context=analysis_workflow_trace_context,
                workflow_domain=workflow_domain or descriptor_workflow_domain or None,
                media_type=media_type,
            )

        _validate_comfykit_tts_trace_boundary(
            workflow_input=workflow_input,
            workflow_params=workflow_params,
            workflow_source=workflow_source,
            tts_workflow_trace_context=tts_workflow_trace_context,
            tts_workflow_contract=workflow_key,
            media_workflow_contract=runninghub_media_contract or None,
            workflow_file_trace=workflow_file_trace,
        )
        trace_context = _validate_comfykit_media_prompt_trace_boundary(
            workflow_input=workflow_input,
            workflow_params=workflow_params,
            workflow_source=workflow_source,
            media_prompt_trace_context=media_prompt_trace_context,
            media_type=media_type,
            resolved_workflow=boundary_resolved_workflow,
            media_workflow_contract=runninghub_media_contract or None,
            tts_workflow_contract=workflow_key
            if descriptor_workflow_domain == "tts" or descriptor_service_domain == "tts"
            else None,
            workflow_domain=workflow_domain or descriptor_workflow_domain or None,
            analysis_service_domain=descriptor_analysis_service_domain,
            workflow_file_boundary=True,
            workflow_file_trace=workflow_file_trace,
        )
        resolved_media_type = str(runninghub_media_contract or media_type or "").strip()
        if isinstance(trace_context, Mapping):
            resolved_media_type = (
                resolved_media_type
                or str(trace_context.get("media_type") or "").strip()
            )

        execute_kwargs: dict[str, Any] = {
            "workflow_source": workflow_source,
            "backend_role": backend_role,
            "media_prompt_trace_context": trace_context,
            "media_type": resolved_media_type or None,
            "resolved_workflow": boundary_resolved_workflow,
        }
        if workflow_source == "runninghub":
            execute_kwargs["media_workflow_contract"] = runninghub_media_contract or None
        effective_workflow_domain = workflow_domain or descriptor_workflow_domain or None
        if effective_workflow_domain is not None:
            execute_kwargs["workflow_domain"] = effective_workflow_domain
        if descriptor_analysis_service_domain is not None:
            execute_kwargs["analysis_service_domain"] = descriptor_analysis_service_domain
            execute_kwargs["analysis_workflow_trace_context"] = analysis_workflow_trace_context
        if tts_workflow_trace_context is not None:
            execute_kwargs["tts_workflow_trace_context"] = tts_workflow_trace_context
            execute_kwargs["tts_workflow_contract"] = workflow_key
        if descriptor_service_domain == "tts":
            execute_kwargs["tts_workflow_contract"] = workflow_key
        execute_kwargs["workflow_file_trace"] = workflow_file_trace
        execute_kwargs["trusted_workflow_file_trace"] = True

        return await self._execute_comfykit_workflow_checked(
            workflow_input,
            workflow_params,
            **execute_kwargs,
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
