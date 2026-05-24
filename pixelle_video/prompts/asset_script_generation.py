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
Asset-based video script generation prompt.
"""

from __future__ import annotations

import json

from pixelle_video.models.asset_script import AssetCatalogEntry, AssetScriptResponse
from pixelle_video.prompts.template_loader import RenderedPrompt, render_prompt_template


def render_asset_script_prompt(
    intent: str,
    duration: int,
    assets: list[AssetCatalogEntry],
    title: str = "",
) -> RenderedPrompt:
    return render_prompt_template(
        "asset_script_generation",
        {
            "intent_json": json.dumps(intent.strip(), ensure_ascii=False),
            "duration_seconds_json": json.dumps(duration, ensure_ascii=False),
            "title_json": json.dumps(title.strip(), ensure_ascii=False),
            "available_assets_json": json.dumps(
                [asset.to_prompt_dict() for asset in assets],
                ensure_ascii=False,
                indent=2,
            ),
            "required_output_json": json.dumps(
                AssetScriptResponse.model_json_schema(),
                ensure_ascii=False,
                indent=2,
            ),
        },
    )


def build_asset_script_prompt(
    intent: str,
    duration: int,
    assets: list[AssetCatalogEntry],
    title: str = "",
) -> str:
    return render_asset_script_prompt(intent, duration, assets, title=title).text
