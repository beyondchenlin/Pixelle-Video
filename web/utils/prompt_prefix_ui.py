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
Pure UI helpers for prompt prefix library interactions.
"""

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from pixelle_video.config.prompt_prefix_library import (
    SCENE_CATEGORY_LABELS,
    STYLE_CATEGORY_LABELS,
    get_prompt_prefix_category_label,
)

CUSTOM_PROMPT_PREFIX_PREVIEW_DIR = Path("resources/prompt_prefix_previews/custom")
DEFAULT_PROMPT_PREFIX_PREVIEW_SUFFIX = ".png"


def create_prompt_prefix_item(
    name: str,
    content: str,
    style_category_id: str,
    scene_category_id: str,
    note: str = "",
    source: str = "manual",
    item_id: str | None = None,
    preview_asset_path: str | None = None,
) -> dict[str, str | bool | None]:
    """Create a normalized prompt prefix library item payload."""
    return {
        "id": item_id or f"{source}-{uuid4().hex[:12]}",
        "name": name.strip(),
        "content": content.strip(),
        "style_category_id": style_category_id,
        "scene_category_id": scene_category_id,
        "source": source,
        "is_builtin": False,
        "note": note.strip(),
        "preview_asset_path": preview_asset_path.strip() if preview_asset_path else None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def get_localized_prompt_prefix_category_options(language: str = "en_US") -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Return localized category options for style and scene selectors."""
    style_options = [
        {"id": category_id, "label": get_prompt_prefix_category_label(category_id, "style", language)}
        for category_id in STYLE_CATEGORY_LABELS
    ]
    scene_options = [
        {"id": category_id, "label": get_prompt_prefix_category_label(category_id, "scene", language)}
        for category_id in SCENE_CATEGORY_LABELS
    ]
    return style_options, scene_options


def toggle_prompt_prefix_preview_selection(selected_ids: list[str], item_id: str) -> list[str]:
    """Toggle one preview selection while preserving order for remaining ids."""
    if item_id in selected_ids:
        return [selected_id for selected_id in selected_ids if selected_id != item_id]
    return [*selected_ids, item_id]


def sanitize_prompt_prefix_preview_selection(selected_ids: list[str], valid_ids: set[str]) -> list[str]:
    """Drop stale preview ids and de-duplicate while preserving selection order."""
    sanitized: list[str] = []
    seen: set[str] = set()

    for item_id in selected_ids:
        if item_id not in valid_ids or item_id in seen:
            continue
        sanitized.append(item_id)
        seen.add(item_id)

    return sanitized


def persist_uploaded_prompt_prefix_preview(uploaded_file, item_id: str) -> str | None:
    """Persist one uploaded preview asset and return a repo-relative path."""
    if uploaded_file is None:
        return None

    suffix = Path(uploaded_file.name or "").suffix.lower() or DEFAULT_PROMPT_PREFIX_PREVIEW_SUFFIX
    if suffix not in {".png", ".jpg", ".jpeg", ".webp", ".svg"}:
        suffix = DEFAULT_PROMPT_PREFIX_PREVIEW_SUFFIX

    CUSTOM_PROMPT_PREFIX_PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    output_path = CUSTOM_PROMPT_PREFIX_PREVIEW_DIR / f"{item_id}{suffix}"
    output_path.write_bytes(uploaded_file.getvalue())
    return output_path.as_posix()
