from pathlib import Path

from web.components.prompt_generation_performance import (
    LLM_PROMPT_BATCH_CONCURRENT_LIMIT_PARAM,
    LLM_PROMPT_BATCH_SIZE_PARAM,
    copy_prompt_generation_performance_params,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_copy_prompt_generation_performance_params_omits_absent_values():
    target = {"mode": "generate"}

    copy_prompt_generation_performance_params({}, target)

    assert LLM_PROMPT_BATCH_SIZE_PARAM not in target
    assert LLM_PROMPT_BATCH_CONCURRENT_LIMIT_PARAM not in target


def test_copy_prompt_generation_performance_params_copies_enabled_values():
    target = {}

    copy_prompt_generation_performance_params(
        {
            LLM_PROMPT_BATCH_SIZE_PARAM: 8,
            LLM_PROMPT_BATCH_CONCURRENT_LIMIT_PARAM: 3,
        },
        target,
    )

    assert target[LLM_PROMPT_BATCH_SIZE_PARAM] == 8
    assert target[LLM_PROMPT_BATCH_CONCURRENT_LIMIT_PARAM] == 3


def test_prompt_generation_performance_ui_uses_plain_title_without_gear_icon():
    source = (
        PROJECT_ROOT / "web" / "components" / "prompt_generation_performance.py"
    ).read_text(encoding="utf-8")

    assert 'tr("prompt_generation_performance.title")' in source
    assert "\u26a1" not in source
    assert "\u2699" not in source


def test_system_settings_do_not_render_llm_prompt_generation_performance_controls():
    source = (PROJECT_ROOT / "web" / "components" / "settings.py").read_text(
        encoding="utf-8"
    )

    assert "settings.llm.default_performance_title" not in source
    assert "settings.llm.prompt_batch_size" not in source
    assert "settings.llm.prompt_batch_concurrent_limit" not in source
    assert "llm_prompt_batch_size_input" not in source
    assert "llm_prompt_batch_concurrent_limit_input" not in source
    assert "prompt_batch_size=int" not in source
    assert "prompt_batch_concurrent_limit=int" not in source
