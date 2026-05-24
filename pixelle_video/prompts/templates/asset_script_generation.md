---
prompt_id: asset_script_generation
version: 1
stage: asset_script_generation
purpose: Plan an asset-based video script from available catalog assets.
output_contract: JSON object matching AssetScriptResponse.
---

<!-- template-loader:strip # asset_script_generation -->
{{
  "task": "plan_asset_video_script",
  "intent": {intent_json},
  "duration_seconds": {duration_seconds_json},
  "title": {title_json},
  "available_assets": {available_assets_json},
  "required_output": {required_output_json},
  "instructions": [
    "Detect the user's input language and keep all narrations in that same language unless the intent explicitly asks for another output language.",
    "Determine a scene count that reasonably matches the target duration, typically 5-15 seconds per scene.",
    "Assign exactly one asset_id from available_assets to each scene.",
    "Return every asset_id exactly as provided in available_assets. Never invent, rewrite, or partially match asset ids.",
    "Each scene should contain 1-3 narration sentences.",
    "Try to use all available assets when it improves coverage, but asset reuse is allowed when necessary.",
    "Total duration across scenes should approximately match duration_seconds.",
    "Validate the final payload against required_output before returning it.",
    "Return JSON only."
  ]
}}
