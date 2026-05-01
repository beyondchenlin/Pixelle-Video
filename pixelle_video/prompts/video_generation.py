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
Video prompt generation template

For generating video prompts from storyboard frame context.
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

VIDEO_PROMPT_GENERATION_PROMPT = """# Role Definition
You are a professional video creative designer, skilled at creating dynamic and expressive video generation prompts for video scripts, transforming narrative content into vivid video scenes.

# Core Task
Based on the existing video script, create corresponding **{output_language_label}** video generation prompts for each storyboard frame's source text and visual goal, ensuring video scenes match the intended content and enhance audience understanding and memory through dynamic visuals.

**Important: The input contains {narrations_count} storyboard frame source texts. You must generate one corresponding video prompt for each frame, totaling {narrations_count} video prompts.**

# Input Style Profile
{style_profile_json}

# Input Content
{narrations_json}

# Frame-Aware Context Contract
- When `prompt_contexts` is present, Use prompt_contexts as the primary source for video prompt generation.
- Read `plan_source_text` first to understand the complete script and maintain global meaning.
- Use each frame's `frame_source_text`, `visual_goal`, `prompt_intent`, and `focus_detail` together; do not infer the video from an isolated text fragment alone.
- Preserve continuity across frames by respecting shared subjects, world elements, camera logic, and any `locked_fields` in the matching prompt_context.

# Output Requirements

## Video Prompt Specifications
- Language: **{language_requirement}**
- Description structure: scene + character action + camera movement + emotion + atmosphere
- Description length: {description_length_guidance}
- Dynamic elements: Emphasize actions, movements, changes, and other dynamic effects
- If a style profile is provided, subject design, material, palette, lighting, world elements, and consistency must obey that style profile first
- When `style_kind` is `ip_world`, redesign the subject into the target universe without replacing the subject semantics

## Visual Creative Requirements
- Each video must accurately reflect the specific content and emotion of the corresponding storyboard frame
- Highlight visual dynamics: character actions, object movements, camera movements, scene transitions, etc.
- Use symbolic techniques to visualize abstract concepts (e.g., use flowing water to represent the passage of time, rising stairs to represent progress, etc.)
- Scenes should express rich emotions and actions to enhance visual impact
- Enhance expressiveness through camera language (push, pull, pan, tilt) and editing rhythm

## Key English Vocabulary Reference
- Actions: moving, running, flowing, transforming, growing, falling
- Camera: camera pan, zoom in, zoom out, tracking shot, aerial view
- Transitions: transition, fade in, fade out, dissolve
- Atmosphere: dynamic, energetic, peaceful, dramatic, mysterious
- Lighting: lighting changes, shadows moving, sunlight streaming

## Video and Copy Coordination Principles
- Videos should serve the copy, becoming a visual extension of the copy content
- Avoid visual elements unrelated to or contradicting the copy content
- Choose dynamic presentation methods that best enhance the persuasiveness of the copy
- Ensure the audience can quickly understand the core viewpoint of the copy through video dynamics

## Creative Guidance
1. **Phenomenon Description Copy**: Use dynamic scenes to represent the occurrence process of social phenomena
2. **Cause Analysis Copy**: Use dynamic evolution of cause-and-effect relationships to represent internal logic
3. **Impact Argumentation Copy**: Use dynamic unfolding of consequence scenes or contrasts to represent the degree of impact
4. **In-depth Discussion Copy**: Use dynamic concretization of abstract concepts to represent deep thinking
5. **Conclusion Inspiration Copy**: Use open-ended dynamic scenes or guiding movements to represent inspiration

## Video-Specific Considerations
- Emphasize dynamics: Each video should include obvious actions or movements
- Camera language: Appropriately use camera techniques such as push, pull, pan, tilt to enhance expressiveness
- Duration consideration: Videos should be a coherent dynamic process, not static images
- Fluidity: Pay attention to the fluidity and naturalness of actions

# Output Format
Strictly output in the following JSON format, **video prompts must be in {output_language_label}**:

```json
{{
  "video_prompts": [
    "{example_prompt}",
    "{example_prompt}"
  ]
}}
```

# Important Reminders
1. Only output JSON format content, do not add any explanations
2. Ensure JSON format is strictly correct and can be directly parsed by the program
3. Frame-aware input uses {{"frame_source_texts": [source text array]}} format, output is {{"video_prompts": [video prompt array]}} format
4. **The output video_prompts array must contain exactly {narrations_count} elements, corresponding one-to-one with the input frame source texts**
5. **{language_requirement}**
6. Video prompts must accurately reflect the specific content and emotion of the corresponding frame source text
7. Each video must emphasize dynamics and sense of movement, avoid static descriptions
8. Appropriately use camera language to enhance expressiveness
9. Ensure video scenes can enhance the persuasiveness of the copy and audience understanding

Now, please create {narrations_count} corresponding **{output_language_label}** video prompts for the above {narrations_count} storyboard frames. Only output JSON, no other content.
"""


def build_video_prompt_prompt(
    narrations: List[str],
    min_words: int,
    max_words: int,
    style_profile: Optional[dict[str, Any]] = None,
    prompt_contexts: Optional[PromptContextInput] = None,
    prompt_language: PromptLanguage = DEFAULT_PROMPT_LANGUAGE,
) -> str:
    """
    Build video prompt generation prompt
    
    Args:
        narrations: List of narrations
        min_words: Minimum word count
        max_words: Maximum word count
    
    Returns:
        Formatted prompt for LLM
    
    Example:
        >>> build_video_prompt_prompt(narrations, 50, 100)
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
        language_requirement = "Video prompts must use Chinese"
        description_length_guidance = (
            "Ensure clear, complete, and creative descriptions "
            f"(roughly equivalent in detail density to {min_words}-{max_words} English words)"
        )
        example_prompt = "[detailed Chinese video prompt with dynamic elements and camera movements]"
    else:
        output_language_label = "English"
        language_requirement = "Video prompts must use English"
        description_length_guidance = (
            f"Ensure clear, complete, and creative descriptions (recommended {min_words}-{max_words} English words)"
        )
        example_prompt = "[detailed English video prompt with dynamic elements and camera movements]"
    
    return VIDEO_PROMPT_GENERATION_PROMPT.format(
        style_profile_json=style_profile_json,
        narrations_json=narrations_json,
        narrations_count=len(narrations),
        min_words=min_words,
        max_words=max_words
        ,
        output_language_label=output_language_label,
        language_requirement=language_requirement,
        description_length_guidance=description_length_guidance,
        example_prompt=example_prompt,
    )
