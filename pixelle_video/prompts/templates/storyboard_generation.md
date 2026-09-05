---
prompt_id: storyboard_generation
version: 3
stage: storyboard_generation
purpose: Create a storyboard plan from complete source text.
output_contract: JSON storyboard plan payload with visible subject fields.
---

<!-- template-loader:strip # storyboard_generation -->
{{
  "task": "create_storyboard_plan_from_complete_source_text",
  "prompt_language": {prompt_language_json},
  "source_text": {source_text_json},
  "sentences": {sentences_json}
<!-- if manual_count_mode -->
  ,"count_instruction": "Create exactly {requested_scene_count} storyboard frames."
<!-- endif -->
<!-- if auto_count_mode -->
  ,"count_instruction": "Choose the best storyboard frame count between {min_scene_count} and {max_scene_count}."
<!-- endif -->
<!-- if use_source_spans -->
  ,"source_spans": {source_spans_json}
<!-- endif -->
  ,"requirements": [
    "Understand the complete source_text before creating frames.",
<!-- if information_design -->
    "按信息设计镜头：先明确整段的核心主张，再按背景、动作、物证、对比、因果与结果的变化划分信息单元；不要机械地一句配一张图。",
    "连续表达同一主张的句子可以合为一镜；出现新的动作、阶段、决定性物证或因果结果时再切镜，完整保持原文顺序与覆盖。",
    "visual_goal 写清这一镜新增的信息及观众应当看懂的事实；prompt_intent 用自然文本说明一个可见静止瞬间、景别视角、主体关系和与相邻镜头的承接或变化。",
    "不同镜头不能只重复人物站立、思考或观看电脑等通用姿态。没有事实依据时不得为了变化虚构事件。",
    "同一场景保持人物、地点和关键物品，跨时间或地点明确改变环境；不为镜头强行添加系列吉祥物。",
<!-- endif -->
    "The returned frames must cover the entire source_text in source order.",
    "Do not omit meaningful source_text; only whitespace-only gaps between frames are allowed.",
    "Maintain continuity of style, subjects, and visual logic across all frames.",
    "Do not rewrite or summarize voiceover text; speech and captions are planned separately from source_text.",
    "Do not generate final image prompts.",
    "For every frame, identify one concise primary_subject that must remain visibly present in the later image.",
    "Return secondary_subjects as a concise list of other visible people, objects, places, or symbols that must not be lost.",
    "Derive primary_subject and secondary_subjects from this frame's covered source text and visual meaning; do not add a mascot, logo, watermark, or unrelated decorative carrier.",
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
<!-- if write_chinese_fields -->
    "visual_goal": "这一帧需要传达的视觉重点",
<!-- endif -->
<!-- if write_english_fields -->
    "visual_goal": "What this frame should communicate visually.",
<!-- endif -->
    "prompt_intent": "Guidance for later image prompt composition.",
    "primary_subject": "One concise visible subject that the later image must preserve.",
    "secondary_subjects": ["Other concise visible subjects that the later image must preserve."]
<!-- if use_sentence_indices -->
    ,"sentence_indices": "Required: consecutive sentence indices covered by this frame (e.g., [0, 1] or [3])."
<!-- endif -->
<!-- if use_source_spans -->
    ,"source_span_indices": "Required: consecutive source_spans covered by this frame (e.g., [0] or [1, 2])."
<!-- endif -->
  }}
}}
