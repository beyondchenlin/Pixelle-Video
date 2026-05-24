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
from pixelle_video.prompts.template_loader import RenderedPrompt, render_prompt_template


def render_style_resolution_prompt(raw_prefix: str) -> RenderedPrompt:
    return render_prompt_template(
        "style_resolution",
        {
            "raw_prefix_json": json.dumps(raw_prefix.strip(), ensure_ascii=False),
            "required_output_json": json.dumps(
                StyleResolutionResponse.model_json_schema(),
                ensure_ascii=False,
                indent=2,
            ),
        },
    )


def build_style_resolution_prompt(raw_prefix: str) -> str:
    return render_style_resolution_prompt(raw_prefix).text
