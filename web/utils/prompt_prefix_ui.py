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
import re
from typing import Any, MutableMapping
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from pixelle_video.config.prompt_prefix_library import (
    PROJECT_ROOT,
    SCENE_CATEGORY_LABELS,
    STYLE_CATEGORY_LABELS,
    get_prompt_prefix_category_label,
)
from web.utils.preview_media import load_preview_media

CUSTOM_PROMPT_PREFIX_PREVIEW_RELATIVE_DIR = Path("resources/prompt_prefix_previews/custom")
DEFAULT_PROMPT_PREFIX_PREVIEW_SUFFIX = ".png"
PROMPT_PREFIX_MANUAL_DRAFT_ID_KEY = "prompt_prefix_manual_draft_id"


def create_prompt_prefix_item(
    name: str,
    content: str,
    style_category_id: str,
    scene_category_id: str,
    note: str = "",
    source: str = "manual",
    item_id: str | None = None,
    preview_asset_path: str | None = None,
    workflow_preview_assets: dict[str, str] | None = None,
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
        "workflow_preview_assets": {
            str(workflow_key).strip(): str(asset_path).strip()
            for workflow_key, asset_path in (workflow_preview_assets or {}).items()
            if str(workflow_key).strip() and str(asset_path).strip()
        },
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


def _get_custom_prompt_prefix_preview_dir() -> Path:
    return PROJECT_ROOT / CUSTOM_PROMPT_PREFIX_PREVIEW_RELATIVE_DIR


def _infer_prompt_prefix_preview_suffix(source_name: str) -> str:
    candidates = [source_name]
    if source_name.startswith(("http://", "https://")):
        parsed = urlparse(source_name)
        filename = parse_qs(parsed.query).get("filename", [None])[0]
        if filename:
            candidates.insert(0, filename)
        if parsed.path:
            candidates.append(parsed.path)

    for candidate in candidates:
        suffix = Path(candidate or "").suffix.lower()
        if suffix in {".png", ".jpg", ".jpeg", ".webp", ".svg"}:
            return suffix

    return DEFAULT_PROMPT_PREFIX_PREVIEW_SUFFIX


def _normalize_prompt_prefix_preview_stem_token(token: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", token.strip())
    return normalized.strip("_") or "default"


def _resolve_custom_prompt_prefix_preview_path(preview_asset_path: str | None) -> Path | None:
    normalized_asset_path = (preview_asset_path or "").strip()
    if not normalized_asset_path:
        return None

    candidate_path = Path(normalized_asset_path)
    if candidate_path.is_absolute():
        return None

    resolved_path = (PROJECT_ROOT / candidate_path).resolve()
    custom_root = _get_custom_prompt_prefix_preview_dir().resolve()
    try:
        resolved_path.relative_to(custom_root)
    except ValueError:
        return None
    return resolved_path


def _persist_prompt_prefix_preview_bytes(
    preview_bytes: bytes,
    item_id: str,
    source_name: str,
    previous_preview_asset_path: str | None = None,
    asset_stem_suffix: str | None = None,
) -> str:
    output_dir = _get_custom_prompt_prefix_preview_dir()
    output_dir.mkdir(parents=True, exist_ok=True)

    suffix = _infer_prompt_prefix_preview_suffix(source_name)
    normalized_suffix = f"__{_normalize_prompt_prefix_preview_stem_token(asset_stem_suffix)}" if asset_stem_suffix else ""
    output_path = output_dir / f"{item_id}{normalized_suffix}{suffix}"
    output_path.write_bytes(preview_bytes)

    relative_output_path = output_path.relative_to(PROJECT_ROOT).as_posix()
    if previous_preview_asset_path and previous_preview_asset_path != relative_output_path:
        delete_prompt_prefix_preview_asset(previous_preview_asset_path)

    return relative_output_path


def get_prompt_prefix_form_item_id(
    session_state: MutableMapping[str, Any],
    editing_item_id: str | None = None,
) -> str:
    """Return a stable item id for prompt-prefix forms across Streamlit reruns."""
    if editing_item_id:
        return editing_item_id

    draft_id = session_state.get(PROMPT_PREFIX_MANUAL_DRAFT_ID_KEY)
    if isinstance(draft_id, str) and draft_id.strip():
        return draft_id

    draft_id = f"manual-{uuid4().hex[:12]}"
    session_state[PROMPT_PREFIX_MANUAL_DRAFT_ID_KEY] = draft_id
    return draft_id


def clear_prompt_prefix_form_item_id(session_state: MutableMapping[str, Any]):
    """Drop the current manual draft id so the next create flow starts fresh."""
    session_state.pop(PROMPT_PREFIX_MANUAL_DRAFT_ID_KEY, None)


def delete_prompt_prefix_preview_asset(preview_asset_path: str | None) -> bool:
    """Delete one custom prompt-prefix preview asset if it exists."""
    resolved_path = _resolve_custom_prompt_prefix_preview_path(preview_asset_path)
    if resolved_path is None or not resolved_path.exists():
        return False

    resolved_path.unlink()
    return True


def clone_prompt_prefix_preview_asset(
    preview_asset_path: str | None,
    item_id: str,
) -> str | None:
    """Clone one custom preview asset for a duplicated item, preserving builtins by reference."""
    resolved_path = _resolve_custom_prompt_prefix_preview_path(preview_asset_path)
    if resolved_path is None:
        return preview_asset_path.strip() if isinstance(preview_asset_path, str) and preview_asset_path.strip() else None
    if not resolved_path.exists():
        return None

    return _persist_prompt_prefix_preview_bytes(
        preview_bytes=resolved_path.read_bytes(),
        item_id=item_id,
        source_name=resolved_path.name,
    )


def persist_uploaded_prompt_prefix_preview(
    uploaded_file,
    item_id: str,
    previous_preview_asset_path: str | None = None,
) -> str | None:
    """Persist one uploaded preview asset and return a repo-relative path."""
    if uploaded_file is None:
        return None

    return _persist_prompt_prefix_preview_bytes(
        preview_bytes=uploaded_file.getvalue(),
        item_id=item_id,
        source_name=uploaded_file.name or DEFAULT_PROMPT_PREFIX_PREVIEW_SUFFIX,
        previous_preview_asset_path=previous_preview_asset_path,
    )


def persist_generated_prompt_prefix_preview(
    preview_media_path: str | None,
    item_id: str,
    previous_preview_asset_path: str | None = None,
) -> str | None:
    """Persist one generated preview image and return a repo-relative path."""
    normalized_preview_media_path = (preview_media_path or "").strip()
    if not normalized_preview_media_path:
        return None

    preview_media = load_preview_media(normalized_preview_media_path, "image")
    return _persist_prompt_prefix_preview_bytes(
        preview_bytes=preview_media.data,
        item_id=item_id,
        source_name=normalized_preview_media_path,
        previous_preview_asset_path=previous_preview_asset_path,
    )


def persist_generated_prompt_prefix_workflow_preview(
    preview_media_path: str | None,
    item_id: str,
    workflow_key: str,
    previous_preview_asset_path: str | None = None,
) -> str | None:
    """Persist one generated preview image for a specific workflow and return a repo-relative path."""
    normalized_preview_media_path = (preview_media_path or "").strip()
    normalized_workflow_key = (workflow_key or "").strip()
    if not normalized_preview_media_path or not normalized_workflow_key:
        return None

    preview_media = load_preview_media(normalized_preview_media_path, "image")
    return _persist_prompt_prefix_preview_bytes(
        preview_bytes=preview_media.data,
        item_id=item_id,
        source_name=normalized_preview_media_path,
        previous_preview_asset_path=previous_preview_asset_path,
        asset_stem_suffix=normalized_workflow_key,
    )
