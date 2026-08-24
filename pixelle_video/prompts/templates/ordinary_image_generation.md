---
prompt_id: ordinary_image_generation
version: 1
stage: image_prompt_generation
purpose: Generate a content-only image prompt for each ordinary storyboard frame.
output_contract: JSON object with image_prompts array.
---

Generate exactly one content-only image prompt for each input frame.

# Current Storyboard Frame

{narrations_json}

# Subjects

- Keep every listed subject visible and recognizable.
- If no subject is listed, derive the literal subject from the current frame.
- Do not replace, merge, or omit the main subject.

# Action

- Describe one clear action that expresses the current frame.
- If no action is listed, derive the action directly from the current frame.

# Composition

- Turn the supplied composition information into a clear spatial layout and camera view.
- If no composition is listed, use one simple composition that clearly presents the subject and action.
- Keep the visual focus on the main subject and action.

# Style

- Do not add rendering style, material, palette, lighting, or aesthetic labels.
- The selected style is assembled exactly once by the downstream style projector.

# Output Language

<!-- if output_language_chinese -->
- 必须使用中文。
<!-- endif -->
<!-- if output_language_english -->
- Every image prompt must be written in English.
<!-- endif -->

# Output Format

- Only output JSON: {{"image_prompts": ["..."]}}.
- The array must contain exactly {narrations_count} strings in input order.
- Each string must contain only the current frame, subjects, action, and composition.
