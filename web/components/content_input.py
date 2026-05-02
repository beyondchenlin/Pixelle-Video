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
Content input components for web UI (left column)
"""

import streamlit as st

from pixelle_video.models.script_generation_limits import SCRIPT_TARGET_WORDS_MAX
from pixelle_video.models.storyboard_limits import (
    DETERMINISTIC_STORYBOARD_MAX_SCENE_COUNT_MIN,
    StoryboardGenerationLimits,
    current_storyboard_generation_limits,
)
from pixelle_video.models.video_generation_contract import StoryboardControlsContract
from pixelle_video.prompt_language import (
    CHINESE_PROMPT_LANGUAGE,
    ENGLISH_PROMPT_LANGUAGE,
)
from web.components.prompt_generation_performance import (
    render_prompt_generation_performance_controls,
)
from web.components.storyboard_planning_controls import (
    render_storyboard_advanced_controls,
)
from web.i18n import tr
from web.state.storyboard_preview import get_storyboard_preview_snapshot
from web.utils.async_helpers import get_project_version

SCRIPT_TARGET_WORDS_MIN = 50
SCRIPT_TARGET_WORDS_DEFAULT = 200
SCRIPT_TARGET_WORDS_STEP = 50


def get_storyboard_generation_limits() -> StoryboardGenerationLimits:
    return current_storyboard_generation_limits()


def _clamp_script_target_words(value: int | float | None) -> int:
    if value is None:
        return SCRIPT_TARGET_WORDS_DEFAULT
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = SCRIPT_TARGET_WORDS_DEFAULT
    return min(max(parsed, SCRIPT_TARGET_WORDS_MIN), SCRIPT_TARGET_WORDS_MAX)


def _initialize_script_target_words_state(*, slider_key: str, input_key: str) -> int:
    stored_value = st.session_state.get(
        input_key,
        st.session_state.get(slider_key, SCRIPT_TARGET_WORDS_DEFAULT),
    )
    target_words = _clamp_script_target_words(stored_value)
    st.session_state[slider_key] = target_words
    st.session_state[input_key] = target_words
    return target_words


def _sync_script_target_words_state(*, source_key: str, target_key: str) -> None:
    st.session_state[target_key] = _clamp_script_target_words(
        st.session_state.get(source_key)
    )


def build_script_generation_payload(
    *,
    mode: str,
    script_target_words: int | None,
) -> dict:
    """Normalize source script-generation controls into the video request contract."""
    if mode != "generate":
        return {
            "script_length_mode": "auto",
            "script_target_words": None,
        }
    return {
        "script_length_mode": "custom",
        "script_target_words": _clamp_script_target_words(script_target_words),
    }


def build_storyboard_generation_payload(
    *,
    storyboard_mode: str,
    storyboard_count_mode: str,
    storyboard_scene_count: int | None,
    storyboard_max_scene_count: int | None = None,
    storyboard_prompt_language: str = CHINESE_PROMPT_LANGUAGE,
) -> dict:
    """Normalize UI storyboard generation controls into the video request contract."""
    resolved_storyboard_max_scene_count = storyboard_max_scene_count
    if (
        storyboard_mode in {"punctuation", "sentence"}
        and resolved_storyboard_max_scene_count is None
    ):
        resolved_storyboard_max_scene_count = (
            get_storyboard_generation_limits().default_deterministic_max_scene_count
        )
    return StoryboardControlsContract.from_mapping(
        {
            "storyboard_mode": storyboard_mode,
            "storyboard_count_mode": storyboard_count_mode,
            "storyboard_scene_count": storyboard_scene_count,
            "storyboard_max_scene_count": resolved_storyboard_max_scene_count,
            "storyboard_prompt_language": storyboard_prompt_language,
        },
        default_prompt_language=CHINESE_PROMPT_LANGUAGE,
    ).to_generation_dict()


def render_storyboard_generation_explanation() -> None:
    """Render a concise help block for storyboard generation controls."""
    with st.expander(
        tr("storyboard.generation.explanation.title", fallback="设置说明"),
        expanded=False,
    ):
        st.markdown(
            tr(
                "storyboard.generation.explanation.body",
                fallback=(
                    "**Smart**：让 AI 先理解完整脚本，再自动规划每个画面覆盖哪段内容，"
                    "适合大多数主题。\n\n"
                    "**按所有标点（中英文）**：遇到逗号、句号、问号等标点就切一段，"
                    "分镜会更细。\n\n"
                    "**按句末标点（。.!?！？）**：只按句子结束位置切分，节奏更稳。\n\n"
                    "**自动**：AI 在 1-30 个分镜里自己选择合适数量；"
                    "**分镜数**：手动指定要生成多少个分镜。\n\n"
                    "**max_tokens**：这是模型最多能输出多少 JSON 内容，不是分镜数量；"
                    "本地会使用 Qwen 能接受的上限，避免请求被 400 拒绝。"
                ),
            )
        )


def render_storyboard_generation_controls(*, mode: str, key_prefix: str) -> dict:
    """Render controls for source-text storyboard generation."""
    with st.expander(
        tr("section.storyboard_planning", fallback="🧭 分镜规划"),
        expanded=False,
    ):
        storyboard_mode = st.radio(
            "Storyboard Mode",
            ["smart", "punctuation", "sentence"],
            index=0,
            horizontal=True,
            key=f"{key_prefix}_storyboard_mode",
            format_func=lambda value: {
                "smart": "Smart",
                "punctuation": tr("split.mode_punctuation"),
                "sentence": tr("split.mode_sentence"),
            }[value],
        )

        storyboard_count_mode = "auto"
        storyboard_scene_count = None
        storyboard_max_scene_count = None
        if storyboard_mode == "smart":
            storyboard_limits = get_storyboard_generation_limits()
            storyboard_count_mode = st.radio(
                "Scene Count",
                ["auto", "manual"],
                index=0,
                horizontal=True,
                key=f"{key_prefix}_storyboard_count_mode",
                format_func=lambda value: {
                    "auto": tr("storyboard.option.content_mode.auto"),
                    "manual": tr("video.frames"),
                }[value],
            )
            if storyboard_count_mode == "manual":
                storyboard_scene_count = st.slider(
                    tr("video.frames"),
                    min_value=storyboard_limits.min_scene_count,
                    max_value=storyboard_limits.max_scene_count,
                    value=min(
                        max(5, storyboard_limits.min_scene_count),
                        storyboard_limits.max_scene_count,
                    ),
                    key=f"{key_prefix}_storyboard_scene_count",
                    help=tr("video.frames_help"),
                )
        else:
            st.caption(tr("video.frames_fixed_mode_hint"))
            storyboard_limits = get_storyboard_generation_limits()
            storyboard_max_scene_count = st.slider(
                tr("storyboard.max_scene_count"),
                min_value=DETERMINISTIC_STORYBOARD_MAX_SCENE_COUNT_MIN,
                max_value=storyboard_limits.deterministic_max_scene_count_limit,
                value=storyboard_limits.default_deterministic_max_scene_count,
                key=f"{key_prefix}_storyboard_max_scene_count",
                help=tr("storyboard.max_scene_count_help"),
            )

        selected_template_type_for_storyboard = st.session_state.get("template_type_selector")
        storyboard_prompt_language = st.radio(
            tr("storyboard.prompt_language"),
            options=[CHINESE_PROMPT_LANGUAGE, ENGLISH_PROMPT_LANGUAGE],
            index=0,
            horizontal=True,
            key=f"{key_prefix}_storyboard_prompt_language",
            format_func=lambda value: tr(f"storyboard.option.prompt_language.{value}"),
            help=tr("storyboard.prompt_language_help"),
            disabled=selected_template_type_for_storyboard == "static",
        )

        render_storyboard_generation_explanation()
        advanced_storyboard_payload = render_storyboard_advanced_controls(
            ui=st,
            translate=tr,
            session_state=st.session_state,
            storyboard_default_enabled=False,
            selected_template_type=selected_template_type_for_storyboard,
            preview_snapshot=get_storyboard_preview_snapshot(st.session_state),
        )

        return {
            **build_storyboard_generation_payload(
                storyboard_mode=storyboard_mode,
                storyboard_count_mode=storyboard_count_mode,
                storyboard_scene_count=storyboard_scene_count,
                storyboard_max_scene_count=storyboard_max_scene_count,
                storyboard_prompt_language=storyboard_prompt_language,
            ),
            **advanced_storyboard_payload,
        }


def render_script_generation_controls(*, mode: str, key_prefix: str) -> dict:
    """Render source script-generation controls for AI creation mode."""
    if mode != "generate":
        return build_script_generation_payload(
            mode=mode,
            script_target_words=None,
        )

    slider_key = f"{key_prefix}_script_target_words_slider"
    input_key = f"{key_prefix}_script_target_words_input"
    target_words = _initialize_script_target_words_state(
        slider_key=slider_key,
        input_key=input_key,
    )

    slider_col, input_col = st.columns([4, 1])
    with slider_col:
        st.slider(
            tr("script.target_words"),
            min_value=SCRIPT_TARGET_WORDS_MIN,
            max_value=SCRIPT_TARGET_WORDS_MAX,
            step=SCRIPT_TARGET_WORDS_STEP,
            key=slider_key,
            help=tr("script.target_words_help"),
            on_change=_sync_script_target_words_state,
            kwargs={"source_key": slider_key, "target_key": input_key},
        )
    with input_col:
        st.number_input(
            tr("script.target_words_input"),
            min_value=SCRIPT_TARGET_WORDS_MIN,
            max_value=SCRIPT_TARGET_WORDS_MAX,
            step=SCRIPT_TARGET_WORDS_STEP,
            key=input_key,
            label_visibility="collapsed",
            on_change=_sync_script_target_words_state,
            kwargs={"source_key": input_key, "target_key": slider_key},
        )
    target_words = _clamp_script_target_words(
        st.session_state.get(input_key, target_words)
    )

    return build_script_generation_payload(
        mode=mode,
        script_target_words=target_words,
    )


def render_content_input():
    """Render content input section (left column) with batch support"""
    with st.container(border=True):
        st.markdown(f"**{tr('section.content_input')}**")
        
        # ====================================================================
        # Step 1: Batch mode toggle (highest priority)
        # ====================================================================
        batch_mode = st.checkbox(
            tr("batch.mode_label"),
            value=False,
            help=tr("batch.mode_help")
        )
        
        if not batch_mode:
            # ================================================================
            # Single task mode (original logic, unchanged)
            # ================================================================
            # Processing mode selection
            mode = st.radio(
                "Processing Mode",
                ["generate", "fixed"],
                horizontal=True,
                format_func=lambda x: tr(f"mode.{x}"),
                label_visibility="collapsed"
            )
            
            # Text input (unified for both modes)
            text_placeholder = tr("input.topic_placeholder") if mode == "generate" else tr("input.content_placeholder")
            text_height = 120 if mode == "generate" else 200
            text_help = tr("input.text_help_generate") if mode == "generate" else tr("input.text_help_fixed")
            
            text = st.text_area(
                tr("input.text"),
                placeholder=text_placeholder,
                height=text_height,
                help=text_help
            )
            
            # Title input (optional for both modes)
            title = st.text_input(
                tr("input.title"),
                placeholder=tr("input.title_placeholder"),
                help=tr("input.title_help")
            )

            script_generation = render_script_generation_controls(
                mode=mode,
                key_prefix="single_video",
            )
            
            storyboard_generation = render_storyboard_generation_controls(
                mode=mode,
                key_prefix="single_video",
            )

            prompt_generation_performance = render_prompt_generation_performance_controls(
                key_prefix="single_video"
            )
            
            return {
                "batch_mode": False,
                "mode": mode,
                "text": text,
                "title": title,
                **script_generation,
                **storyboard_generation,
                **prompt_generation_performance,
            }
        
        else:
            # ================================================================
            # Batch mode (simplified YAGNI version)
            # ================================================================
            st.markdown(f"**{tr('batch.section_title')}**")
            
            # Batch rules info
            st.info(f"""
**{tr('batch.rules_title')}**
- ✅ {tr('batch.rule_1')}
- ✅ {tr('batch.rule_2')}
- ✅ {tr('batch.rule_3')}
            """)
            
            # Batch topics input
            text_input = st.text_area(
                tr("batch.topics_label"),
                height=300,
                placeholder=tr("batch.topics_placeholder"),
                help=tr("batch.topics_help")
            )
            
            # Split topics by newline
            if text_input:
                # Simple split by newline, filter empty lines
                topics = [
                    line.strip() 
                    for line in text_input.strip().split('\n') 
                    if line.strip()
                ]
                
                if topics:
                    # Check count limit
                    if len(topics) > 100:
                        st.error(tr("batch.count_error", count=len(topics)))
                        topics = []
                    else:
                        st.success(tr("batch.count_success", count=len(topics)))
                        
                        # Preview topics list
                        with st.expander(tr("batch.preview_title"), expanded=False):
                            for i, topic in enumerate(topics, 1):
                                st.markdown(f"`{i}.` {topic}")
                else:
                    topics = []
            else:
                topics = []
            
            st.markdown("---")
            
            # Title prefix (optional)
            title_prefix = st.text_input(
                tr("batch.title_prefix_label"),
                placeholder=tr("batch.title_prefix_placeholder"),
                help=tr("batch.title_prefix_help")
            )

            script_generation = render_script_generation_controls(
                mode="generate",
                key_prefix="batch_video",
            )
            
            storyboard_generation = render_storyboard_generation_controls(
                mode="generate",
                key_prefix="batch_video",
            )

            prompt_generation_performance = render_prompt_generation_performance_controls(
                key_prefix="batch_video"
            )
            
            # Config info
            st.info(f"📌 {tr('batch.config_info')}")
            
            return {
                "batch_mode": True,
                "topics": topics,
                "mode": "generate",  # Fixed to AI generate content
                "title_prefix": title_prefix,
                **script_generation,
                **storyboard_generation,
                **prompt_generation_performance,
            }


def render_version_info():
    """Render version info and GitHub link"""
    with st.container(border=True):
        st.markdown(f"**{tr('version.title')}**")
        version = get_project_version()
        github_url = "https://github.com/AIDC-AI/Pixelle-Video"
        
        # Version and GitHub link in one line
        github_url = "https://github.com/AIDC-AI/Pixelle-Video"
        badge_url = "https://img.shields.io/github/stars/AIDC-AI/Pixelle-Video"

        st.markdown(
            f'{tr("version.current")}: `{version}` &nbsp;&nbsp; '
            f'<a href="{github_url}" target="_blank">'
            f'<img src="{badge_url}" alt="GitHub stars" style="vertical-align: middle;">'
            f'</a>',
            unsafe_allow_html=True)
