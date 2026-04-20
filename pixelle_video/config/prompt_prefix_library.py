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
Prompt prefix library defaults and pure helpers.
"""

from dataclasses import dataclass
from typing import Any, Optional


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
    ),
    BuiltinPromptPrefix(
        id="builtin_flat_knowledge_clean",
        name="Clean Flat Knowledge",
        content="flat illustration, geometric composition, crisp shapes, balanced spacing, clear visual hierarchy, editorial clarity",
        style_category_id="flat_illustration",
        scene_category_id="knowledge_sharing",
        note="Good for knowledge cards and educational explainers.",
    ),
    BuiltinPromptPrefix(
        id="builtin_line_art_emotion_minimal",
        name="Minimal Emotion Line Art",
        content="minimal line art, elegant contour drawing, lots of negative space, subtle emotional tone, clean monochrome illustration",
        style_category_id="minimal_line_art",
        scene_category_id="emotional_copywriting",
        note="Simple symbolic visuals for reflective topics.",
    ),
    BuiltinPromptPrefix(
        id="builtin_watercolor_story_gentle",
        name="Gentle Watercolor Story",
        content="watercolor illustration, soft color bleeding, delicate paper texture, poetic atmosphere, painterly children's book aesthetic",
        style_category_id="watercolor",
        scene_category_id="childrens_story",
        note="A softer painterly look with warmth and texture.",
    ),
    BuiltinPromptPrefix(
        id="builtin_3d_cover_playful",
        name="Playful 3D Cover",
        content="stylized 3D cartoon render, smooth materials, vibrant color accents, friendly shapes, polished commercial cover composition",
        style_category_id="cartoon_3d",
        scene_category_id="commercial_cover",
        note="Useful for playful promo art and commercial thumbnails.",
    ),
    BuiltinPromptPrefix(
        id="builtin_cinematic_short_video",
        name="Cinematic Short Video",
        content="cinematic realism, dramatic lighting, refined color grading, strong focal subject, polished editorial composition",
        style_category_id="cinematic_realism",
        scene_category_id="short_video_illustration",
        note="A more dramatic, thumbnail-friendly visual style.",
    ),
    BuiltinPromptPrefix(
        id="builtin_anime_education_bright",
        name="Bright Anime Education",
        content="anime-inspired illustration, clean cel shading, bright palette, readable composition, lively character-driven scene",
        style_category_id="anime",
        scene_category_id="educational_illustration",
        note="Readable educational visuals with lively anime energy.",
    ),
    BuiltinPromptPrefix(
        id="builtin_chinese_traditional_story",
        name="Traditional Chinese Story",
        content="traditional Chinese illustration style, elegant brush-inspired lines, layered atmosphere, refined color harmony, poetic scene design",
        style_category_id="chinese_traditional",
        scene_category_id="childrens_story",
        note="A poetic Chinese-inspired illustration direction.",
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


def get_effective_image_prompt_prefix(image_config: Any) -> str:
    library = getattr(image_config, "prompt_prefix_library", None)
    if library is not None:
        active_prefix_id = getattr(library, "active_prefix_id", None)
        items = getattr(library, "items", [])
        for item in items:
            if getattr(item, "id", None) == active_prefix_id:
                content = getattr(item, "content", "")
                if content and content.strip():
                    return content.strip()

    legacy_prefix = getattr(image_config, "prompt_prefix", "") or ""
    return legacy_prefix.strip()


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
