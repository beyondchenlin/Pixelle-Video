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
Topic narration generation prompt

For generating narrations from a topic/theme.
"""



def render_topic_narration_prompt(
    topic: str,
    n_storyboard: int,
    min_words: int,
    max_words: int,
    preserve_natural_punctuation: bool = True,
) -> RenderedPrompt:
    """
    Build topic narration prompt
    
    Args:
        topic: Topic or theme
        n_storyboard: Number of storyboard frames
        min_words: Minimum word count
        max_words: Maximum word count
    
    Returns:
        Formatted prompt
    """
    punctuation_instruction = (
        "- 生成文稿时保留自然标点。"
        if preserve_natural_punctuation
        else ""
    )
    return render_prompt_template(
        "topic_narration",
        {
            "topic": topic,
            "n_storyboard": n_storyboard,
            "min_words": min_words,
            "max_words": max_words,
            "punctuation_instruction": punctuation_instruction,
        },
    )



def build_topic_narration_prompt(
    topic: str,
    n_storyboard: int,
    min_words: int,
    max_words: int,
    preserve_natural_punctuation: bool = True,
) -> str:
    return render_topic_narration_prompt(
        topic,
        n_storyboard,
        min_words,
        max_words,
        preserve_natural_punctuation=preserve_natural_punctuation,
    ).text
