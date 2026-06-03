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
Shared text rendering API schemas.
"""

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from pixelle_video.models.text_overlay import DEFAULT_IMAGE_TEXT_POSITIVE_PROMPT

DEFAULT_SUPPRESS_EMBEDDED_TEXT_PROMPT = DEFAULT_IMAGE_TEXT_POSITIVE_PROMPT


class TextOverlayRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    mode: Literal["suppress", "programmatic_only", "native_hint", "hybrid"] = "programmatic_only"
    renderer_targets: List[Literal["hyperframes", "html", "ass", "native_prompt", "python"]] = Field(default_factory=list)
    density: Literal["low", "medium", "high"] = "medium"
    max_items_per_frame: int = Field(2, ge=0)


class ImageTextPolicyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suppress_embedded_text: bool = False
    positive_prompt: str = Field(
        DEFAULT_SUPPRESS_EMBEDDED_TEXT_PROMPT,
        description="Prompt fragment appended only when suppress_embedded_text is true",
    )
    negative_prompt: Optional[str] = None


class CaptionRenderingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True


class TextStyleProfileRequest(BaseModel):
    """Partial text style override merged with role-specific defaults downstream."""

    model_config = ConfigDict(extra="forbid")

    font_family: Optional[str] = Field(None, min_length=1, max_length=128)
    font_file: Optional[str] = Field(None, min_length=1, max_length=512)
    font_size: Optional[int] = Field(None, ge=8, le=240)
    primary_color: Optional[str] = Field(None, pattern=r"^#[0-9a-fA-F]{6}$")
    stroke_color: Optional[str] = Field(None, pattern=r"^#[0-9a-fA-F]{6}$")
    stroke_width: Optional[int] = Field(None, ge=0, le=16)
    background_color: Optional[str] = Field(None, pattern=r"^#[0-9a-fA-F]{6}$")
    background_opacity: Optional[float] = Field(None, ge=0.0, le=1.0)
    position: Optional[Literal[
        "top",
        "center",
        "bottom",
        "lower_third",
        "top_left",
        "top_right",
        "bottom_left",
        "bottom_right",
    ]] = None
    alignment: Optional[Literal["left", "center", "right"]] = None
    margin_x: Optional[int] = Field(None, ge=0, le=1000)
    margin_y: Optional[int] = Field(None, ge=0, le=1000)
    max_width_ratio: Optional[float] = Field(None, ge=0.05, le=1.0)
    max_chars_per_line: Optional[int] = Field(None, ge=1, le=200)


class TextRenderingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    caption: CaptionRenderingRequest = Field(default_factory=CaptionRenderingRequest)
    overlay: TextOverlayRequest = Field(default_factory=TextOverlayRequest)
    image_text: ImageTextPolicyRequest = Field(default_factory=ImageTextPolicyRequest)
    caption_style: Optional[TextStyleProfileRequest] = None
    title_style: Optional[TextStyleProfileRequest] = None
    overlay_style: Optional[TextStyleProfileRequest] = None
