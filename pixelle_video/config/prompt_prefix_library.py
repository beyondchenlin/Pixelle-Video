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

"""Prompt-prefix library defaults, validation, and pure lookup helpers."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from pixelle_video.models.image_style_selection import (
    IMAGE_STYLE_ID_PATTERN,
    IMAGE_STYLE_REVISION_PATTERN,
    image_style_revision,
    normalize_image_style_id,
    normalize_image_style_revision,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_PROMPT_PREFIX_PLACEHOLDER = "resources/prompt_prefix_previews/placeholder.svg"
PROMPT_PREFIX_ID_PATTERN = IMAGE_STYLE_ID_PATTERN
PROMPT_PREFIX_REVISION_PATTERN = IMAGE_STYLE_REVISION_PATTERN


STYLE_CATEGORY_LABELS = {
    "storybook": {"en_US": "Storybook", "zh_CN": "绘本"},
    "flat_illustration": {"en_US": "Flat Illustration", "zh_CN": "扁平插画"},
    "minimal_line_art": {"en_US": "Minimal Line Art", "zh_CN": "极简线稿"},
    "watercolor": {"en_US": "Watercolor", "zh_CN": "水彩手绘"},
    "cartoon_3d": {"en_US": "3D Cartoon", "zh_CN": "3D 卡通"},
    "cinematic_realism": {"en_US": "Cinematic Realism", "zh_CN": "电影感写实"},
    "anime": {"en_US": "Anime", "zh_CN": "日系动漫"},
    "chinese_traditional": {"en_US": "Chinese Traditional", "zh_CN": "国风插画"},
}

SCENE_CATEGORY_LABELS = {
    "childrens_story": {"en_US": "Children's Story", "zh_CN": "儿童故事"},
    "educational_illustration": {"en_US": "Educational Illustration", "zh_CN": "科普配图"},
    "emotional_copywriting": {"en_US": "Emotional Copywriting", "zh_CN": "情感文案"},
    "knowledge_sharing": {"en_US": "Knowledge Sharing", "zh_CN": "知识分享"},
    "commercial_cover": {"en_US": "Commercial Cover", "zh_CN": "商业封面"},
    "short_video_illustration": {"en_US": "Short Video Illustration", "zh_CN": "短视频配图"},
}


@dataclass(frozen=True)
class BuiltinPromptPrefix:
    id: str
    name: str
    content: str
    style_category_id: str
    scene_category_id: str
    note: str
    preview_asset_path: str
    source: str = "builtin"
    is_builtin: bool = True
    created_at: str = "2026-04-20T00:00:00Z"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "content": self.content,
            "style_category_id": self.style_category_id,
            "scene_category_id": self.scene_category_id,
            "source": self.source,
            "is_builtin": self.is_builtin,
            "note": self.note,
            "preview_asset_path": self.preview_asset_path,
            "workflow_preview_assets": {},
            "created_at": self.created_at,
        }


BUILTIN_PROMPT_PREFIXES = [
    BuiltinPromptPrefix(
        id="builtin_childrens_storybook_warm",
        name="Warm Storybook",
        content="warm children's storybook illustration, soft lighting, gentle hand-painted texture, expressive characters, clean composition",
        style_category_id="storybook",
        scene_category_id="childrens_story",
        note="Soft, healing visuals for stories and family-friendly content.",
        preview_asset_path="resources/prompt_prefix_previews/builtin/warm_storybook.svg",
    ),
    BuiltinPromptPrefix(
        id="builtin_flat_knowledge_clean",
        name="Clean Flat Knowledge",
        content="flat illustration, geometric composition, crisp shapes, balanced spacing, clear visual hierarchy, editorial clarity",
        style_category_id="flat_illustration",
        scene_category_id="knowledge_sharing",
        note="Good for knowledge cards and educational explainers.",
        preview_asset_path="resources/prompt_prefix_previews/builtin/clean_flat_knowledge.svg",
    ),
    BuiltinPromptPrefix(
        id="builtin_line_art_emotion_minimal",
        name="Minimal Emotion Line Art",
        content=(
            "strict pure black, white, and single-value gray minimalist 2D contour drawing "
            "across the entire image; uniform thin black outlines, pure white fill areas, "
            "occasional hard-edged flat light-gray blocks, and large white negative space, "
            "with no continuous tone or gradient; every person and celebrity face and body, "
            "skin, clothing, phone and screen, logo, furniture, outdoor view, and visual "
            "identity uses this same graphic treatment; celebrities are simplified iconic "
            "contour characters whose face and skin are flat white shapes defined by only a "
            "few clean lines for the eyes, nose, and mouth plus a recognizable silhouette, "
            "with hair rendered as a solid black shape; zero colored pixels; no photographic "
            "texture, realistic skin detail, tonal face modeling, individual hair strands, "
            "cross-hatching, gradient volumetric lighting, or 3D material; colored scenes "
            "such as sunsets are expressed only through flat grayscale blocks and line density"
        ),
        style_category_id="minimal_line_art",
        scene_category_id="emotional_copywriting",
        note="Simple symbolic visuals for reflective topics.",
        preview_asset_path="resources/prompt_prefix_previews/builtin/minimal_emotion_line_art.svg",
    ),
    BuiltinPromptPrefix(
        id="builtin_watercolor_story_gentle",
        name="Gentle Watercolor Story",
        content="watercolor illustration, soft color bleeding, delicate paper texture, poetic atmosphere, painterly children's book aesthetic",
        style_category_id="watercolor",
        scene_category_id="childrens_story",
        note="A softer painterly look with warmth and texture.",
        preview_asset_path="resources/prompt_prefix_previews/builtin/gentle_watercolor_story.svg",
    ),
    BuiltinPromptPrefix(
        id="builtin_3d_cover_playful",
        name="Playful 3D Cover",
        content="stylized 3D cartoon render, smooth materials, vibrant color accents, friendly shapes, polished commercial cover composition",
        style_category_id="cartoon_3d",
        scene_category_id="commercial_cover",
        note="Useful for playful promo art and commercial thumbnails.",
        preview_asset_path="resources/prompt_prefix_previews/builtin/playful_3d_cover.svg",
    ),
    BuiltinPromptPrefix(
        id="builtin_cinematic_short_video",
        name="Cinematic Short Video",
        content="cinematic realism, dramatic lighting, refined color grading, strong focal subject, polished editorial composition",
        style_category_id="cinematic_realism",
        scene_category_id="short_video_illustration",
        note="A more dramatic, thumbnail-friendly visual style.",
        preview_asset_path="resources/prompt_prefix_previews/builtin/cinematic_short_video.svg",
    ),
    BuiltinPromptPrefix(
        id="builtin_anime_education_bright",
        name="Bright Anime Education",
        content="anime-inspired illustration, clean cel shading, bright palette, readable composition, lively character-driven scene",
        style_category_id="anime",
        scene_category_id="educational_illustration",
        note="Readable educational visuals with lively anime energy.",
        preview_asset_path="resources/prompt_prefix_previews/builtin/bright_anime_education.svg",
    ),
    BuiltinPromptPrefix(
        id="builtin_chinese_traditional_story",
        name="Traditional Chinese Story",
        content="traditional Chinese illustration style, elegant brush-inspired lines, layered atmosphere, refined color harmony, poetic scene design",
        style_category_id="chinese_traditional",
        scene_category_id="childrens_story",
        note="A poetic Chinese-inspired illustration direction.",
        preview_asset_path="resources/prompt_prefix_previews/builtin/traditional_chinese_story.svg",
    ),
]


def build_builtin_prompt_prefix_library_dict() -> dict[str, Any]:
    return {
        "active_prefix_id": BUILTIN_PROMPT_PREFIXES[0].id,
        "items": [item.to_dict() for item in BUILTIN_PROMPT_PREFIXES],
    }


def get_prompt_prefix_category_options() -> tuple[list[str], list[str]]:
    return list(STYLE_CATEGORY_LABELS.keys()), list(SCENE_CATEGORY_LABELS.keys())


def get_prompt_prefix_category_label(category_id: str, category_type: str, language: str = "en_US") -> str:
    label_map = STYLE_CATEGORY_LABELS if category_type == "style" else SCENE_CATEGORY_LABELS
    category = label_map.get(category_id, {})
    return category.get(language) or category.get("en_US") or category_id


def normalize_prompt_prefix_id(prefix_id: Any, *, allow_none: bool = False) -> str | None:
    """Compatibility name for the canonical image-style id validator."""

    return normalize_image_style_id(prefix_id, allow_none=allow_none)


def image_prompt_prefix_revision(content: Any) -> str:
    """Compatibility name for the canonical image-style revision."""

    return image_style_revision(content)


def normalize_prompt_prefix_revision(
    revision: Any,
    *,
    allow_none: bool = False,
) -> str | None:
    """Compatibility name for the canonical image-style revision validator."""

    return normalize_image_style_revision(revision, allow_none=allow_none)


def _read_mapping_or_attr(container: Any, key: str, default: Any = None) -> Any:
    if isinstance(container, dict):
        return container.get(key, default)
    return getattr(container, key, default)


def normalize_prompt_prefix_workflow_preview_entry(entry: Any) -> dict[str, Any] | None:
    """Strictly normalize one workflow preview asset metadata record."""
    if entry is None:
        return None
    if hasattr(entry, "model_dump"):
        entry = entry.model_dump()

    if not isinstance(entry, dict):
        raise ValueError("workflow preview entry must be a mapping with metadata fields")

    asset_path = str(entry.get("asset_path") or "").strip()
    if not asset_path:
        raise ValueError("workflow preview entry asset_path is required")

    reference_prompt = entry.get("reference_prompt")
    if isinstance(reference_prompt, str):
        reference_prompt = reference_prompt.strip() or None
    else:
        reference_prompt = None

    generated_at = entry.get("generated_at")
    if isinstance(generated_at, str):
        generated_at = generated_at.strip() or None
    else:
        generated_at = None

    status = str(entry.get("status") or "").strip() or "ready"
    return {
        "asset_path": asset_path,
        "reference_prompt": reference_prompt,
        "generated_at": generated_at,
        "status": status,
    }


def normalize_prompt_prefix_workflow_preview_assets(entries: Any) -> dict[str, dict[str, Any]]:
    """Strictly normalize a workflow-preview mapping."""
    if entries is None:
        return {}
    if not isinstance(entries, dict):
        raise ValueError("workflow_preview_assets must be a mapping of workflow keys to metadata records")

    normalized_entries: dict[str, dict[str, Any]] = {}
    for workflow_key, entry in entries.items():
        normalized_workflow_key = str(workflow_key).strip()
        if not normalized_workflow_key:
            raise ValueError("workflow_preview_assets contains an empty workflow key")
        normalized_entry = normalize_prompt_prefix_workflow_preview_entry(entry)
        if normalized_entry is None:
            raise ValueError(f"workflow_preview_assets[{normalized_workflow_key!r}] is missing metadata")
        normalized_entries[normalized_workflow_key] = normalized_entry

    return normalized_entries


def build_prompt_prefix_workflow_preview_record(
    asset_path: str,
    reference_prompt: str | None = None,
    generated_at: str | None = None,
    status: str = "ready",
) -> dict[str, Any]:
    """Build one normalized workflow preview record."""
    normalized = normalize_prompt_prefix_workflow_preview_entry(
        {
            "asset_path": asset_path,
            "reference_prompt": reference_prompt,
            "generated_at": generated_at,
            "status": status,
        }
    )
    if normalized is None:
        raise ValueError("asset_path is required for workflow preview record")
    return normalized


def get_prompt_prefix_workflow_preview_asset_path(entry: Any) -> str | None:
    """Return the asset path from one workflow preview entry."""
    normalized_entry = normalize_prompt_prefix_workflow_preview_entry(entry)
    if normalized_entry is None:
        return None
    return normalized_entry["asset_path"]


def get_effective_image_prompt_prefix(image_config: Any) -> str:
    library = _read_mapping_or_attr(image_config, "prompt_prefix_library", None)
    if library is not None:
        active_prefix_id = _read_mapping_or_attr(library, "active_prefix_id", None)
        items = _read_mapping_or_attr(library, "items", [])
        for item in items:
            if _read_mapping_or_attr(item, "id", None) == active_prefix_id:
                content = _read_mapping_or_attr(item, "content", "")
                if content and content.strip():
                    return content.strip()

    return ""


def get_active_image_prompt_prefix_item(image_config: Any) -> Optional[dict[str, Any]]:
    library = _read_mapping_or_attr(image_config, "prompt_prefix_library", None)
    if library is None:
        return None

    active_prefix_id = _read_mapping_or_attr(library, "active_prefix_id", None)
    return get_image_prompt_prefix_item(image_config, active_prefix_id)


def get_image_prompt_prefix_item(
    image_config: Any,
    prefix_id: Optional[str],
) -> Optional[dict[str, Any]]:
    """Return one image style library item by its stable id."""

    normalized_prefix_id = normalize_prompt_prefix_id(prefix_id, allow_none=True)
    if normalized_prefix_id is None:
        return None

    library = _read_mapping_or_attr(image_config, "prompt_prefix_library", None)
    if library is None:
        return None

    items = _read_mapping_or_attr(library, "items", [])
    for item in items:
        if _read_mapping_or_attr(item, "id", None) == normalized_prefix_id:
            return item if isinstance(item, dict) else item.model_dump()

    return None


def get_prompt_prefix_preview_asset(item: dict[str, Any]) -> str:
    """Return a gallery preview asset path or the neutral placeholder."""
    preview_asset_path = (item.get("preview_asset_path") or "").strip()
    if preview_asset_path:
        resolved_path = PROJECT_ROOT / preview_asset_path
        if resolved_path.exists():
            return preview_asset_path
    return DEFAULT_PROMPT_PREFIX_PLACEHOLDER


def _resolve_prompt_prefix_asset_path(asset_path: Any) -> str | None:
    if not isinstance(asset_path, str):
        asset_path = get_prompt_prefix_workflow_preview_asset_path(asset_path)

    normalized_asset_path = (asset_path or "").strip()
    if not normalized_asset_path:
        return None

    resolved_path = PROJECT_ROOT / normalized_asset_path
    if resolved_path.exists():
        return normalized_asset_path
    return None


def resolve_prompt_prefix_gallery_cover(item: dict[str, Any], workflow_key: str | None) -> dict[str, Any]:
    """Resolve the best gallery cover for one prompt-prefix card."""
    normalized_workflow_key = (workflow_key or "").strip()
    workflow_preview_assets = normalize_prompt_prefix_workflow_preview_assets(
        item.get("workflow_preview_assets") or {}
    )

    if normalized_workflow_key:
        current_workflow_record = workflow_preview_assets.get(normalized_workflow_key)
        current_workflow_asset = _resolve_prompt_prefix_asset_path(current_workflow_record)
        if current_workflow_asset:
            return {
                "asset_path": current_workflow_asset,
                "source": "workflow",
                "is_stale": False,
                "workflow_key": normalized_workflow_key,
                "reference_prompt": current_workflow_record.get("reference_prompt") if current_workflow_record else None,
                "generated_at": current_workflow_record.get("generated_at") if current_workflow_record else None,
                "status": current_workflow_record.get("status") if current_workflow_record else None,
            }

    latest_other_asset: tuple[float, str, str, dict[str, Any]] | None = None
    for other_workflow_key, other_record in workflow_preview_assets.items():
        resolved_asset_path = _resolve_prompt_prefix_asset_path(other_record)
        if not resolved_asset_path:
            continue
        asset_mtime = (PROJECT_ROOT / resolved_asset_path).stat().st_mtime
        if latest_other_asset is None or asset_mtime > latest_other_asset[0]:
            latest_other_asset = (asset_mtime, other_workflow_key, resolved_asset_path, other_record)

    if latest_other_asset is not None:
        _, stale_workflow_key, stale_asset_path, stale_record = latest_other_asset
        return {
            "asset_path": stale_asset_path,
            "source": "workflow",
            "is_stale": True,
            "workflow_key": stale_workflow_key,
            "reference_prompt": stale_record.get("reference_prompt"),
            "generated_at": stale_record.get("generated_at"),
            "status": stale_record.get("status"),
        }

    return {
        "asset_path": get_prompt_prefix_preview_asset(item),
        "source": "reference",
        "is_stale": False,
        "workflow_key": None,
        "reference_prompt": None,
        "generated_at": None,
        "status": None,
    }


def filter_prompt_prefix_items(
    items: list[dict[str, Any]],
    style_category_id: Optional[str] = None,
    scene_category_id: Optional[str] = None,
    keyword: str = "",
) -> list[dict[str, Any]]:
    normalized_keyword = keyword.strip().lower()
    filtered: list[dict[str, Any]] = []

    for item in items:
        if style_category_id and item.get("style_category_id") != style_category_id:
            continue
        if scene_category_id and item.get("scene_category_id") != scene_category_id:
            continue
        if normalized_keyword:
            haystack = " ".join(
                str(item.get(field, ""))
                for field in ("name", "content", "note")
            ).lower()
            if normalized_keyword not in haystack:
                continue
        filtered.append(item)

    return filtered
