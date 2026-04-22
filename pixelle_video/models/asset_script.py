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

"""Structured contracts for asset-based script generation."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _normalize_required_string(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be a non-empty string")
    return normalized


class AssetCatalogEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    asset_id: str
    asset_path: str
    asset_type: Literal["image", "video"]
    asset_name: str
    description: str

    @field_validator("asset_id", "asset_path", "asset_name", "description")
    @classmethod
    def _validate_required_text_fields(cls, value: str, info) -> str:
        return _normalize_required_string(value, info.field_name)

    def to_prompt_dict(self) -> dict[str, str]:
        return {
            "asset_id": self.asset_id,
            "asset_type": self.asset_type,
            "asset_name": self.asset_name,
            "description": self.description,
        }


class AssetScriptSceneResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    scene_number: int = Field(description="Scene number starting from 1")
    asset_id: str = Field(description="Exact asset_id selected from available_assets")
    narrations: list[str] = Field(description="List of narration sentences for this scene (1-5 sentences)")
    duration: int = Field(description="Estimated duration in seconds for this scene")

    @field_validator("asset_id")
    @classmethod
    def _validate_asset_id(cls, value: str) -> str:
        return _normalize_required_string(value, "asset_id")

    @field_validator("narrations")
    @classmethod
    def _validate_narrations(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            normalized.append(_normalize_required_string(value, "narrations"))
        return normalized


class AssetScriptResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    scenes: list[AssetScriptSceneResponse] = Field(description="List of scenes in the video")


__all__ = [
    "AssetCatalogEntry",
    "AssetScriptResponse",
    "AssetScriptSceneResponse",
]
