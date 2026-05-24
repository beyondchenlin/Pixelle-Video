---
prompt_id: storyboard_repair
version: 2026-05-24
stage: smart_storyboard_generation
purpose: Repair an invalid smart storyboard response while preserving the original storyboard contract.
output_contract: valid SmartStoryboardPlanResponse JSON object
---
# Original Storyboard Prompt

{original_prompt}

# Repair the previous storyboard response

The previous response was invalid: {reason}

# Repair requirements

- Return JSON only.
- Return a corrected JSON object that satisfies the same schema and requirements.
- Preserve the original source-text coverage and storyboard planning rules.
- Do not add Markdown fences, commentary, headings, or extra text outside the JSON object.
