---
prompt_id: storyboard_generation
version: 1
stage: storyboard_generation
purpose: Create a storyboard plan from complete source text.
output_contract: JSON storyboard plan payload.
---

<!-- template-loader:strip # storyboard_generation -->
{{
  "task": "create_storyboard_plan_from_complete_source_text",
  "prompt_language": {prompt_language_json},
  "source_text": {source_text_json},
  "sentences": {sentences_json},
  "count_instruction": {count_instruction_json}
<!-- if use_source_spans -->
  ,"source_spans": {source_spans_json}
<!-- endif -->
  ,"requirements": [
    "Understand the complete source_text before creating frames.",
    "The returned frames must cover the entire source_text in source order.",
    "Do not omit meaningful source_text; only whitespace-only gaps between frames are allowed.",
    "Maintain continuity of style, subjects, and visual logic across all frames.",
    "Do not rewrite or summarize voiceover text; speech and captions are planned separately from source_text.",
    "Do not generate final image prompts.",
    "Return JSON only."
<!-- if use_sentence_indices -->
    ,"Use sentence_indices to specify which sentences each frame covers.",
    "Frames may cover multiple consecutive sentences (e.g., [0, 1, 2]).",
    "Do not split one sentence across multiple frames when using sentence_indices.",
    "All sentence indices must be covered by exactly one frame (no gaps, no overlaps).",
    "When using sentence_indices, omit source_start and source_end entirely unless you can provide both integers together."
<!-- endif -->
<!-- if use_source_spans -->
    ,"Use source_span_indices, not sentence_indices, because the requested frame count exceeds the sentence count.",
    "Each frame must cover one or more consecutive source_spans.",
    "All source_span_indices must be covered by exactly one frame in source order (no gaps, no overlaps).",
    "When using source_span_indices, omit source_start and source_end entirely unless you can provide both integers together."
<!-- endif -->
<!-- if write_chinese_fields -->
    ,"Write visual_goal and prompt_intent in Chinese."
<!-- endif -->
  ],
  "frame_schema": {{
    "source_text": "Text preview covered by this frame (for reference).",
    "visual_goal": {visual_goal_description_json},
    "prompt_intent": "Guidance for later image prompt composition."
<!-- if use_sentence_indices -->
    ,"sentence_indices": "Required: consecutive sentence indices covered by this frame (e.g., [0, 1] or [3])."
<!-- endif -->
<!-- if use_source_spans -->
    ,"source_span_indices": "Required: consecutive source_spans covered by this frame (e.g., [0] or [1, 2])."
<!-- endif -->
  }}
}}
