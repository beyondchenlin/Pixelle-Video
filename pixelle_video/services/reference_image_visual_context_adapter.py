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

import json
import re
from collections.abc import Iterable, Mapping
from contextvars import ContextVar, Token
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from pixelle_video.models.asset_bible import IPProfile
from pixelle_video.models.reference_image import ReferenceImageAsset
from pixelle_video.models.reference_image_analysis import ReferenceImageAnalysisResult
from pixelle_video.models.reference_image_visual_context import (
    ReferenceImageProfileMergeMode,
    ReferenceImageVisualContext,
)

_REFERENCE_IMAGE_VISUAL_STORY_CONTEXT_PATCH: ContextVar[dict[str, Any]] = ContextVar(
    "reference_image_visual_story_context_patch",
    default={},
)
_DATA_IMAGE_RE = re.compile(r"data:image/[^;,\s]+;base64,[A-Za-z0-9+/=]+", re.IGNORECASE)
_ABSOLUTE_PATH_HINT_RE = re.compile(
    r"([A-Za-z]:\\[^ \n\r\t]+|/(?:Users|home|mnt|var|tmp|etc)/[^ \n\r\t]+)"
)


@dataclass(frozen=True)
class ReferenceImageContextBuildResult:
    visual_context: ReferenceImageVisualContext
    ip_profile: IPProfile | None
    visual_story_context_patch: dict[str, Any]


def set_reference_image_visual_story_context_patch(
    patch: Mapping[str, Any] | None,
) -> Token:
    return _REFERENCE_IMAGE_VISUAL_STORY_CONTEXT_PATCH.set(dict(patch or {}))


def reset_reference_image_visual_story_context_patch(token: Token) -> None:
    _REFERENCE_IMAGE_VISUAL_STORY_CONTEXT_PATCH.reset(token)


def current_reference_image_visual_story_context_patch() -> dict[str, Any]:
    return dict(_REFERENCE_IMAGE_VISUAL_STORY_CONTEXT_PATCH.get() or {})


class ReferenceImageVisualContextAdapter:
    """Merge reference-image analysis into prompt planning inputs.

    The adapter is conservative: it supplements existing IPProfile fields rather
    than overwriting them by default. When there is no IPProfile, it returns a
    supplemental visual-story context and prompt fallback hint so the generation
    path can still benefit from reference-image analysis without physical image
    injection.
    """

    def build(
        self,
        *,
        asset: ReferenceImageAsset,
        analysis_result: ReferenceImageAnalysisResult,
        ip_profile: IPProfile | None = None,
        merge_mode: ReferenceImageProfileMergeMode = "supplement",
        preserve_real_asset_without_analysis: bool = False,
    ) -> ReferenceImageContextBuildResult:
        warnings: list[str] = []
        analysis = analysis_result.analysis
        asset_trace = asset.to_trace_dict()
        reference_payload = {
            "enabled": True,
            "asset_sha256": asset.workflow_sha256,
            "workflow_asset_relative_path": asset.workflow_asset_relative_path,
            "mime_type": asset.workflow_mime_type,
            "width": asset.workflow_width,
            "height": asset.workflow_height,
            "byte_size": asset.workflow_byte_size,
            "resource_version": f"reference-image:{asset.workflow_sha256}",
            "asset": asset_trace,
            "merge_mode": merge_mode,
        }
        if analysis is None or analysis_result.status != "success":
            if not preserve_real_asset_without_analysis:
                warnings.append("reference image analysis is not available")
                return ReferenceImageContextBuildResult(
                    visual_context=ReferenceImageVisualContext(
                        enabled=False,
                        asset=asset_trace,
                        analysis=analysis_result.to_trace_dict(),
                        merge_mode=merge_mode,
                        merge_warnings=warnings,
                    ),
                    ip_profile=ip_profile,
                    visual_story_context_patch={},
                )
            warnings.append(
                (
                    "reference image analysis is intentionally disabled for visual-anchor "
                    "generation; the immutable real asset remains enabled"
                )
                if analysis_result.analysis_mode == "off"
                else (
                    "reference image analysis is unavailable; the immutable real asset "
                    "remains enabled"
                )
            )
            visual_story_context_patch = {
                "reference_image": reference_payload,
            }
            visual_context = ReferenceImageVisualContext(
                enabled=True,
                asset=asset_trace,
                analysis=analysis_result.to_trace_dict(),
                supplemental_visual_story_context=visual_story_context_patch,
                merge_mode=merge_mode,
                merge_warnings=warnings,
            )
            return ReferenceImageContextBuildResult(
                visual_context=visual_context,
                ip_profile=ip_profile,
                visual_story_context_patch=visual_story_context_patch,
            )

        prompt_hint = _build_prompt_hint(analysis_result)
        visual_story_context_patch = {
            "reference_image": {
                **reference_payload,
                "subject_summary": analysis.subject_summary,
                "style_summary": analysis.style_summary,
                "color_atmosphere": analysis.color_atmosphere,
                "composition_summary": analysis.composition_summary,
                "identity_anchors": list(analysis.identity_anchors),
                "style_anchors": list(analysis.style_anchors),
                "negative_constraints": list(analysis.negative_constraints),
                "prompt_fallback_hint": prompt_hint,
                "confidence": analysis.confidence,
                "limitations": list(analysis.limitations),
            }
        }

        merged_ip_profile = None
        if ip_profile is not None:
            if merge_mode == "strict":
                merged_profile = ip_profile
                warnings.append("strict merge mode keeps existing IPProfile unchanged")
            elif merge_mode == "override":
                merged_profile = self._override_ip_profile(ip_profile, analysis_result)
            else:
                merged_profile = self._supplement_ip_profile(ip_profile, analysis_result)
            merged_ip_profile = _profile_trace_dict(merged_profile)
        else:
            merged_profile = None

        visual_context = ReferenceImageVisualContext(
            enabled=True,
            asset=asset.to_trace_dict(),
            analysis=analysis_result.to_trace_dict(),
            merged_ip_profile=merged_ip_profile,
            supplemental_visual_story_context=visual_story_context_patch,
            prompt_fallback_hint=prompt_hint,
            merge_mode=merge_mode,
            merge_warnings=warnings,
        )
        return ReferenceImageContextBuildResult(
            visual_context=visual_context,
            ip_profile=merged_profile,
            visual_story_context_patch=visual_story_context_patch,
        )

    @staticmethod
    def _supplement_ip_profile(
        ip_profile: IPProfile,
        analysis_result: ReferenceImageAnalysisResult,
    ) -> IPProfile:
        analysis = analysis_result.analysis
        if analysis is None:
            return ip_profile
        metadata = {
            **dict(ip_profile.metadata),
            "reference_image_analysis": {
                "image_sha256": analysis_result.image_sha256,
                "status": analysis_result.status,
                "merge_mode": "supplement",
            },
        }
        return replace(
            ip_profile,
            visual_summary=ip_profile.visual_summary or analysis.subject_summary or None,
            style_hint=ip_profile.style_hint or analysis.style_summary or None,
            identity_anchors=_dedupe_strings((*ip_profile.identity_anchors, *analysis.identity_anchors)),
            style_boundary_rules=_dedupe_strings((*ip_profile.style_boundary_rules, *analysis.style_anchors)),
            negative_constraints=_dedupe_strings((*ip_profile.negative_constraints, *analysis.negative_constraints)),
            minimal_traits=_dedupe_strings((*ip_profile.minimal_traits, analysis.subject_summary, analysis.color_atmosphere)),
            metadata=metadata,
        )

    @staticmethod
    def _override_ip_profile(
        ip_profile: IPProfile,
        analysis_result: ReferenceImageAnalysisResult,
    ) -> IPProfile:
        analysis = analysis_result.analysis
        if analysis is None:
            return ip_profile
        metadata = {
            **dict(ip_profile.metadata),
            "reference_image_analysis": {
                "image_sha256": analysis_result.image_sha256,
                "status": analysis_result.status,
                "merge_mode": "override",
            },
        }
        return replace(
            ip_profile,
            visual_summary=analysis.subject_summary or ip_profile.visual_summary,
            style_hint=analysis.style_summary or ip_profile.style_hint,
            identity_anchors=_dedupe_strings(analysis.identity_anchors),
            style_boundary_rules=_dedupe_strings(analysis.style_anchors),
            negative_constraints=_dedupe_strings(analysis.negative_constraints),
            minimal_traits=_dedupe_strings((analysis.subject_summary, analysis.color_atmosphere, analysis.composition_summary)),
            metadata=metadata,
        )

    @staticmethod
    def write_artifact(
        task_dir: str | Path,
        visual_context: ReferenceImageVisualContext,
    ) -> ReferenceImageVisualContext:
        task_root = Path(task_dir)
        artifact_dir = task_root / "reference_image"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = artifact_dir / "visual_context.json"
        relative_path = str(artifact_path.relative_to(task_root).as_posix())
        visual_context = visual_context.model_copy(update={"artifact_relative_path": relative_path})
        artifact_path.write_text(
            json.dumps(visual_context.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return visual_context


def merge_ip_profile_from_reference_patch(
    ip_profile: IPProfile | None,
    visual_story_context_patch: Mapping[str, Any] | None,
) -> IPProfile | None:
    if ip_profile is None or not isinstance(visual_story_context_patch, Mapping):
        return ip_profile
    reference_payload = visual_story_context_patch.get("reference_image")
    if not isinstance(reference_payload, Mapping) or not reference_payload.get("enabled"):
        return ip_profile

    merge_mode = str(reference_payload.get("merge_mode") or "supplement").strip().lower()
    identity_anchors = _dedupe_strings(reference_payload.get("identity_anchors") or ())
    style_anchors = _dedupe_strings(reference_payload.get("style_anchors") or ())
    negative_constraints = _dedupe_strings(reference_payload.get("negative_constraints") or ())
    subject_summary = str(reference_payload.get("subject_summary") or "").strip()
    style_summary = str(reference_payload.get("style_summary") or "").strip()
    color_atmosphere = str(reference_payload.get("color_atmosphere") or "").strip()
    composition_summary = str(reference_payload.get("composition_summary") or "").strip()
    metadata = {
        **dict(ip_profile.metadata),
        "reference_image_visual_context": {
            "asset_sha256": str(reference_payload.get("asset_sha256") or ""),
            "merge_mode": merge_mode,
        },
    }

    if merge_mode == "strict":
        return replace(ip_profile, metadata=metadata)
    if merge_mode == "override":
        return replace(
            ip_profile,
            visual_summary=subject_summary or ip_profile.visual_summary,
            style_hint=style_summary or ip_profile.style_hint,
            identity_anchors=identity_anchors or ip_profile.identity_anchors,
            style_boundary_rules=style_anchors or ip_profile.style_boundary_rules,
            negative_constraints=negative_constraints or ip_profile.negative_constraints,
            minimal_traits=_dedupe_strings((subject_summary, color_atmosphere, composition_summary)),
            metadata=metadata,
        )
    return replace(
        ip_profile,
        visual_summary=ip_profile.visual_summary or subject_summary or None,
        style_hint=ip_profile.style_hint or style_summary or None,
        identity_anchors=_dedupe_strings((*ip_profile.identity_anchors, *identity_anchors)),
        style_boundary_rules=_dedupe_strings((*ip_profile.style_boundary_rules, *style_anchors)),
        negative_constraints=_dedupe_strings((*ip_profile.negative_constraints, *negative_constraints)),
        minimal_traits=_dedupe_strings((*ip_profile.minimal_traits, subject_summary, color_atmosphere)),
        metadata=metadata,
    )


def reference_image_prompt_planning_snapshot(
    visual_story_context_patch: Mapping[str, Any] | None,
    *,
    ip_profile: IPProfile | None = None,
) -> dict[str, Any]:
    if not isinstance(visual_story_context_patch, Mapping) or not visual_story_context_patch:
        return {}
    payload: dict[str, Any] = {
        "visual_story_context_patch": _redact_trace_value(dict(visual_story_context_patch)),
    }
    if ip_profile is not None:
        payload["merged_ip_profile"] = _profile_trace_dict(ip_profile)
    return payload


def _profile_trace_dict(ip_profile: IPProfile) -> dict[str, Any]:
    return _redact_trace_value(ip_profile.to_dict())


def _redact_trace_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _redact_trace_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact_trace_value(item) for item in value]
    if isinstance(value, str):
        text = _DATA_IMAGE_RE.sub("<redacted:data-url>", value)
        text = _ABSOLUTE_PATH_HINT_RE.sub("<redacted:absolute-path>", text)
        return text
    return value


def _build_prompt_hint(analysis_result: ReferenceImageAnalysisResult) -> str:
    analysis = analysis_result.analysis
    if analysis is None:
        return ""
    parts = [
        analysis.prompt_hint_zh or analysis.prompt_hint_en,
        analysis.subject_summary,
        analysis.style_summary,
        analysis.color_atmosphere,
        "视觉一致性锚点: " + ", ".join(analysis.identity_anchors[:6]) if analysis.identity_anchors else "",
        "风格锚点: " + ", ".join(analysis.style_anchors[:6]) if analysis.style_anchors else "",
        "避免: " + ", ".join(analysis.negative_constraints[:6]) if analysis.negative_constraints else "",
    ]
    return "；".join(part.strip() for part in parts if isinstance(part, str) and part.strip())[:2000]


def _dedupe_strings(values: Iterable[Any]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return tuple(result)
