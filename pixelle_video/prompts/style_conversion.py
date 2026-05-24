from pixelle_video.prompts.template_loader import RenderedPrompt, render_prompt_template

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
Style conversion prompt

For converting user's custom style description to image generation prompt.
"""



def render_style_conversion_prompt(description: str) -> RenderedPrompt:
    """
    Build style conversion prompt
    
    Converts user's custom style description (in any language) to an English
    image generation prompt suitable for Stable Diffusion/FLUX models.
    
    Args:
        description: User's style description in any language
    
    Returns:
        Formatted prompt
    
    Example:
        >>> build_style_conversion_prompt("赛博朋克风格，霓虹灯，未来感")
        # Returns prompt that will convert to: "cyberpunk style, neon lights, futuristic..."
    """
    return render_prompt_template(
        "style_conversion",
        {"description": description},
    )




def build_style_conversion_prompt(description: str) -> str:
    return render_style_conversion_prompt(description).text
