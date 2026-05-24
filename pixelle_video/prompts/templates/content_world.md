---
prompt_id: content_world
version: 1
stage: content_world_planning
purpose: Extract the current generation world profile from source text and hints.
output_contract: JSON object matching ContentWorldProfile fields.
---

<!-- template-loader:strip # content_world -->
{{
  "task": "extract_current_generation_world_profile",
  "source_text": {source_text_json},
  "generation_world_hint": {generation_world_hint_json},
  "ip_default_world_hint": {ip_world_hint_json},
  "world_preset": {world_preset_json},
  "required_output": {{
    "summary": "string",
    "time_space": "string",
    "visual_environment": "string",
    "atmosphere": "string",
    "cultural_context": "string",
    "story_constraints": "string",
    "ip_integration_guidance": "string"
  }},
  "instructions": [
    "Return JSON only.",
    "Treat generation_world_hint as the highest priority when present.",
    "Use ip_default_world_hint only as compatibility guidance, not as the current story world.",
    "Do not output markdown fences.",
    "Do not output hex color codes.",
    "Do not copy field names into natural language values."
  ]
}}
