---
prompt_id: prompt_prefix_generation
version: 1
stage: prompt_prefix_generation
purpose: Generate reusable image prompt prefix candidates.
output_contract: JSON object with items array.
---

<!-- template-loader:strip # prompt_prefix_generation -->
You are generating reusable image prompt prefix presets for Pixelle.

User idea:
{user_idea}

Requirements:
- Return valid JSON only.
- Generate 4 candidates.
- `content` must be English and suitable for image generation models.
- `name` and `note` should be concise user-facing text in {language_hint}.
- `style_category_id` must be one of: {style_ids_csv}
- `scene_category_id` must be one of: {scene_ids_csv}
- Avoid markdown fences and extra narration.

Output shape:
```json
{{
  "items": [
    {{
      "name": "...",
      "content": "...",
      "style_category_id": "...",
      "scene_category_id": "...",
      "note": "..."
    }}
  ]
}}
```
