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
Runtime models for structured style resolution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from pixelle_video.models.prompt_plan import PromptPlanBundle

StyleKind = Literal["visual_only", "ip_world", "hybrid"]
StyleSourceOrigin = Literal["request", "library", "legacy"]


def _normalize_optional_string(value: str) -> str:
    return value.strip()


def _normalize_required_string(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be a non-empty string")
    return normalized


@dataclass(frozen=True)
class StyleSourceSpec:
    origin: StyleSourceOrigin
    raw_content: str
    content_hash: str
    source_identity: str
    item_id: Optional[str] = None


@dataclass(frozen=True)
class ResolvedStyleSpec:
    style_kind: StyleKind
    prompt_template: str = ""
    negative_prompt: str = ""
    style_profile: dict[str, Any] = field(default_factory=dict)
    content_hash: str = ""
    resolver_version: str = ""
    source_identity: str = ""
    raw_content: str = ""


class StyleResolutionProfileResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    style_kind: StyleKind
    subject_policy: str
    shape_language: str
    material: str
    palette: str
    lighting: str
    world_elements: str
    consistency_anchor: str
    negative_rules: str

    @field_validator(
        "subject_policy",
        "shape_language",
        "material",
        "palette",
        "lighting",
        "world_elements",
        "consistency_anchor",
        "negative_rules",
    )
    @classmethod
    def _validate_required_text_fields(cls, value: str, info) -> str:
        return _normalize_required_string(value, f"style_profile.{info.field_name}")


class StyleResolutionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    style_kind: StyleKind
    prompt_template: str = ""
    negative_prompt: str = ""
    style_profile: StyleResolutionProfileResponse

    @field_validator("prompt_template")
    @classmethod
    def _validate_prompt_template(cls, value: str) -> str:
        normalized = _normalize_optional_string(value)
        if normalized and normalized.count("{prompt}") != 1:
            raise ValueError("prompt_template must contain {prompt} exactly once")
        return normalized

    @field_validator("negative_prompt")
    @classmethod
    def _validate_negative_prompt(cls, value: str) -> str:
        return _normalize_optional_string(value)

    @model_validator(mode="after")
    def _validate_style_kind_alignment(self) -> "StyleResolutionResponse":
        if self.style_profile.style_kind != self.style_kind:
            raise ValueError("style_profile.style_kind must match top-level style_kind")
        return self

    def to_resolved_style_spec(
        self,
        *,
        source: StyleSourceSpec,
        resolver_version: str,
    ) -> ResolvedStyleSpec:
        return ResolvedStyleSpec(
            style_kind=self.style_kind,
            prompt_template=self.prompt_template,
            negative_prompt=self.negative_prompt,
            style_profile=self.style_profile.model_dump(),
            content_hash=source.content_hash,
            resolver_version=resolver_version,
            source_identity=source.source_identity,
            raw_content=source.raw_content,
        )


@dataclass(frozen=True)
class StyledImagePromptBatch:
    prompts: list[str]
    negative_prompt: Optional[str]
    resolved_style: Optional[ResolvedStyleSpec]
    planning_snapshot: Optional[dict[str, Any]] = None
    prompt_plan_bundle: Optional[PromptPlanBundle] = None


__all__ = [
    "ResolvedStyleSpec",
    "StyleResolutionProfileResponse",
    "StyleResolutionResponse",
    "StyleSourceOrigin",
    "StyleSourceSpec",
    "StyleKind",
    "StyledImagePromptBatch",
]
