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
Title generation prompt

For generating video title from content.
"""



def render_title_generation_prompt(content: str, max_length: int = 15) -> RenderedPrompt:
    """
    Build title generation prompt
    
    Args:
        content: Content to generate title from
        max_length: Maximum title length in characters (default: 15)
    
    Returns:
        Formatted prompt with character limit
    """
    # Take first 500 chars to avoid overly long prompts
    content_preview = content[:500]
    
    return render_prompt_template(
        "title_generation",
        {
            "content": content_preview,
            "max_length": max_length,
        },
    )




def build_title_generation_prompt(content: str, max_length: int = 15) -> str:
    return render_title_generation_prompt(content, max_length=max_length).text
