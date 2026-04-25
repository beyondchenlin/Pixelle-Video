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
    assert "⚙" not in source
    assert "齿轮" not in source
