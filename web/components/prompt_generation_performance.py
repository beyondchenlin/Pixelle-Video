"""Prompt generation performance controls shared by quick-create flows."""

import streamlit as st

from pixelle_video.config import config_manager
from pixelle_video.utils.prompt_generation_performance import (
    LLM_PROMPT_BATCH_CONCURRENT_LIMIT_PARAM,
    LLM_PROMPT_BATCH_SIZE_PARAM,
    PROMPT_BATCH_CONCURRENT_LIMIT_MAX,
    PROMPT_BATCH_CONCURRENT_LIMIT_MIN,
    PROMPT_BATCH_SIZE_MAX,
    PROMPT_BATCH_SIZE_MIN,
    copy_prompt_generation_performance_params,
)
from web.i18n import tr

__all__ = [
    "LLM_PROMPT_BATCH_CONCURRENT_LIMIT_PARAM",
    "LLM_PROMPT_BATCH_SIZE_PARAM",
    "copy_prompt_generation_performance_params",
    "render_prompt_generation_performance_controls",
]


def _read_llm_prompt_defaults() -> tuple[int, int]:
    llm_config = config_manager.get_llm_config()
    return (
        int(llm_config.get("prompt_batch_size", 10) or 10),
        int(llm_config.get("prompt_batch_concurrent_limit", 1) or 1),
    )


def render_prompt_generation_performance_controls(*, key_prefix: str) -> dict[str, int]:
    """Render request-scoped prompt generation controls and return enabled overrides."""
    default_batch_size, default_concurrency = _read_llm_prompt_defaults()

    with st.expander(tr("prompt_generation_performance.title"), expanded=False):
        st.caption(
            tr(
                "prompt_generation_performance.default_summary",
                batch_size=default_batch_size,
                concurrency=default_concurrency,
            )
        )
        st.caption(tr("prompt_generation_performance.help"))

        custom_enabled = st.checkbox(
            tr("prompt_generation_performance.custom_enabled"),
            value=False,
            key=f"{key_prefix}_prompt_generation_performance_enabled",
        )
        if not custom_enabled:
            return {}

        batch_col, concurrency_col = st.columns(2)
        with batch_col:
            batch_size = st.number_input(
                tr("prompt_generation_performance.batch_size"),
                min_value=PROMPT_BATCH_SIZE_MIN,
                max_value=PROMPT_BATCH_SIZE_MAX,
                value=default_batch_size,
                help=tr("prompt_generation_performance.batch_size_help"),
                key=f"{key_prefix}_llm_prompt_batch_size",
            )
        with concurrency_col:
            concurrency = st.number_input(
                tr("prompt_generation_performance.concurrency"),
                min_value=PROMPT_BATCH_CONCURRENT_LIMIT_MIN,
                max_value=PROMPT_BATCH_CONCURRENT_LIMIT_MAX,
                value=default_concurrency,
                help=tr("prompt_generation_performance.concurrency_help"),
                key=f"{key_prefix}_llm_prompt_batch_concurrent_limit",
            )

    return {
        LLM_PROMPT_BATCH_SIZE_PARAM: int(batch_size),
        LLM_PROMPT_BATCH_CONCURRENT_LIMIT_PARAM: int(concurrency),
    }
