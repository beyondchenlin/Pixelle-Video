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

STYLE_RESOLUTION_PROMPT = """# Role
You convert one raw image-style prefix into structured backend style metadata.

# Input Prefix
{raw_prefix}

# Output JSON
{{
  "style_kind": "visual_only | ip_world | hybrid",
  "prompt_template": "optional wrapper that contains {{prompt}} exactly once",
  "negative_prompt": "optional negative prompt",
  "style_profile": {{
    "style_kind": "repeat the same value as the top-level style_kind",
    "subject_policy": "how the subject should be preserved or redesigned",
    "shape_language": "the intended silhouette and geometric language",
    "material": "surface or rendering material cues",
    "palette": "dominant color guidance",
    "lighting": "lighting and atmosphere guidance",
    "world_elements": "background props and universe cues",
    "consistency_anchor": "shared multi-frame consistency rule",
    "negative_rules": "things the image prompt should avoid"
  }}
}}

Rules:
- Return JSON only.
- `style_kind` must be one of `visual_only`, `ip_world`, or `hybrid`.
- If `prompt_template` is non-empty it must contain `{{prompt}}` exactly once.
- For `ip_world`, `subject_policy`, `world_elements`, and `consistency_anchor` must be specific.
- For `visual_only`, do not replace the subject with a named IP character.
"""


def build_style_resolution_prompt(raw_prefix: str) -> str:
    return STYLE_RESOLUTION_PROMPT.format(raw_prefix=raw_prefix.strip())
