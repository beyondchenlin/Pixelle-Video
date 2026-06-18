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

import base64
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from pixelle_video.models.llm_interaction_trace import LLMTraceContext, LLMTraceRequiredError
from pixelle_video.models.reference_image import ReferenceImageAsset
from pixelle_video.models.reference_image_analysis import (
    REFERENCE_IMAGE_ANALYSIS_ARTIFACT_VERSION,
    REFERENCE_IMAGE_ANALYSIS_PROMPT_VERSION,
    ReferenceImageAnalysis,
    ReferenceImageAnalysisMode,
    ReferenceImageAnalysisResult,
)
from pixelle_video.services.llm_interaction_recorder import LLMInteractionRecorder
from pixelle_video.services.vision_llm_service import VisionLLMService
from pixelle_video.utils.json_parsing import parse_llm_json_response

_ALLOWED_ANALYSIS_MODES = {"off", "auto", "required"}
_IMAGE_MIME_BY_SUFFIX = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}
_DATA_IMAGE_RE = re.compile(r"data:image/[^;,\s]+;base64,[A-Za-z0-9+/=]+", re.IGNORECASE)
_ABSOLUTE_PATH_HINT_RE = re.compile(
    r"([A-Za-z]:\\[^ \n\r\t]+|/(?:Users|home|mnt|var|tmp|etc)/[^ \n\r\t]+)"
)
_MAX_ERROR_MESSAGE_CHARS = 2000

_SYSTEM_PROMPT = """You are analyzing a reference image for consistent AI video storyboard generation.
Return ONLY a valid JSON object.
Do not identify real people.
Do not infer sensitive attributes.
Do not claim copyrighted character identity unless explicitly supplied by the user.
Focus on visible visual traits, style, composition, palette, clothing, pose, and reusable anchors.
"""

_USER_PROMPT_TEMPLATE = """Analyze the attached reference image for an AI short-video storyboard system.

Return exactly one JSON object with these keys:
- subject_summary: visible subject / role / object description, no identity guessing
- style_summary: visual style and rendering medium
- color_atmosphere: palette, lighting, mood
- composition_summary: framing, pose, camera angle, layout
- identity_anchors: short reusable visible anchors for character/object consistency
- style_anchors: short reusable style anchors
- negative_constraints: what should be avoided to preserve consistency
- prompt_hint_en: compact English prompt hint for image/video generation
- prompt_hint_zh: compact Chinese prompt hint for image/video generation
- confidence: number from 0 to 1
- limitations: uncertainty and visible limitations

Target language preference: {language}
"""


def normalize_reference_image_analysis_mode(value: Any, default: str = "auto") -> ReferenceImageAnalysisMode:
    normalized = str(value or default or "auto").strip().lower()
    if normalized not in _ALLOWED_ANALYSIS_MODES:
        raise ValueError("reference image analysis_mode must be one of: off, auto, required")
    return normalized  # type: ignore[return-value]


def resolve_reference_image_analysis_mode(
    params: Mapping[str, Any] | None,
    reference_image_config: Mapping[str, Any] | Any | None,
) -> ReferenceImageAnalysisMode:
    params = params or {}
    for key in ("reference_image_analysis_mode", "ref_image_analysis_mode"):
        if params.get(key) is not None:
            return normalize_reference_image_analysis_mode(params[key])
    structured_input = params.get("reference_image")
    if isinstance(structured_input, Mapping) and structured_input.get("analysis_mode") is not None:
        return normalize_reference_image_analysis_mode(structured_input.get("analysis_mode"))
    if isinstance(reference_image_config, Mapping):
        return normalize_reference_image_analysis_mode(reference_image_config.get("analysis_mode"), default="off")
    return normalize_reference_image_analysis_mode(
        getattr(reference_image_config, "analysis_mode", "off"),
        default="off",
    )


def vision_config_enabled(vision_config: Mapping[str, Any] | Any | None) -> bool:
    if isinstance(vision_config, Mapping):
        return bool(vision_config.get("enabled", False))
    return bool(getattr(vision_config, "enabled", False))


def vision_config_model(vision_config: Mapping[str, Any] | Any | None) -> str:
    return str(_vision_config_value(vision_config, "model", "") or "").strip()


def vision_unavailable_policy(vision_config: Mapping[str, Any] | Any | None) -> str:
    policy = str(_vision_config_value(vision_config, "unavailable_policy", "skip") or "skip").strip().lower()
    return policy if policy in {"skip", "fail"} else "skip"


def sanitize_reference_image_analysis_error(message: object) -> str:
    text = str(message or "")
    text = _DATA_IMAGE_RE.sub("<redacted:data-url>", text)
    text = _ABSOLUTE_PATH_HINT_RE.sub("<redacted:absolute-path>", text)
    return text[:_MAX_ERROR_MESSAGE_CHARS]


def _vision_config_value(
    vision_config: Mapping[str, Any] | Any | None,
    key: str,
    default: Any = None,
) -> Any:
    if isinstance(vision_config, Mapping):
        return vision_config.get(key, default)
    return getattr(vision_config, key, default)


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _vision_chat_kwargs(vision_config: Mapping[str, Any] | None) -> dict[str, Any]:
    return {
        "api_key": _vision_config_value(vision_config, "api_key"),
        "base_url": _vision_config_value(vision_config, "base_url"),
        "model": vision_config_model(vision_config),
        "temperature": _safe_float(_vision_config_value(vision_config, "temperature", 0.2), 0.2),
        "max_tokens": _safe_int(_vision_config_value(vision_config, "max_tokens", 1200), 1200),
    }


class ReferenceImageAnalysisService:
    """Run structured Vision analysis and persist task-local analysis artifacts."""

    async def analyze(
        self,
        *,
        vision_llm_service: VisionLLMService,
        asset: ReferenceImageAsset,
        prompt_language: str,
        task_dir: str | Path,
        analysis_mode: ReferenceImageAnalysisMode,
        trace_context: LLMTraceContext | None = None,
        trace_recorder: LLMInteractionRecorder | None = None,
        vision_config: Mapping[str, Any] | None = None,
    ) -> ReferenceImageAnalysisResult:
        task_root = Path(task_dir)
        if analysis_mode == "off":
            return self._write_result(
                task_root,
                ReferenceImageAnalysisResult(
                    status="skipped",
                    analysis_mode=analysis_mode,
                    image_sha256=asset.sha256,
                    vision_model=vision_config_model(vision_config),
                    analysis_language=prompt_language,
                    reason="analysis_mode_off",
                ),
            )

        unavailable_reason = self._vision_unavailable_reason(vision_config)
        if unavailable_reason:
            should_fail = analysis_mode == "required" or vision_unavailable_policy(vision_config) == "fail"
            result = self._write_result(
                task_root,
                ReferenceImageAnalysisResult(
                    status="failed" if should_fail else "skipped",
                    analysis_mode=analysis_mode,
                    image_sha256=asset.sha256,
                    vision_model=vision_config_model(vision_config),
                    analysis_language=prompt_language,
                    reason=unavailable_reason,
                    error=unavailable_reason if should_fail else "",
                ),
            )
            if should_fail:
                raise ValueError(f"reference image analysis unavailable: {unavailable_reason}")
            return result

        messages = self._build_messages(
            asset=asset,
            prompt_language=prompt_language,
        )
        vision_chat_kwargs = _vision_chat_kwargs(vision_config)
        try:
            content = await vision_llm_service.chat(
                messages=messages,
                trace_context=trace_context,
                trace_recorder=trace_recorder,
                **vision_chat_kwargs,
            )
            analysis = self._parse_analysis(content)
        except LLMTraceRequiredError:
            raise
        except Exception as first_exc:
            try:
                retry_messages = [*messages, {"role": "user", "content": "The previous response was invalid. Return ONLY one valid JSON object matching the requested schema."}]
                content = await vision_llm_service.chat(
                    messages=retry_messages,
                    trace_context=trace_context,
                    trace_recorder=trace_recorder,
                    **vision_chat_kwargs,
                )
                analysis = self._parse_analysis(content)
            except LLMTraceRequiredError:
                raise
            except Exception as retry_exc:
                error_message = sanitize_reference_image_analysis_error(retry_exc) or sanitize_reference_image_analysis_error(first_exc)
                first_warning = sanitize_reference_image_analysis_error(first_exc)
                result = self._write_result(
                    task_root,
                    ReferenceImageAnalysisResult(
                        status="skipped" if analysis_mode == "auto" else "failed",
                        analysis_mode=analysis_mode,
                        image_sha256=asset.sha256,
                        vision_model=vision_config_model(vision_config),
                        analysis_language=prompt_language,
                        reason="vision_analysis_failed",
                        error=error_message,
                        warnings=[first_warning] if first_warning and first_warning != error_message else [],
                    ),
                )
                if analysis_mode == "required":
                    raise ValueError(f"reference image analysis failed: {error_message}") from retry_exc
                return result

        return self._write_result(
            task_root,
            ReferenceImageAnalysisResult(
                status="success",
                analysis_mode=analysis_mode,
                image_sha256=asset.sha256,
                vision_model=vision_config_model(vision_config),
                analysis_language=prompt_language,
                analysis=analysis,
                metadata={
                    "asset": asset.to_trace_dict(),
                    "artifact_version": REFERENCE_IMAGE_ANALYSIS_ARTIFACT_VERSION,
                    "prompt_version": REFERENCE_IMAGE_ANALYSIS_PROMPT_VERSION,
                },
            ),
        )

    @staticmethod
    def _vision_unavailable_reason(vision_config: Mapping[str, Any] | None) -> str:
        if not vision_config_enabled(vision_config):
            return "vision_llm_disabled"
        if not vision_config_model(vision_config):
            return "vision_llm_model_missing"
        return ""

    def _build_messages(
        self,
        *,
        asset: ReferenceImageAsset,
        prompt_language: str,
    ) -> list[Mapping[str, Any]]:
        image_data_url = self._image_data_url(asset)
        return [
            {"role": "system", "content": _SYSTEM_PROMPT.strip()},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": _USER_PROMPT_TEMPLATE.format(language=prompt_language).strip(),
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": image_data_url},
                    },
                ],
            },
        ]

    @staticmethod
    def _image_data_url(asset: ReferenceImageAsset) -> str:
        image_path = Path(asset.vision_asset_path or asset.task_asset_path)
        if not image_path.is_file():
            raise ValueError("reference image vision asset is missing")
        mime_type = _IMAGE_MIME_BY_SUFFIX.get(image_path.suffix.lower(), asset.mime_type or "image/png")
        encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
        return f"data:{mime_type};base64,{encoded}"

    @staticmethod
    def _parse_analysis(content: str) -> ReferenceImageAnalysis:
        parsed = parse_llm_json_response(
            content,
            allow_code_fence=True,
            allow_embedded_json=False,
        )
        if not isinstance(parsed, Mapping):
            raise ValueError("reference image analysis response must be a JSON object")
        try:
            return ReferenceImageAnalysis.model_validate(parsed)
        except ValidationError as exc:
            raise ValueError(f"reference image analysis validation failed: {exc}") from exc

    @staticmethod
    def _write_result(task_root: Path, result: ReferenceImageAnalysisResult) -> ReferenceImageAnalysisResult:
        artifact_dir = task_root / "reference_image"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = artifact_dir / "analysis.json"
        relative_path = str(artifact_path.relative_to(task_root).as_posix())
        result = result.model_copy(update={"artifact_relative_path": relative_path})
        artifact_path.write_text(
            json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return result
