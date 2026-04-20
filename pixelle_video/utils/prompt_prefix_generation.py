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
Helpers for prompt prefix LLM generation and preview selection.
"""

from typing import Any

from pydantic import BaseModel, Field

from pixelle_video.config.prompt_prefix_library import get_prompt_prefix_category_options


class PromptPrefixCandidate(BaseModel):
    """Structured LLM candidate for one prompt prefix preset."""

    name: str
    content: str
    style_category_id: str
    scene_category_id: str
    note: str = ""


class PromptPrefixGenerationResult(BaseModel):
    """Structured LLM response containing multiple prompt prefix candidates."""

    items: list[PromptPrefixCandidate] = Field(default_factory=list)


def sanitize_prompt_prefix_candidates(result: PromptPrefixGenerationResult) -> list[dict[str, str]]:
    """Trim and keep only candidates that use allowed category ids."""
    style_ids, scene_ids = get_prompt_prefix_category_options()
    sanitized: list[dict[str, str]] = []

    for item in result.items:
        content = item.content.strip()
        if not content:
            continue
        if item.style_category_id not in style_ids:
            continue
        if item.scene_category_id not in scene_ids:
            continue

        sanitized.append(
            {
                "name": item.name.strip(),
                "content": content,
                "style_category_id": item.style_category_id,
                "scene_category_id": item.scene_category_id,
                "note": item.note.strip(),
            }
        )

    return sanitized


def build_prompt_prefix_preview_batch(
    items_by_id: dict[str, dict[str, Any]],
    selected_ids: list[str],
    max_items: int = 4,
) -> list[dict[str, Any]]:
    """Return selected preview items in user-selected order."""
    if len(selected_ids) > max_items:
        raise ValueError(f"Preview selection supports at most {max_items} prefixes.")

    preview_items: list[dict[str, Any]] = []
    for item_id in selected_ids:
        item = items_by_id.get(item_id)
        if item is None:
            continue
        preview_items.append(item)

    return preview_items
