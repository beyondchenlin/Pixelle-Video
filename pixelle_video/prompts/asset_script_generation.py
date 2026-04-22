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


def build_asset_script_prompt(
    intent: str,
    duration: int,
    assets: list[AssetCatalogEntry],
    title: str = "",
) -> str:
    payload = {
        "task": "plan_asset_video_script",
        "intent": intent.strip(),
        "duration_seconds": duration,
        "title": title.strip(),
        "available_assets": [asset.to_prompt_dict() for asset in assets],
        "required_output": AssetScriptResponse.model_json_schema(),
        "instructions": [
            "Detect the user's input language and keep all narrations in that same language unless the intent explicitly asks for another output language.",
            "Determine a scene count that reasonably matches the target duration, typically 5-15 seconds per scene.",
            "Assign exactly one asset_id from available_assets to each scene.",
            "Return every asset_id exactly as provided in available_assets. Never invent, rewrite, or partially match asset ids.",
            "Each scene should contain 1-3 narration sentences.",
            "Try to use all available assets when it improves coverage, but asset reuse is allowed when necessary.",
            "Total duration across scenes should approximately match duration_seconds.",
            "Validate the final payload against required_output before returning it.",
            "Return JSON only.",
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)
