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
Prompt builder for structured style resolution.
"""

from __future__ import annotations

import json

from pixelle_video.models.style_resolution import StyleResolutionResponse


def build_style_resolution_prompt(raw_prefix: str) -> str:
    payload = {
        "task": "resolve_style_prefix",
        "raw_prefix": raw_prefix.strip(),
        "required_output": StyleResolutionResponse.model_json_schema(),
        "instructions": [
            "Return JSON only.",
            "Resolve the prefix into backend-ready style metadata.",
            "Return style_profile.style_kind identical to the top-level style_kind.",
            "If prompt_template is non-empty it must contain {prompt} exactly once.",
            "Use concise but specific strings for every style_profile field.",
            "Do not leave any style_profile field empty.",
            "For ip_world, subject_policy, world_elements, and consistency_anchor must describe the persistent world rules.",
            "For visual_only, preserve the subject semantics instead of replacing it with a named IP character.",
            "Validate the final payload against required_output before returning it.",
            "Do not wrap the JSON in markdown fences.",
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)
