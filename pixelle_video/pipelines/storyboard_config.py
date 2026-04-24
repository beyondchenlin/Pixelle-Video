# Copyright (C) 2025 AIDC-AI
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Storyboard configuration helpers for runtime pipeline construction.
"""

from typing import Any, Dict, Optional

from pixelle_video.render_backend import DEFAULT_RENDER_BACKEND
from pixelle_video.tts_audio_strategy import DEFAULT_TTS_AUDIO_STRATEGY
from pixelle_video.tts_split_strategy import DEFAULT_TTS_SPLIT_MODE

STORYBOARD_RENDER_DEFAULTS: Dict[str, Any] = {
    "tts_batching_mode": "paragraph",
    "tts_audio_strategy": DEFAULT_TTS_AUDIO_STRATEGY,
    "tts_split_mode": DEFAULT_TTS_SPLIT_MODE,
    "tts_batch_max_sentences": 8,
    "tts_batch_max_chars": 220,
    "tts_sentence_joiner_mode": "direct",
    "caption_punctuation_mode": "strip_all",
    "preserve_natural_punctuation": True,
    "max_chars_per_tts_segment": 90,
    "tts_split_overflow_policy": "hard_limit",
    "tts_boundary_search_radius": 20,
    "tts_soft_overflow_chars": 0,
    "tts_audio_boundary_fade_ms": 8,
    "subtitle_alignment_engine": "qwen_forced_aligner",
    "silence_trim_tool": None,
    "silence_trim_margin_ms": 120,
    "render_backend": DEFAULT_RENDER_BACKEND,
    "element_animation_enabled": False,
    "element_animation_backend": "hyperframes_canvas",
    "element_animation_subject_count": 3,
    "element_animation_candidate_limit": 3,
    "element_animation_prompt": None,
    "element_animation_intensity": "medium",
    "element_animation_workflow": "image_sam31_segment.json",
}

ELEMENT_ANIMATION_CONFIG_KEY_MAP = {
    "element_animation_enabled": "enabled",
    "element_animation_backend": "backend",
    "element_animation_subject_count": "subject_count",
    "element_animation_candidate_limit": "candidate_limit",
    "element_animation_prompt": "prompt",
    "element_animation_intensity": "intensity",
    "element_animation_workflow": "workflow",
}


def resolve_storyboard_render_kwargs(
    runtime_config: Optional[Dict[str, Any]],
    request_params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Resolve render-related StoryboardConfig kwargs from runtime config and request params.

    Request params take precedence when explicitly provided; otherwise the configured
    render defaults are used, with built-in fallbacks as the final safety net.
    """
    config = runtime_config or {}
    render_config = config.get("render", {}) or {}
    timing_config = render_config.get("timing", {}) or {}
    element_animation_config = render_config.get("element_animation", {}) or {}
    request_params = request_params or {}

    def pick(name: str, default: Any):
        if name in request_params:
            return request_params[name]
        element_animation_key = ELEMENT_ANIMATION_CONFIG_KEY_MAP.get(name)
        if element_animation_key and element_animation_key in element_animation_config:
            value = element_animation_config[element_animation_key]
            if value is not None:
                return value
        if name in timing_config:
            value = timing_config[name]
            if value is not None:
                return value
        return default

    resolved = {}
    for name, default in STORYBOARD_RENDER_DEFAULTS.items():
        if name == "render_backend":
            resolved[name] = pick(name, render_config.get("backend") or default)
        else:
            resolved[name] = pick(name, default)
    return resolved
