---
prompt_id: style_conversion
version: 1
stage: style_conversion
purpose: Convert a custom style description into an English image prompt prefix.
output_contract: Plain English image prompt text.
---

<!-- template-loader:strip # style_conversion -->
Convert this style description into a detailed image generation prompt for Stable Diffusion/FLUX:

Style Description: {description}

Requirements:
- Focus on visual elements, colors, lighting, mood, atmosphere
- Be specific and detailed
- Use professional photography/art terminology
- Output ONLY the prompt in English (no explanations)
- Keep it under 100 words
- Use comma-separated descriptive phrases

Image Prompt:
