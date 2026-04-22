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

from dataclasses import dataclass, field
from typing import Any, Literal, Optional

StyleKind = Literal["visual_only", "ip_world", "hybrid"]
StyleSourceOrigin = Literal["request", "library", "legacy"]


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


@dataclass(frozen=True)
class StyledImagePromptBatch:
    prompts: list[str]
    negative_prompt: Optional[str]
    resolved_style: Optional[ResolvedStyleSpec]
    planning_snapshot: Optional[dict[str, Any]] = None
