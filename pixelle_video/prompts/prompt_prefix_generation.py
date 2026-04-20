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
Prompt builder for prompt prefix generation via LLM.
"""

from pixelle_video.config.prompt_prefix_library import get_prompt_prefix_category_options


def build_prompt_prefix_generation_prompt(user_idea: str, language: str = "en_US") -> str:
    """Build the LLM prompt for prompt prefix candidate generation."""
    style_ids, scene_ids = get_prompt_prefix_category_options()
    language_hint = "Chinese" if language == "zh_CN" else "English"

    return f"""You are generating reusable image prompt prefix presets for Pixelle.

User idea:
{user_idea}

Requirements:
- Return valid JSON only.
- Generate 4 candidates.
- `content` must be English and suitable for image generation models.
- `name` and `note` should be concise user-facing text in {language_hint}.
- `style_category_id` must be one of: {", ".join(style_ids)}
- `scene_category_id` must be one of: {", ".join(scene_ids)}
- Avoid markdown fences and extra narration.

Output shape:
{{
  "items": [
    {{
      "name": "...",
      "content": "...",
      "style_category_id": "...",
      "scene_category_id": "...",
      "note": "..."
    }}
  ]
}}"""
