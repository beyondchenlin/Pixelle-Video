from pixelle_video.config import config_manager
from pixelle_video.config.schema import PixelleVideoConfig
from pixelle_video.utils import prompt_generation_performance as prompt_performance
from pixelle_video.utils.content_generators import (
    _resolve_llm_prompt_batch_concurrency,
    _resolve_llm_prompt_batch_size,
)


def test_llm_config_exposes_only_connection_settings():
    original_config = config_manager.config
    try:
        config_manager.config = PixelleVideoConfig()

        config_manager.set_llm_config(
            api_key="key",
            base_url="https://example.test/v1",
            model="demo-model",
        )

        updated = config_manager.get_llm_config()
        assert updated == {
            "api_key": "key",
            "base_url": "https://example.test/v1",
            "model": "demo-model",
        }
    finally:
        config_manager.config = original_config


def test_legacy_llm_prompt_batch_settings_are_ignored_by_schema():
    config = PixelleVideoConfig(
        llm={
            "api_key": "key",
            "base_url": "https://example.test/v1",
            "model": "demo-model",
            "prompt_batch_size": 6,
            "prompt_batch_concurrent_limit": 3,
        }
    )

    assert not hasattr(config.llm, "prompt_batch_size")
    assert not hasattr(config.llm, "prompt_batch_concurrent_limit")
    assert config.llm.model_dump() == {
        "api_key": "key",
        "base_url": "https://example.test/v1",
        "model": "demo-model",
    }


def test_prompt_generation_defaults_are_owned_by_prompt_performance_module():
    assert getattr(prompt_performance, "DEFAULT_PROMPT_BATCH_SIZE", None) == 10
    assert getattr(prompt_performance, "DEFAULT_PROMPT_BATCH_CONCURRENT_LIMIT", None) == 1


def test_prompt_generation_default_resolver_ignores_legacy_llm_config():
    original_config = config_manager.config
    try:
        config_manager.config = PixelleVideoConfig(
            llm={
                "api_key": "key",
                "base_url": "https://example.test/v1",
                "model": "demo-model",
                "prompt_batch_size": 6,
                "prompt_batch_concurrent_limit": 3,
            }
        )

        assert _resolve_llm_prompt_batch_size(None) == 10
        assert _resolve_llm_prompt_batch_concurrency(None) == 1
        assert _resolve_llm_prompt_batch_size(6) == 6
        assert _resolve_llm_prompt_batch_concurrency(3) == 3
    finally:
        config_manager.config = original_config

