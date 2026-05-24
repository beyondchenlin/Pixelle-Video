---
prompt_id: storyboard_planning
version: 1
stage: storyboard_planning
purpose: Plan structured storyboard frame metadata from narration inputs.
output_contract: JSON object matching StoryboardPlanningResponse.
---

<!-- template-loader:strip # storyboard_planning -->
{{
  "task": "plan_storyboard_frames",
  "resolved_mode": {resolved_mode_json},
  "prompt_language": {prompt_language_json},
  "consistency_strength": {consistency_strength_json},
  "role_strategy": {role_strategy_json},
  "role_locking_strength": {role_locking_strength_json},
  "shot_strategy": {shot_strategy_json},
  "world_preset": {world_preset_json},
  "shot_preset": {shot_preset_json},
  "required_frame_fields": {required_frame_fields_json},
  "required_output": {required_output_json}
<!-- if has_generation_world_profile -->
  ,"generation_world_profile": {generation_world_profile_json}
<!-- endif -->
<!-- if uses_frame_context -->
  ,"frame_source_texts": {frame_source_texts_json},
  "frame_source_items": {frame_source_items_json}
  {prompt_context_entries}
<!-- endif -->
<!-- if uses_legacy_narrations -->
  ,"narrations": {narrations_json},
  "narration_items": {frame_source_items_json}
<!-- endif -->
  ,"instructions": [
    "Return JSON only."
<!-- if uses_frame_context -->
    ,"Produce exactly one frame plan per frame_source_item.",
    "Use frame_source_items as the authoritative input list and keep exactly the same order.",
    "Use prompt_contexts as the primary source for frame meaning and continuity.",
    "Read plan_source_text before planning individual frames.",
    "Use frame_source_text, visual_goal, prompt_intent, and focus_detail together instead of planning from isolated text alone.",
    "Return every \"scene_id\" as the quoted string from frame_source_items, never a number."
<!-- endif -->
<!-- if uses_legacy_narrations -->
    ,"Produce exactly one frame plan per narration.",
    "Use narration_items as the authoritative input list and keep exactly the same order.",
    "Return every \"scene_id\" as the quoted string from narration_items, never a number."
<!-- endif -->
    ,"Make every array field contain strings only.",
    "Validate the final payload against required_output before returning it.",
    "Do not wrap the JSON in markdown fences."
<!-- if has_generation_world_profile -->
    ,"Use generation_world_profile as the current script world. It refines this request and does not replace protected source subjects."
<!-- endif -->
<!-- if write_chinese_fields -->
    ,"Write narration_fragment, knowledge_goal, focus_detail, and prompt_intent in Chinese."
<!-- endif -->
  ]
}}
