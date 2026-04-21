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
    request_params = request_params or {}

    def pick(name: str, default: Any):
        value = request_params.get(name)
        if value is not None:
            return value
        value = timing_config.get(name)
        if value is not None:
            return value
        return default

    return {
        "tts_batching_mode": pick("tts_batching_mode", "paragraph"),
        "tts_batch_max_sentences": pick("tts_batch_max_sentences", 8),
        "tts_batch_max_chars": pick("tts_batch_max_chars", 220),
        "subtitle_alignment_engine": pick("subtitle_alignment_engine", "qwen_forced_aligner"),
        "silence_trim_tool": pick("silence_trim_tool", None),
        "silence_trim_margin_ms": pick("silence_trim_margin_ms", 120),
        "render_backend": pick("render_backend", render_config.get("backend", "hyperframes")),
    }
