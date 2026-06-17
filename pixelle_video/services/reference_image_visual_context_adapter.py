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
from collections.abc import Iterable, Mapping
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


@dataclass(frozen=True)
class ReferenceImageContextBuildResult:
    visual_context: ReferenceImageVisualContext
    ip_profile: IPProfile | None
    visual_story_context_patch: dict[str, Any]


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
    ) -> ReferenceImageContextBuildResult:
        warnings: list[str] = []
        analysis = analysis_result.analysis
        if analysis is None or analysis_result.status != "success":
            visual_context = ReferenceImageVisualContext(
                enabled=False,
                asset=asset.to_trace_dict(),
                analysis=analysis_result.to_trace_dict(),
                merge_mode=merge_mode,
                merge_warnings=["reference image analysis is not available"],
            )
            return ReferenceImageContextBuildResult(
                visual_context=visual_context,
                ip_profile=ip_profile,
                visual_story_context_patch={},
            )

        prompt_hint = _build_prompt_hint(analysis_result)
        visual_story_context_patch = {
            "reference_image": {
                "enabled": True,
                "asset_sha256": asset.sha256,
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
            merged_ip_profile = merged_profile.to_dict()
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
    return "；".join(part.strip() for part in parts if isinstance(part, str) and part.strip())


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
