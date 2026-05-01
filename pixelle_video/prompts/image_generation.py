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
Image prompt generation template

For generating image prompts from storyboard frame context.
"""

import json
from typing import Any, List, Optional

from pixelle_video.models.prompt_context import PromptContextInput, prompt_context_payload
from pixelle_video.prompt_language import (
    CHINESE_PROMPT_LANGUAGE,
    DEFAULT_PROMPT_LANGUAGE,
    PromptLanguage,
    normalize_prompt_language,
)

# ==================== PRESET IMAGE STYLES ====================
# Predefined visual styles for different use cases

IMAGE_STYLE_PRESETS = {
    "stick_figure": {
        "name": "Stick Figure Sketch",
        "description": "stick figure style sketch, black and white lines, pure white background, minimalist hand-drawn feel",
        "use_case": "General scenes, simple and intuitive"
    },
    
    "minimal": {
        "name": "Minimalist Abstract",
        "description": "minimalist abstract art, geometric shapes, clean composition, modern design, soft pastel colors",
        "use_case": "Modern, artistic feel"
    },
    
    "concept": {
        "name": "Conceptual Visual",
        "description": "conceptual visual metaphors, symbolic elements, thought-provoking imagery, artistic interpretation",
        "use_case": "Deep content, philosophical thinking"
    },
}

# Default preset
DEFAULT_IMAGE_STYLE = "stick_figure"


IMAGE_PROMPT_GENERATION_PROMPT = """# Role Definition
You are a professional visual creative designer, skilled at creating expressive and symbolic image prompts for video scripts, transforming abstract concepts into concrete visual scenes.

# Core Task
Based on the existing video script, create corresponding **{output_language_label}** image prompts for each storyboard frame's source text and visual goal, ensuring visual scenes match the intended content and enhance audience understanding and memory.

**Important: The input contains {narrations_count} storyboard frame source texts. You must generate one corresponding image prompt for each frame, totaling {narrations_count} image prompts.**

# Input Style Profile
{style_profile_json}

# Input Content
{narrations_json}

# Frame-Aware Context Contract
- When `prompt_contexts` is present, Use prompt_contexts as the primary source for image prompt generation.
- Read `plan_source_text` first to understand the complete script and maintain global meaning.
- Use each frame's `frame_source_text`, `visual_goal`, `prompt_intent`, and `focus_detail` together; do not infer the image from an isolated text fragment alone.
- Preserve continuity across frames by respecting shared subjects, world elements, and any `locked_fields` in the matching prompt_context.

# Output Requirements

## Image Prompt Specifications
- Language: **{language_requirement}**
- Description structure: scene + character action + emotion + symbolic elements
- Description length: {description_length_guidance}
- If a style profile is provided, subject design, material, palette, lighting, world elements, and consistency must obey that style profile first
- When `style_kind` is `ip_world`, redesign the subject into the target universe without replacing the subject semantics

## Visual Creative Requirements
- Each image must accurately reflect the specific content and emotion of the corresponding frame source text
- Use symbolic techniques to visualize abstract concepts (e.g., use paths to represent life choices, chains to represent constraints, etc.)
- Scenes should express rich emotions and actions to enhance visual impact
- Highlight themes through composition and element arrangement, avoid overly literal representations

## Key English Vocabulary Reference
- Symbolic elements: symbolic elements
- Expression: expression / facial expression
- Action: action / gesture / movement
- Scene: scene / setting
- Atmosphere: atmosphere / mood

## Visual and Copy Coordination Principles
- Images should serve the copy, becoming a visual extension of the copy content
- Avoid visual elements unrelated to or contradicting the copy content
- Choose visual presentation methods that best enhance the persuasiveness of the copy
- Ensure the audience can quickly understand the core viewpoint of the copy through images

## Creative Guidance
1. **Phenomenon Description Copy**: Use intuitive scenes to represent social phenomena
2. **Cause Analysis Copy**: Use visual metaphors of cause-and-effect relationships to represent internal logic
3. **Impact Argumentation Copy**: Use consequence scenes or contrast techniques to represent the degree of impact
4. **In-depth Discussion Copy**: Use concretization of abstract concepts to represent deep thinking
5. **Conclusion Inspiration Copy**: Use open-ended scenes or guiding elements to represent inspiration

# Output Format
Strictly output in the following JSON format, **image prompts must be in {output_language_label}**:

```json
{{
  "image_prompts": [
    "{example_prompt}",
    "{example_prompt}"
  ]
}}
```

# Important Reminders
1. Only output JSON format content, do not add any explanations
2. Ensure JSON format is strictly correct and can be directly parsed by the program
3. Frame-aware input uses {{"frame_source_texts": [source text array]}} format, output is {{"image_prompts": [image prompt array]}} format
4. **The output image_prompts array must contain exactly {narrations_count} elements, corresponding one-to-one with the input frame source texts**
5. **{language_requirement}**
6. Image prompts must accurately reflect the specific content and emotion of the corresponding frame source text
7. Each image must be creative and visually impactful, avoid being monotonous
8. Ensure visual scenes can enhance the persuasiveness of the copy and audience understanding

Now, please create {narrations_count} corresponding **{output_language_label}** image prompts for the above {narrations_count} storyboard frames. Only output JSON, no other content.
"""


def build_image_prompt_prompt(
    narrations: List[str],
    min_words: int,
    max_words: int,
    style_profile: Optional[dict[str, Any]] = None,
    prompt_contexts: Optional[PromptContextInput] = None,
    prompt_language: PromptLanguage = DEFAULT_PROMPT_LANGUAGE,
) -> str:
    """
    Build image prompt generation prompt
    
    Note: Style/prefix will be applied later via prompt_prefix in config.
    
    Args:
        narrations: List of narrations
        min_words: Minimum word count
        max_words: Maximum word count
    
    Returns:
        Formatted prompt for LLM
    
    Example:
        >>> build_image_prompt_prompt(narrations, 50, 100)
    """
    context_payload = prompt_context_payload(prompt_contexts, len(narrations))
    payload: dict[str, Any] = (
        {"frame_source_texts": narrations}
        if context_payload is not None
        else {"narrations": narrations}
    )
    if context_payload is not None:
        payload.update(context_payload)
    narrations_json = json.dumps(payload, ensure_ascii=False, indent=2)
    style_profile_json = json.dumps(style_profile or None, ensure_ascii=False, indent=2)
    resolved_prompt_language = normalize_prompt_language(prompt_language)
    if resolved_prompt_language == CHINESE_PROMPT_LANGUAGE:
        output_language_label = "Chinese"
        language_requirement = "必须使用中文"
        description_length_guidance = (
            "确保描述清晰、完整且有创意，篇幅与 50-100 个英文单词的细节密度相当。"
        )
        example_prompt = "[详细中文图片提示词，遵循风格要求]"
    else:
        output_language_label = "English"
        language_requirement = "Image prompts must use English"
        description_length_guidance = (
            "Ensure clear, complete, and creative descriptions (recommended 50-100 English words)"
        )
        example_prompt = "[detailed English image prompt following the style requirements]"
    
    return IMAGE_PROMPT_GENERATION_PROMPT.format(
        style_profile_json=style_profile_json,
        narrations_json=narrations_json,
        narrations_count=len(narrations),
        min_words=min_words,
        max_words=max_words,
        output_language_label=output_language_label,
        language_requirement=language_requirement,
        description_length_guidance=description_length_guidance,
        example_prompt=example_prompt,
    )
